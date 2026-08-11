#!/usr/bin/env python3
"""Audit a CandyBar Icon Request report against Papirus Android mappings.

The report format is the plain-text block produced by CandyBar's icon request
screen: an app label line, a package/activity component line, and optionally a
Play Store URL. Device/header metadata is ignored.

By default the audit is fully offline and checks data.json for exact component
coverage and same-package historical mappings. With --external it additionally
queries the Arcticons and Lawnicons appfilters to identify known app identities
without treating those identities as automatic Papirus artwork matches.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data.json"
COMPONENT_RE = re.compile(r"^([^\s/]+)/([^\s]+)$")
HEADER_PREFIXES = (
    "Manufacturer :",
    "Model :",
    "Product :",
    "Screen Resolution :",
    "Android Version :",
    "App Version :",
    "CandyBar Version :",
)


@dataclass(frozen=True)
class RequestedApp:
    label: str
    component: str

    @property
    def package(self) -> str:
        return self.component.split("/", 1)[0]


def normalize_component(value: str) -> str:
    value = value.strip()
    if value.startswith("ComponentInfo{") and value.endswith("}"):
        value = value[len("ComponentInfo{") : -1]
    return value


def parse_report(text: str) -> list[RequestedApp]:
    lines = [line.strip() for line in text.splitlines()]
    apps: list[RequestedApp] = []
    pending_label: str | None = None

    for line in lines:
        if not line:
            continue
        if line.startswith(HEADER_PREFIXES) or line.startswith(("http://", "https://")):
            continue
        component = normalize_component(line)
        if COMPONENT_RE.match(component):
            if pending_label is None:
                pending_label = component.split("/", 1)[0]
            apps.append(RequestedApp(pending_label, component))
            pending_label = None
            continue
        pending_label = line

    return apps


def load_database(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def build_indexes(data: dict[str, list[str]]):
    exact: dict[str, set[str]] = defaultdict(set)
    packages: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for drawable, components in data.items():
        if not isinstance(components, list):
            raise ValueError(f"{drawable!r} must map to a list")
        for raw in components:
            component = normalize_component(raw)
            exact[component].add(drawable)
            if "/" in component:
                packages[component.split("/", 1)[0]].append((drawable, component))
    return exact, packages


def load_external_identities(packages: set[str]):
    # Import the existing parser rather than duplicating source-format logic.
    from sync_external_mappings import SOURCES, parse_appfilter, read_source

    result: dict[str, dict[str, set[str]]] = {
        package: defaultdict(set) for package in packages
    }
    for source_name, source in SOURCES.items():
        groups = parse_appfilter(read_source(source))
        for drawable, components in groups.items():
            for component in components:
                package = component.split("/", 1)[0]
                if package in result:
                    result[package][source_name].add(drawable)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="CandyBar icon-request text file, or - for stdin")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--external", action="store_true", help="query Arcticons and Lawnicons identities")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    text = sys.stdin.read() if str(args.report) == "-" else args.report.read_text(encoding="utf-8")
    apps = parse_report(text)
    if not apps:
        print("No package/activity entries found in report.", file=sys.stderr)
        return 2

    data = load_database(args.db)
    exact, package_index = build_indexes(data)
    external = load_external_identities({app.package for app in apps}) if args.external else {}

    records = []
    counts = defaultdict(int)
    for app in apps:
        exact_targets = sorted(exact.get(app.component, ()))
        same_package = package_index.get(app.package, [])

        if exact_targets:
            status = "covered"
        elif same_package:
            status = "stale-activity"
        else:
            status = "missing-artwork-or-mapping"
        counts[status] += 1

        ext = {
            source: sorted(drawables)
            for source, drawables in external.get(app.package, {}).items()
        }
        records.append(
            {
                "label": app.label,
                "component": app.component,
                "package": app.package,
                "status": status,
                "papirus_drawables": exact_targets,
                "same_package_mappings": [
                    {"drawable": drawable, "component": component}
                    for drawable, component in same_package
                ],
                "external_identities": ext,
            }
        )

    if args.json:
        print(json.dumps({"counts": dict(counts), "apps": records}, indent=2, ensure_ascii=False))
        return 0

    for record in records:
        print(f"{record['label']}\n  {record['component']}\n  status: {record['status']}")
        if record["papirus_drawables"]:
            print("  mapped: " + ", ".join(record["papirus_drawables"]))
        if record["same_package_mappings"] and not record["papirus_drawables"]:
            drawables = sorted({item["drawable"] for item in record["same_package_mappings"]})
            print("  existing package artwork: " + ", ".join(drawables))
        if record["external_identities"]:
            formatted = []
            for source, drawables in sorted(record["external_identities"].items()):
                formatted.append(f"{source}={','.join(drawables)}")
            print("  external identity: " + "; ".join(formatted))
        print()

    print(
        "Summary: "
        + ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
