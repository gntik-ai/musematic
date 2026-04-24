from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize govulncheck JSONL output.")
    parser.add_argument("input", type=Path, help="Raw govulncheck -json output")
    parser.add_argument("--output", type=Path, default=Path("scan-results/govulncheck.json"))
    parser.add_argument("--invalid-output", type=Path, default=None)
    return parser


def normalize_jsonl(path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    vulns: list[dict[str, Any]] = []
    invalid_lines: list[str] = []

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            invalid_lines.append(f"{line_number}: {stripped}")
            continue
        if not isinstance(item, dict):
            continue

        vuln = item.get("finding") or item.get("osv")
        if isinstance(vuln, dict):
            vulns.append(_normalize_vuln(vuln))

    return {"vulns": vulns}, invalid_lines


def _normalize_vuln(vuln: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(vuln)
    osv_id = normalized.get("osv")
    if "id" not in normalized and isinstance(osv_id, str):
        normalized["id"] = osv_id
    return normalized


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, invalid_lines = normalize_jsonl(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    if args.invalid_output is not None:
        args.invalid_output.parent.mkdir(parents=True, exist_ok=True)
        args.invalid_output.write_text(
            "\n".join(invalid_lines) + ("\n" if invalid_lines else ""),
            encoding="utf-8",
        )
    if invalid_lines:
        print(
            f"warning: skipped {len(invalid_lines)} non-JSON govulncheck output lines",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
