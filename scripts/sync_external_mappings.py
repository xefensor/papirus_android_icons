#!/usr/bin/env python3
"""Safely extend Papirus Android component mappings from other icon packs.

The importer deliberately does not guess icon matches from app names. Instead it
uses mapping overlap:

1. Read Papirus' existing component -> drawable mapping from data.json.
2. Group an external appfilter.xml by its drawable.
3. If components in one external drawable group overlap exactly one Papirus
   drawable, infer that the whole external group represents that Papirus icon.
4. Add only previously unknown components from that unambiguous group.

This lets actively maintained packs teach us new package/activity aliases while
keeping Papirus' existing artwork and mapping decisions authoritative.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Iterable

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data.json"

SOURCES = {
    "arcticons": "https://raw.githubusercontent.com/Arcticons-Team/Arcticons/main/app/src/main/res/xml/appfilter.xml",
    "lawnicons": "https://raw.githubusercontent.com/LawnchairLauncher/lawnicons/develop/app/assets/appfilter.xml",
}


def normalize_component(value: str) -> str:
    value = value.strip()
    if value.startswith("ComponentInfo{") and value.endswith("}"):
        value = value[len("ComponentInfo{") : -1]
    return value


def load_database(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def reverse_database(data: dict[str, list[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    duplicates: dict[str, set[str]] = defaultdict(set)

    for drawable, components in data.items():
        if not isinstance(components, list):
            raise ValueError(f"{drawable!r} must map to a list")
        for component in components:
            normalized = normalize_component(component)
            if normalized in result and result[normalized] != drawable:
                duplicates[normalized].update((result[normalized], drawable))
            else:
                result[normalized] = drawable

    if duplicates:
        sample = next(iter(duplicates.items()))
        raise ValueError(
            "Papirus data.json contains components assigned to multiple icons; "
            f"cannot infer safely. Example: {sample[0]} -> {sorted(sample[1])}"
        )

    return result


def read_source(source: str) -> bytes:
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "papirus-android-mapping-sync/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    return Path(source).read_bytes()


def parse_appfilter(content: bytes) -> dict[str, set[str]]:
    root = ET.fromstring(content)
    groups: dict[str, set[str]] = defaultdict(set)

    for item in root.iter("item"):
        component = item.attrib.get("component")
        drawable = item.attrib.get("drawable")
        if not component or not drawable:
            continue
        normalized = normalize_component(component)
        if "/" not in normalized:
            continue
        groups[drawable].add(normalized)

    return groups


def selected_sources(names: Iterable[str], custom_sources: list[str]) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for name in names:
        if name == "all":
            for source_name, source_url in SOURCES.items():
                if (source_name, source_url) not in selected:
                    selected.append((source_name, source_url))
        else:
            selected.append((name, SOURCES[name]))

    for index, source in enumerate(custom_sources, start=1):
        selected.append((f"custom-{index}", source))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to data.json")
    parser.add_argument(
        "--source",
        action="append",
        choices=[*SOURCES.keys(), "all"],
        default=[],
        help="Known mapping source; may be repeated (default: all)",
    )
    parser.add_argument(
        "--appfilter",
        action="append",
        default=[],
        metavar="URL_OR_FILE",
        help="Additional appfilter.xml URL or local path",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write unambiguous new mappings to data.json (default is dry-run)",
    )
    parser.add_argument(
        "--report-unresolved",
        action="store_true",
        help="Print external drawable groups that have no Papirus overlap",
    )
    args = parser.parse_args()

    source_names = args.source or ["all"]
    sources = selected_sources(source_names, args.appfilter)

    data = load_database(args.db)
    reverse = reverse_database(data)

    additions: dict[str, set[str]] = defaultdict(set)
    conflicts: list[tuple[str, str, list[str]]] = []
    unresolved = 0
    learned_groups = 0

    print(f"Papirus: {len(data)} icons, {len(reverse)} component mappings")

    for source_name, source in sources:
        print(f"\n[{source_name}] reading {source}")
        groups = parse_appfilter(read_source(source))
        source_additions = 0
        source_learned = 0
        source_conflicts = 0
        source_unresolved = 0

        for external_drawable, components in groups.items():
            targets = {reverse[c] for c in components if c in reverse}

            if len(targets) == 1:
                target = next(iter(targets))
                source_learned += 1
                learned_groups += 1
                for component in components:
                    if component not in reverse:
                        additions[target].add(component)
                        source_additions += 1
            elif len(targets) > 1:
                conflicts.append((source_name, external_drawable, sorted(targets)))
                source_conflicts += 1
            else:
                unresolved += 1
                source_unresolved += 1
                if args.report_unresolved:
                    print(f"  unresolved: {external_drawable} ({len(components)} components)")

        print(
            f"  groups={len(groups)}, inferred={source_learned}, "
            f"new-components={source_additions}, conflicts={source_conflicts}, "
            f"unresolved={source_unresolved}"
        )

    unique_additions = sum(len(values) for values in additions.values())
    print(
        f"\nResult: {unique_additions} unique new component mappings for "
        f"{len(additions)} Papirus icons from {learned_groups} inferred groups."
    )

    if conflicts:
        print(f"Skipped {len(conflicts)} ambiguous external groups:")
        for source_name, external_drawable, targets in conflicts[:20]:
            print(f"  {source_name}:{external_drawable} -> {', '.join(targets)}")
        if len(conflicts) > 20:
            print(f"  ... and {len(conflicts) - 20} more")

    if not args.write:
        print("Dry-run only. Re-run with --write to update data.json.")
        return 0

    for drawable, components in additions.items():
        existing = {normalize_component(c) for c in data[drawable]}
        existing.update(components)
        data[drawable] = sorted(existing)

    with args.db.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Updated {args.db} with {unique_additions} mappings.")
    if unresolved:
        print(
            f"Left {unresolved} external drawable groups unresolved; these need a "
            "different matching strategy or an icon request."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
