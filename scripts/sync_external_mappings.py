#!/usr/bin/env python3
"""Safely extend Papirus Android component mappings from other icon packs.

Matches are inferred from existing, trusted Papirus mappings rather than app-name
fuzzy matching. Imported mappings are tracked separately and never become new
anchors, preventing self-reinforcing matches across runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data.json"
DEFAULT_PROVENANCE = ROOT / "external-mappings.json"
SINGLE_ANCHOR_MAX_GROUP = 10
DRAWABLE_PREFIXES = ("apps_", "games_", "google_", "system_")

SOURCES = {
    "arcticons": "https://raw.githubusercontent.com/Arcticons-Team/Arcticons/main/app/src/main/res/xml/appfilter.xml",
    "lawnicons": "https://raw.githubusercontent.com/LawnchairLauncher/lawnicons/develop/app/assets/appfilter.xml",
}


def normalize_component(value: str) -> str:
    value = value.strip()
    if value.startswith("ComponentInfo{") and value.endswith("}"):
        value = value[len("ComponentInfo{") : -1]
    return value


def normalize_drawable(value: str) -> str:
    value = value.lower().strip()
    for prefix in DRAWABLE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def load_database(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_provenance(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "components": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("components", {}), dict):
        raise ValueError(f"{path} must contain an object with a components object")
    data.setdefault("version", 1)
    data.setdefault("components", {})
    return data


def reverse_database(data: dict[str, list[str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for drawable, components in data.items():
        if not isinstance(components, list):
            raise ValueError(f"{drawable!r} must map to a list")
        for component in components:
            result[normalize_component(component)].add(drawable)
    return dict(result)


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
        component = normalize_component(component)
        if "/" in component:
            groups[drawable].add(component)
    return groups


def selected_sources(names: Iterable[str], custom_sources: list[str]) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for name in names:
        if name == "all":
            for pair in SOURCES.items():
                if pair not in selected:
                    selected.append(pair)
        else:
            selected.append((name, SOURCES[name]))
    for index, source in enumerate(custom_sources, start=1):
        selected.append((f"custom-{index}", source))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--source", action="append", choices=[*SOURCES.keys(), "all"], default=[])
    parser.add_argument("--appfilter", action="append", default=[], metavar="URL_OR_FILE")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--report-unresolved", action="store_true")
    args = parser.parse_args()

    sources = selected_sources(args.source or ["all"], args.appfilter)
    data = load_database(args.db)
    provenance = load_provenance(args.provenance)
    imported_components = set(provenance["components"])
    reverse = reverse_database(data)

    trusted_reverse = {
        component: next(iter(targets))
        for component, targets in reverse.items()
        if len(targets) == 1 and component not in imported_components
    }
    ambiguous_existing = {c for c, targets in reverse.items() if len(targets) > 1}

    proposals: dict[str, set[str]] = defaultdict(set)
    proposal_sources: dict[str, set[str]] = defaultdict(set)
    group_conflicts: list[tuple[str, str, list[str]]] = []
    rejected_low_confidence = 0
    unresolved = 0
    accepted_groups = 0

    print(
        f"Papirus: {len(data)} icons, {len(reverse)} unique components, "
        f"{len(trusted_reverse)} trusted anchors, {len(imported_components)} external mappings, "
        f"{len(ambiguous_existing)} legacy ambiguous components"
    )

    for source_name, source in sources:
        print(f"\n[{source_name}] reading {source}")
        groups = parse_appfilter(read_source(source))
        source_accepted = source_proposals = source_conflicts = 0
        source_rejected = source_unresolved = 0

        for external_drawable, components in groups.items():
            anchor_components = [c for c in components if c in trusted_reverse]
            targets = {trusted_reverse[c] for c in anchor_components}

            if len(targets) > 1:
                group_conflicts.append((source_name, external_drawable, sorted(targets)))
                source_conflicts += 1
                continue
            if not targets:
                unresolved += 1
                source_unresolved += 1
                if args.report_unresolved:
                    print(f"  unresolved: {external_drawable} ({len(components)} components)")
                continue

            target = next(iter(targets))
            exact_name = normalize_drawable(external_drawable) == normalize_drawable(target)
            multi_anchor = len(anchor_components) >= 2
            small_group = len(components) <= SINGLE_ANCHOR_MAX_GROUP
            if not (exact_name or multi_anchor or small_group):
                rejected_low_confidence += 1
                source_rejected += 1
                continue

            accepted_groups += 1
            source_accepted += 1
            for component in components:
                if component not in reverse:
                    proposals[component].add(target)
                    proposal_sources[component].add(source_name)
                    source_proposals += 1

        print(
            f"  groups={len(groups)}, accepted={source_accepted}, proposals={source_proposals}, "
            f"conflicts={source_conflicts}, low-confidence={source_rejected}, "
            f"unresolved={source_unresolved}"
        )

    additions: dict[str, set[str]] = defaultdict(set)
    proposal_conflicts: dict[str, set[str]] = {}
    for component, targets in proposals.items():
        if len(targets) == 1:
            additions[next(iter(targets))].add(component)
        else:
            proposal_conflicts[component] = targets

    unique_additions = sum(len(values) for values in additions.values())
    print(
        f"\nResult: {unique_additions} unique new component mappings for "
        f"{len(additions)} Papirus icons from {accepted_groups} accepted groups."
    )
    print(f"Rejected {rejected_low_confidence} low-confidence groups.")

    if group_conflicts:
        print(f"Skipped {len(group_conflicts)} ambiguous external drawable groups.")
        for source_name, external_drawable, targets in group_conflicts[:20]:
            print(f"  {source_name}:{external_drawable} -> {', '.join(targets)}")
    if proposal_conflicts:
        print(f"Skipped {len(proposal_conflicts)} new components proposed for multiple Papirus icons.")
        for component, targets in list(sorted(proposal_conflicts.items()))[:20]:
            print(f"  {component} -> {', '.join(sorted(targets))}")

    if not args.write:
        print("Dry-run only. Re-run with --write to update data.json and provenance.")
        return 0

    for drawable, components in additions.items():
        existing_list = [normalize_component(c) for c in data[drawable]]
        existing_set = set(existing_list)
        new_components = sorted(c for c in components if c not in existing_set)
        data[drawable] = existing_list + new_components
        for component in new_components:
            provenance["components"][component] = {
                "drawable": drawable,
                "sources": sorted(proposal_sources[component]),
            }

    with args.db.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with args.provenance.open("w", encoding="utf-8") as handle:
        json.dump(provenance, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Updated data and provenance with {unique_additions} mappings.")
    if unresolved:
        print(f"Left {unresolved} external drawable groups unresolved.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
