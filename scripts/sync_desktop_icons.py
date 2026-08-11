#!/usr/bin/env python3
"""Synchronize application artwork from the desktop Papirus theme.

Android-specific artwork always wins. The script only updates files that it
previously imported and tracks those files in ``desktop-sync.json``.

Typical usage from the Android repository root::

    python3 scripts/sync_desktop_icons.py ../papirus-icon-theme

The argument may point either at the desktop repository root or directly at
``Papirus/64x64/apps``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

DEFAULT_MANIFEST = Path("desktop-sync.json")
DEFAULT_ANDROID_SRC = Path("src")
DESKTOP_APPS = Path("Papirus/64x64/apps")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_name(filename: str) -> str:
    """Convert a desktop icon filename into a valid Android drawable name."""
    stem = Path(filename).stem
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    stem = stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    if not stem:
        raise ValueError(f"cannot derive Android resource name from {filename!r}")

    # The Android drawable itself starts with the safe ``apps_`` prefix, so a
    # desktop filename such as ``1password.svg`` should become
    # ``apps_1password`` rather than the incorrect ``apps__1password``.
    return "apps_" + stem


def desktop_apps_dir(root: Path) -> Path:
    direct = root.resolve()
    nested = direct / DESKTOP_APPS
    if nested.is_dir():
        return nested
    if direct.is_dir() and direct.name == "apps":
        return direct
    raise FileNotFoundError(
        f"{root} is neither a Papirus desktop checkout nor a Papirus/64x64/apps directory"
    )


def alias_target(path: Path) -> str | None:
    """Return an SVG alias target for symlinks and git-exported symlink stubs."""
    if path.is_symlink():
        return os.readlink(path)

    # GitHub/archive exports can occasionally expose a symlink as a tiny text file.
    if path.stat().st_size > 256:
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return None
    if text.endswith(".svg") and "<svg" not in text:
        return text
    return None


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "upstream": "PapirusDevelopmentTeam/papirus-icon-theme", "icons": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("icons"), dict):
        raise ValueError(f"unsupported manifest format in {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path, help="desktop Papirus checkout or Papirus/64x64/apps")
    parser.add_argument("--android-src", type=Path, default=DEFAULT_ANDROID_SRC)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--upstream-ref", default="", help="optional desktop commit/tag recorded in the manifest")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 when a sync would change files",
    )
    args = parser.parse_args()

    apps_dir = desktop_apps_dir(args.desktop)
    android_src = args.android_src.resolve()
    android_src.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    managed: dict[str, dict] = manifest["icons"]

    changed = 0
    imported = 0
    updated = 0
    protected = 0
    aliases = 0
    collisions = 0
    seen_destinations: dict[str, str] = {}

    for source in sorted(apps_dir.glob("*.svg"), key=lambda p: p.name.lower()):
        alias = alias_target(source)
        if alias is not None:
            aliases += 1
            continue

        try:
            dest_name = resource_name(source.name) + ".svg"
        except ValueError as exc:
            print(f"SKIP: {exc}")
            continue

        previous_source = seen_destinations.get(dest_name)
        if previous_source and previous_source != source.name:
            print(f"COLLISION: {source.name} and {previous_source} -> {dest_name}")
            collisions += 1
            continue
        seen_destinations[dest_name] = source.name

        destination = android_src / dest_name
        digest = sha256(source)
        entry = managed.get(dest_name)

        if destination.exists() and entry is None:
            # Existing Android artwork may be intentionally redrawn for a launcher.
            protected += 1
            continue

        needs_write = not destination.exists() or entry is None or entry.get("sha256") != digest
        if not needs_write:
            continue

        changed += 1
        action = "UPDATE" if destination.exists() else "IMPORT"
        print(f"{action}: {source.name} -> {destination.relative_to(Path.cwd()) if destination.is_relative_to(Path.cwd()) else destination}")

        if not (args.dry_run or args.check):
            shutil.copyfile(source, destination)
            managed[dest_name] = {
                "source": source.name,
                "sha256": digest,
            }

        if action == "IMPORT":
            imported += 1
        else:
            updated += 1

    if collisions:
        print(f"ERROR: {collisions} normalized filename collision(s) need review", file=sys.stderr)
        return 2

    if changed and not (args.dry_run or args.check):
        manifest["upstream_ref"] = args.upstream_ref
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"Desktop Papirus sync: {imported} import(s), {updated} update(s), "
        f"{protected} Android-specific icon(s) protected, {aliases} alias(es) skipped."
    )

    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
