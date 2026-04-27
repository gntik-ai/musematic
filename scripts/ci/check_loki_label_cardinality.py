#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = {
    "workspace_id",
    "user_id",
    "goal_id",
    "correlation_id",
    "trace_id",
    "execution_id",
}


def main() -> int:
    values_path = Path("deploy/helm/observability/values.yaml")
    text = values_path.read_text(encoding="utf-8")
    labels_blocks = _extract_labels_blocks(text)
    violations: set[str] = set()
    for block in labels_blocks:
        for label in FORBIDDEN:
            if re.search(rf"^\s*{re.escape(label)}\s*:", block, re.MULTILINE):
                violations.add(label)
    if violations:
        joined = ", ".join(sorted(violations))
        print(
            f"{values_path}: forbidden high-cardinality Loki labels promoted: {joined}",
            file=sys.stderr,
        )
        return 1
    return 0


def _extract_labels_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if not re.match(r"^\s*-\s+labels:\s*$", line):
            continue
        base_indent = len(line) - len(line.lstrip())
        block_lines = [line]
        for next_line in lines[index + 1 :]:
            indent = len(next_line) - len(next_line.lstrip())
            if next_line.strip().startswith("- ") and indent <= base_indent:
                break
            block_lines.append(next_line)
        blocks.append("\n".join(block_lines))
    return blocks


if __name__ == "__main__":
    raise SystemExit(main())
