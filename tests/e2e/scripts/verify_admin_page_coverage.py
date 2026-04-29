#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROUTE_RE = re.compile(r"^\| (`/admin[^`]+`) \|")


def inventory_routes(inventory: Path) -> list[str]:
    routes: list[str] = []
    for line in inventory.read_text().splitlines():
        match = ROUTE_RE.match(line)
        if match is None:
            continue
        route = match.group(1).strip("`")
        routes.append(route.replace("[id]", "id").replace("[connector_id]", "connector_id"))
    return routes


def assertion_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists():
            chunks.append(path.read_text())
    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory",
        default="specs/086-administrator-workbench-and/contracts/admin-page-inventory.md",
    )
    parser.add_argument(
        "--journey",
        action="append",
        default=[
            "tests/e2e/journeys/test_j01_admin_bootstrap.py",
            "tests/e2e/journeys/test_j18_super_admin_lifecycle.py",
        ],
    )
    parser.add_argument("--suite-dir", default="tests/e2e/suites/admin")
    args = parser.parse_args()

    root = Path.cwd()
    routes = inventory_routes(root / args.inventory)
    suite_paths = sorted((root / args.suite_dir).glob("test_*.py"))
    text = assertion_text([root / item for item in args.journey] + suite_paths)
    missing = [route for route in routes if route not in text]

    if missing:
        print("Admin page coverage is missing assertions for:", file=sys.stderr)
        for route in missing:
            print(f"  - {route}", file=sys.stderr)
        return 1

    print(f"Verified admin page coverage for {len(routes)} routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
