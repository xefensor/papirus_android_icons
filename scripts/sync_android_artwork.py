#!/usr/bin/env python3
"""Import Android-relevant artwork from desktop Papirus using exact-name evidence.

This is intentionally stricter than a generic desktop artwork sync. A new Android
icon is imported only when an external Android icon pack (currently Arcticons or
Lawnicons) has a drawable whose normalized name exactly matches a canonical
Papirus desktop SVG filename. Existing Android artwork and mappings always win.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from sync_desktop_icons import (
    alias_target,
    desktop_apps_dir,
    load_manifest,
    resource_name,
    sha256,
)
from sync_external_mappings import (
    SOURCES,
    normalize_component,
    parse_appfilter,
    read_source,
    selected_sources,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data.json"
DEFAULT_PROVENANCE = ROOT / "external-mappings.json"
DEFAULT_MANIFEST = ROOT / "desktop-sync.json"
DEFAULT_ANDROID_SRC = ROOT / "src"


def load_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def external_resource_name(drawable: str) -> str:
    """Normalize an external drawable using the same rules as desktop filenames."""
    name = drawable
    if name.startswith("apps_"):
        name = name[len("apps_") :]
    return resource_name(name + ".svg")


def build_desktop_index(apps_dir: Path) -> tuple[dict[str, Path], set[str], int]:
    index: dict[str, Path] = {}
    collisions: set[str] = set()
    aliases = 0

    for source in sorted(apps_dir.glob("*.svg"), key=lambda p: p.name.lower()):
        if alias_target(source) is not None:
            aliases += 1
            continue
        try:
            target = resource_name(source.name)
        except ValueError:
            continue

        if target in index and index[target].name != source.name:
            collisions.add(target)
            continue
        index[target] = source

    for target in collisions:
        index.pop(target, None)
    return index, collisions, aliases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path, help="desktop Papirus checkout or Papirus/64x64/apps")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--android-src", type=Path, default=DEFAULT_ANDROID_SRC)
    parser.add_argument("--source", action="append", choices=[*SOURCES.keys(), "all"], default=[])
    parser.add_argument("--appfilter", action="append", default=[], metavar="URL_OR_FILE")
    parser.add_argument("--upstream-ref", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--list", action="store_true", help="print every safe import candidate")
    args = parser.parse_args()

    apps_dir = desktop_apps_dir(args.desktop)
    desktop, collisions, aliases = build_desktop_index(apps_dir)

    data = load_json_object(args.db)
    provenance = load_json_object(args.provenance)
    provenance.setdefault("version", 1)
    provenance.setdefault("components", {})
    if not isinstance(provenance["components"], dict):
        raise ValueError(f"{args.provenance} components must be an object")

    manifest = load_manifest(args.manifest)
    managed: dict[str, dict] = manifest["icons"]
    android_src = args.android_src.resolve()

    existing_targets: dict[str, set[str]] = defaultdict(set)
    for drawable, components in data.items():
        if not isinstance(components, list):
            raise ValueError(f"{drawable!r} must map to a list")
        for component in components:
            existing_targets[normalize_component(component)].add(drawable)

    external_components: dict[str, set[str]] = defaultdict(set)
    external_sources: dict[str, set[str]] = defaultdict(set)
    for source_name, source in selected_sources(args.source or ["all"], args.appfilter):
        groups = parse_appfilter(read_source(source))
        for external_drawable, components in groups.items():
            target = external_resource_name(external_drawable)
            external_components[target].update(components)
            external_sources[target].add(source_name)

    existing_svgs = {path.stem for path in android_src.glob("*.svg")}
    candidates: dict[str, tuple[Path, set[str]]] = {}
    skipped_existing = 0
    skipped_existing_mapping = 0
    skipped_no_components = 0

    for target in sorted(set(desktop) & set(external_components)):
        if target in existing_svgs or target in data:
            skipped_existing += 1
            continue

        components = {normalize_component(c) for c in external_components[target]}
        if not components:
            skipped_no_components += 1
            continue

        # A brand-new icon must not steal a component that Papirus already maps.
        if any(component in existing_targets for component in components):
            skipped_existing_mapping += 1
            continue

        candidates[target] = (desktop[target], components)

    # Do not accept a component if separate exact-name candidates disagree about
    # where it belongs. Keep the non-conflicting remainder of each candidate.
    component_candidates: dict[str, set[str]] = defaultdict(set)
    for target, (_, components) in candidates.items():
        for component in components:
            component_candidates[component].add(target)
    ambiguous_components = {
        component for component, targets in component_candidates.items() if len(targets) > 1
    }

    safe: dict[str, tuple[Path, list[str]]] = {}
    for target, (source, components) in candidates.items():
        remaining = sorted(components - ambiguous_components)
        if remaining:
            safe[target] = (source, remaining)

    print(
        f"Desktop: {len(desktop)} canonical application SVGs, {aliases} aliases skipped, "
        f"{len(collisions)} normalized collisions skipped."
    )
    print(
        f"Android exact-name coverage: {len(safe)} safe new icon candidates; "
        f"{skipped_existing} already covered; {skipped_existing_mapping} overlap existing mappings; "
        f"{len(ambiguous_components)} ambiguous components removed."
    )

    if args.list or args.write:
        for target, (source, components) in sorted(safe.items()):
            print(
                f"{'IMPORT' if args.write else 'CANDIDATE'}: {source.name} -> {target}.svg "
                f"({len(components)} components; sources={','.join(sorted(external_sources[target]))})"
            )

    if not args.write:
        print("Dry-run only. Re-run with --write to import safe exact-name candidates.")
        return 0

    for target, (source, components) in safe.items():
        destination_name = target + ".svg"
        destination = android_src / destination_name
        shutil.copyfile(source, destination)
        data[target] = components
        managed[destination_name] = {
            "source": source.name,
            "sha256": sha256(source),
        }
        for component in components:
            provenance["components"][component] = {
                "drawable": target,
                "sources": sorted(external_sources[target]),
                "evidence": "desktop-exact-name",
            }

    if safe:
        manifest["upstream_ref"] = args.upstream_ref
        with args.db.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        with args.provenance.open("w", encoding="utf-8") as handle:
            json.dump(provenance, handle, indent=2, sort_keys=True)
            handle.write("\n")
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Imported {len(safe)} Android-relevant desktop Papirus icons.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
