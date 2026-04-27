#!/usr/bin/env python3
"""Validate structural parity across multilingual README variants."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable


LOCALES = ["", ".es", ".it", ".de", ".fr", ".zh"]
GRACE_WINDOW = timedelta(days=7)
LANGUAGE_BAR_RE = re.compile(
    r"^> \*\*Read this in other languages\*\*: "
    r"\[English\]\(\./README\.md\) · "
    r"\[Español\]\(\./README\.es\.md\) · "
    r"\[Italiano\]\(\./README\.it\.md\) · "
    r"\[Deutsch\]\(\./README\.de\.md\) · "
    r"\[Français\]\(\./README\.fr\.md\) · "
    r"\[简体中文\]\(\./README\.zh\.md\)$",
    re.MULTILINE,
)

BADGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+]\(([^)]+)\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def readme_path(repo_root: Path, locale: str) -> Path:
    if locale == "":
        return repo_root / "README.md"
    return repo_root / f"README{locale}.md"


def _content_without_fenced_blocks(content: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in content.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def extract_headings(content: str, max_level: int = 3) -> list[tuple[int, str]]:
    """Return ATX H1-H3 headings outside fenced code blocks."""
    body = _content_without_fenced_blocks(content)
    heading_re = re.compile(rf"^(#{{1,{max_level}}})\s+(.+?)\s*#*\s*$", re.MULTILINE)
    headings: list[tuple[int, str]] = []
    for match in heading_re.finditer(body):
        text = match.group(2).strip()
        headings.append((len(match.group(1)), text))
    return headings


def count_badges(content: str) -> int:
    return len(BADGE_RE.findall(content))


def count_links(content: str) -> int:
    content_without_badges = BADGE_RE.sub("", content)
    return len(LINK_RE.findall(content_without_badges))


def extract_links(content: str) -> list[str]:
    content_without_badges = BADGE_RE.sub("", content)
    return [target.strip() for target in LINK_RE.findall(content_without_badges)]


def extract_language_bar(content: str) -> str | None:
    match = LANGUAGE_BAR_RE.search(content)
    if not match:
        return None
    return match.group(0)


def _has_unclosed_fence(content: str) -> bool:
    in_fence = False
    for line in content.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
    return in_fence


def validate_pandoc(file: Path) -> bool:
    """Validate Markdown with pandoc when available."""
    try:
        content = file.read_text(encoding="utf-8")
    except OSError:
        return False
    if _has_unclosed_fence(content):
        return False

    try:
        result = subprocess.run(
            ["pandoc", "-f", "gfm", "-t", "html", str(file)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _github_env() -> dict[str, str] | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return None
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    return env


def _run_gh_json(args: list[str]) -> object | None:
    env = _github_env()
    if env is None:
        return None
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return None


def _parse_github_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _effective_grace_window() -> timedelta:
    override = os.environ.get("MUSEMATIC_README_GRACE_OVERRIDE_SECONDS")
    if not override:
        return GRACE_WINDOW
    try:
        seconds = int(override)
    except ValueError:
        return GRACE_WINDOW
    return timedelta(seconds=max(seconds, 0))


def check_grace_window(issue_number: int) -> bool:
    """Return True while the drift tracking issue is still inside grace."""
    if issue_number <= 0:
        return True
    payload = _run_gh_json(["issue", "view", str(issue_number), "--json", "createdAt"])
    if not isinstance(payload, dict):
        return True
    created_at_raw = payload.get("createdAt")
    if not isinstance(created_at_raw, str):
        return True
    created_at = _parse_github_timestamp(created_at_raw)
    if created_at is None:
        return True
    now = datetime.now(UTC)
    return now - created_at <= _effective_grace_window()


def has_exempt_label(pr_number: int) -> bool:
    if pr_number <= 0:
        return False
    payload = _run_gh_json(["pr", "view", str(pr_number), "--json", "labels"])
    if not isinstance(payload, dict):
        return False
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return False
    return any(isinstance(label, dict) and label.get("name") == "docs-translation-exempt" for label in labels)


def find_open_drift_issue() -> int | None:
    payload = _run_gh_json(
        [
            "issue",
            "list",
            "--label",
            "readme-translation-drift",
            "--state",
            "open",
            "--json",
            "number,createdAt",
            "--limit",
            "20",
        ]
    )
    if not isinstance(payload, list) or not payload:
        return None
    candidates: list[tuple[datetime, int]] = []
    for issue in payload:
        if not isinstance(issue, dict):
            continue
        number = issue.get("number")
        created_at_raw = issue.get("createdAt")
        if not isinstance(number, int) or not isinstance(created_at_raw, str):
            continue
        created_at = _parse_github_timestamp(created_at_raw)
        if created_at is not None:
            candidates.append((created_at, number))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _heading_levels(headings: Iterable[tuple[int, str]]) -> list[int]:
    return [level for level, _text in headings]


def _format_heading_levels(levels: Iterable[int]) -> str:
    return ", ".join(f"H{level}" for level in levels)


def find_missing_local_links(repo_root: Path, file: Path, content: str) -> list[str]:
    warnings: list[str] = []
    for raw_target in extract_links(content):
        target = raw_target.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (file.parent / target).resolve()
        try:
            path.relative_to(repo_root.resolve())
        except ValueError:
            warnings.append(f"{file.name}: local link escapes repository: {raw_target}")
            continue
        if not path.exists():
            warnings.append(f"{file.name}: local link target missing: {raw_target}")
    return warnings


def _compare_variant(
    *,
    repo_root: Path,
    locale: str,
    baseline_headings: list[tuple[int, str]],
    baseline_badges: int,
    baseline_links: int,
    baseline_language_bar: str | None,
) -> tuple[list[str], list[str], list[str]]:
    file = readme_path(repo_root, locale)
    drift: list[str] = []
    hard_failures: list[str] = []
    warnings: list[str] = []

    if not file.exists():
        hard_failures.append(f"{file.name}: required README variant is missing")
        return drift, hard_failures, warnings

    content = file.read_text(encoding="utf-8")
    if not validate_pandoc(file):
        hard_failures.append(f"{file.name}: pandoc validation failed")

    headings = extract_headings(content)
    expected_levels = _heading_levels(baseline_headings)
    actual_levels = _heading_levels(headings)
    if actual_levels != expected_levels:
        drift.append(
            f"{file.name}: heading-structure mismatch "
            f"(expected {_format_heading_levels(expected_levels)}; got {_format_heading_levels(actual_levels)})"
        )

    badges = count_badges(content)
    if badges != baseline_badges:
        drift.append(f"{file.name}: badge count mismatch (expected {baseline_badges}; got {badges})")

    links = count_links(content)
    if links != baseline_links:
        drift.append(f"{file.name}: link count mismatch (expected {baseline_links}; got {links})")

    language_bar = extract_language_bar(content)
    if language_bar != baseline_language_bar:
        drift.append(f"{file.name}: language-switcher-bar byte-mismatch")

    warnings.extend(find_missing_local_links(repo_root, file, content))
    return drift, hard_failures, warnings


def _print_lines(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(title)
    for line in lines:
        print(f"- {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check multilingual README structural parity.")
    parser.add_argument("--pr-number", type=int, default=0, help="GitHub PR number for label lookup.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root path.")
    parser.add_argument("--drift-issue", type=int, default=0, help="Existing README drift tracking issue number.")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    canonical = readme_path(repo_root, "")
    hard_failures: list[str] = []
    warnings: list[str] = []

    if not canonical.exists():
        print("README parity hard failures:")
        print("- README.md: canonical English README is missing")
        return 2

    canonical_content = canonical.read_text(encoding="utf-8")
    if not validate_pandoc(canonical):
        hard_failures.append("README.md: pandoc validation failed")

    baseline_headings = extract_headings(canonical_content)
    baseline_badges = count_badges(canonical_content)
    baseline_links = count_links(canonical_content)
    baseline_language_bar = extract_language_bar(canonical_content)
    if baseline_language_bar is None:
        hard_failures.append("README.md: language switcher bar is missing or malformed")

    drift: list[str] = []
    warnings.extend(find_missing_local_links(repo_root, canonical, canonical_content))

    for locale in LOCALES[1:]:
        variant_drift, variant_hard_failures, variant_warnings = _compare_variant(
            repo_root=repo_root,
            locale=locale,
            baseline_headings=baseline_headings,
            baseline_badges=baseline_badges,
            baseline_links=baseline_links,
            baseline_language_bar=baseline_language_bar,
        )
        drift.extend(variant_drift)
        hard_failures.extend(variant_hard_failures)
        warnings.extend(variant_warnings)

    _print_lines("README parity warnings:", warnings)

    if hard_failures:
        _print_lines("README parity hard failures:", hard_failures)
        return 2

    if not drift:
        print("README parity check passed.")
        return 0

    _print_lines("README translation drift detected:", drift)

    if has_exempt_label(args.pr_number):
        print("docs-translation-exempt label is present; drift remains a warning and requires 30-day backfill.")
        return 1

    drift_issue = args.drift_issue or find_open_drift_issue() or 0
    if drift_issue and not check_grace_window(drift_issue):
        print(f"README drift grace window expired for issue #{drift_issue}.")
        return 2

    if drift_issue:
        print(f"README drift is inside the grace window tracked by issue #{drift_issue}.")
    else:
        print("README drift is fresh; create or update a tracking issue to start the 7-day grace window.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
