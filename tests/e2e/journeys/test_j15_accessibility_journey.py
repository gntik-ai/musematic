from __future__ import annotations

from pathlib import Path


def test_j15_accessibility_journey_artifacts_are_wired() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    assert (repo_root / "apps" / "web" / "tests" / "a11y" / "playwright.a11y.config.ts").is_file()
    assert (repo_root / "apps" / "web" / "components" / "layout" / "command-palette" / "HelpOverlay.tsx").is_file()
    assert (repo_root / "apps" / "web" / "components" / "layout" / "desktop-best-hint" / "DesktopBestHint.tsx").is_file()
