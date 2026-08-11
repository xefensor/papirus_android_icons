#!/usr/bin/env python3
"""Import Android-relevant artwork from desktop Papirus conservatively.

A brand-new Android icon starts with an exact drawable-name match between an
Android icon pack and a canonical desktop Papirus SVG. Automatic imports then
require package-name identity evidence and pass an explicit review policy.
Existing Android artwork and mappings always win.
"""

from __future__ import annotations

import argparse
import json
import re
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
DEFAULT_POLICY = ROOT / "artwork-sync-policy.json"
DEFAULT_ANDROID_SRC = ROOT / "src"

IGNORED_IDENTITY_TOKENS = {
    "a",
    "an",
    "and",
    "app",
    "apps",
    "beta",
    "client",
    "dev",
    "for",
    "mobile",
    "of",
    "official",
    "the",
    "to",
}


def load_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_policy(path: Path) -> dict:
    data = load_json_object(path)
    if data.get("version") != 1:
        raise ValueError(f"unsupported artwork policy version in {path}")
    if not isinstance(data.get("deny"), list):
        raise ValueError(f"{path} must contain a deny list")
    if not isinstance(data.get("max_components"), int) or data["max_components"] < 1:
        raise ValueError(f"{path} max_components must be a positive integer")
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


def identity_tokens(target: str) -> list[str]:
    name = target.removeprefix("apps_")
    return [
        token
        for token in name.split("_")
        if token and token not in IGNORED_IDENTITY_TOKENS
    ]


def package_matches_target(target: str, component: str) -> bool:
    """Require the Android package name itself to carry the desktop identity.

    Activity names are deliberately ignored: generic frameworks such as Ren'Py
    may put their own name in hundreds of unrelated activities even though the
    installed application package is a completely different game.
    """
    package = normalize_component(component).split("/", 1)[0].lower()
    package_compact = re.sub(r"[^a-z0-9]+", "", package)
    tokens = identity_tokens(target)
    if not tokens:
        return False

    # Each meaningful word from a compound drawable must be represented by the
    # package. This handles e.g. proton-pass and stardew-valley while avoiding
    # loose one-word substring matches from the full component/activity string.
    return all(re.sub(r"[^a-z0-9]+", "", token) in package_compact for token in tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path, help="desktop Papirus checkout or Papirus/64x64/apps")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--android-src", type=Path, default=DEFAULT_ANDROID_SRC)
    parser.add_argument("--source", action="append", choices=[*SOURCES.keys(), "all"], default=[])
    parser.add_argument("--appfilter", action="append", default=[], metavar="URL_OR_FILE")
    parser.add_argument("--upstream-ref", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--list", action="store_true", help="print automatic and review candidates")
    args = parser.parse_args()

    apps_dir = desktop_apps_dir(args.desktop)
    desktop, collisions, aliases = build_desktop_index(apps_dir)
    policy = load_policy(args.policy)
    denied_targets = set(policy["deny"])
    max_components = policy["max_components"]

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
    exact_candidates: dict[str, tuple[Path, set[str]]] = {}
    skipped_existing = 0
    skipped_existing_mapping = 0

    for target in sorted(set(desktop) & set(external_components)):
        if target in existing_svgs or target in data:
            skipped_existing += 1
            continue

        components = {normalize_component(c) for c in external_components[target]}
        if not components:
            continue

        # A brand-new icon must not steal a component that Papirus already maps.
        if any(component in existing_targets for component in components):
            skipped_existing_mapping += 1
            continue

        exact_candidates[target] = (desktop[target], components)

    # Remove components if separate exact-name candidates disagree about where
    # they belong. This does not discard a whole icon when its other components
    # remain safe.
    component_candidates: dict[str, set[str]] = defaultdict(set)
    for target, (_, components) in exact_candidates.items():
        for component in components:
            component_candidates[component].add(target)
    ambiguous_components = {
        component for component, targets in component_candidates.items() if len(targets) > 1
    }

    automatic: dict[str, tuple[Path, list[str]]] = {}
    review: dict[str, tuple[Path, list[str], str]] = {}

    for target, (source, components) in exact_candidates.items():
        unambiguous = sorted(components - ambiguous_components)
        if not unambiguous:
            continue

        if target in denied_targets:
            review[target] = (source, unambiguous, "policy-deny")
            continue

        identity_components = [
            component for component in unambiguous if package_matches_target(target, component)
        ]
        if not identity_components:
            review[target] = (source, unambiguous, "no-package-identity")
            continue

        if len(identity_components) > max_components:
            review[target] = (
                source,
                identity_components,
                f"too-many-components>{max_components}",
            )
            continue

        automatic[target] = (source, sorted(identity_components))

    print(
        f"Desktop: {len(desktop)} canonical application SVGs, {aliases} aliases skipped, "
        f"{len(collisions)} normalized collisions skipped."
    )
    print(
        f"Android exact-name audit: {len(exact_candidates)} raw new icon candidates; "
        f"{len(automatic)} automatic; {len(review)} review; "
        f"{skipped_existing} already covered; {skipped_existing_mapping} overlap existing mappings; "
        f"{len(ambiguous_components)} ambiguous components removed."
    )

    if args.list or args.write:
        for target, (source, components) in sorted(automatic.items()):
            print(
                f"{'IMPORT' if args.write else 'AUTO'}: {source.name} -> {target}.svg "
                f"({len(components)} package-matched components; "
                f"sources={','.join(sorted(external_sources[target]))})"
            )
        if args.list:
            for target, (source, components, reason) in sorted(review.items()):
                print(
                    f"REVIEW: {source.name} -> {target}.svg "
                    f"({len(components)} components; reason={reason}; "
                    f"sources={','.join(sorted(external_sources[target]))})"
                )

    if not args.write:
        print("Dry-run only. Re-run with --write to import automatic candidates only.")
        return 0

    for target, (source, components) in automatic.items():
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
                "evidence": "desktop-exact-name+package-identity",
            }

    if automatic:
        manifest["upstream_ref"] = args.upstream_ref
        with args.db.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        with args.provenance.open("w", encoding="utf-8") as handle:
            json.dump(provenance, handle, indent=2, sort_keys=True)
            handle.write("\n")
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Imported {len(automatic)} automatically verified desktop Papirus icons.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
