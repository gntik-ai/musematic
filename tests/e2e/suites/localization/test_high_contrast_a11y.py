from __future__ import annotations

from pathlib import Path


def test_high_contrast_theme_tokens_are_committed() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    globals_css = (repo_root / "apps" / "web" / "app" / "globals.css").read_text(
        encoding="utf-8",
    )

    assert ".high_contrast" in globals_css
    assert "--severity-critical" in globals_css
    assert "--chart-1" in globals_css
