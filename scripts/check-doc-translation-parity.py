#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

LOCALES = ("es", "de", "fr", "it", "zh")
SECTIONS = ("getting-started", "user-guide", "admin-guide")
GRACE_SECONDS = 7 * 24 * 60 * 60


def english_sources(docs_dir: Path) -> list[Path]:
    files: list[Path] = []
    for section in SECTIONS:
        root = docs_dir / section
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            stem_parts = path.stem.split(".")
            if stem_parts[-1] in LOCALES:
                continue
            files.append(path)
    return sorted(files)


def localized_path(path: Path, locale: str) -> Path:
    return path.with_name(f"{path.stem}.{locale}{path.suffix}")


def last_commit_time(path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return int(value) if value.isdigit() else None


def heading_fingerprint(path: Path) -> list[str]:
    headings: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            marker, _, text = line.partition(" ")
            headings.append(f"{len(marker)}:{text.strip()}")
    return headings


def check(docs_dir: Path, now: int) -> int:
    failures: list[str] = []
    warnings: list[str] = []
    for source in english_sources(docs_dir):
        source_age_start = last_commit_time(source)
        in_grace = source_age_start is None or now - source_age_start < GRACE_SECONDS
        source_headings = heading_fingerprint(source)
        for locale in LOCALES:
            localized = localized_path(source, locale)
            if not localized.exists():
                message = f"missing {locale} translation for {source}"
                (warnings if in_grace else failures).append(message)
                continue
            if len(heading_fingerprint(localized)) != len(source_headings):
                failures.append(f"heading-count drift in {localized} compared with {source}")

    if warnings:
        print("Translation parity warnings within grace window:")
        for item in warnings:
            print(f"- {item}")
    if failures:
        print("Translation parity failures:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("No translation parity failures found.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check localized docs parity with English source pages.")
    parser.add_argument("docs_dir", nargs="?", type=Path, default=Path("docs"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return check(args.docs_dir, int(time.time()))


if __name__ == "__main__":
    raise SystemExit(main())
