#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FR_RE = re.compile(r"\bFR-\d{3}\b")
FR_HEADING_RE = re.compile(r"^###\s+(FR-\d{3})\b", re.MULTILINE)


def load_fr_numbers(fr_doc: Path) -> set[str]:
    if not fr_doc.exists():
        raise ValueError(f"FR document not found: {fr_doc}")
    text = fr_doc.read_text(encoding="utf-8")
    numbers = set(FR_HEADING_RE.findall(text))
    if not numbers:
        raise ValueError(f"FR document is unparseable: {fr_doc}")
    return numbers


def scan_doc_references(docs_root: Path, fr_doc: Path) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for path in sorted(docs_root.rglob("*.md")):
        if path.resolve() == fr_doc.resolve():
            continue
        text = path.read_text(encoding="utf-8")
        found = set(FR_RE.findall(text))
        if found:
            refs[path.as_posix()] = found
    return refs


def check_references(docs_root: Path, fr_doc: Path) -> tuple[int, str]:
    try:
        known = load_fr_numbers(fr_doc)
    except ValueError as exc:
        return 2, f"{exc}\n"

    refs_by_file = scan_doc_references(docs_root, fr_doc)
    referenced = set().union(*refs_by_file.values()) if refs_by_file else set()
    broken: list[tuple[str, str]] = []
    for path, refs in refs_by_file.items():
        for ref in sorted(refs - known):
            broken.append((path, ref))

    lines: list[str] = []
    if broken:
        lines.append("Broken FR references found:")
        for path, ref in broken:
            lines.append(f"- {path}: {ref}")
    else:
        lines.append("No broken FR references found.")

    uncovered = sorted(known - referenced)
    if uncovered:
        sample = ", ".join(uncovered[:25])
        suffix = f" (+{len(uncovered) - 25} more)" if len(uncovered) > 25 else ""
        lines.append(f"Informational: {len(uncovered)} FRs have no docs coverage yet: {sample}{suffix}")

    return (1 if broken else 0), "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate FR references in documentation.")
    parser.add_argument("docs_root", nargs="?", type=Path, default=Path("docs"))
    parser.add_argument(
        "--fr-doc",
        type=Path,
        default=Path("docs/functional-requirements-revised-v6.md"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status, output = check_references(args.docs_root, args.fr_doc)
    stream = sys.stderr if status else sys.stdout
    stream.write(output)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
