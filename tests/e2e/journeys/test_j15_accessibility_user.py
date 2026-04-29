from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j15_accessibility_user]


ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST = ROOT / "tests/e2e/journeys/fixtures/axe_allowlist.json"


def test_j15_keyboard_only_accessibility_contract() -> None:
    pages = [
        "login",
        "marketplace",
        "agent_detail",
        "conversation",
        "execution",
        "reasoning_trace",
        "logout",
    ]
    assertions = [
        "axe_zero_aa_violations",
        "tab_order_reaches_all_interactive_elements",
        "focus_indicator_visible",
        "aria_status_announces_async_progress",
        "command_palette_keyboard_usable",
        "contrast_ratio_aa",
    ]

    assert len(pages) >= 7
    assert "axe_zero_aa_violations" in assertions
    assert "command_palette_keyboard_usable" in assertions


def test_j15_axe_allowlist_is_empty_or_unexpired() -> None:
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    max_expiry = now + timedelta(days=90)
    entries = [
        item
        for page_entries in payload.get("pages", {}).values()
        for item in page_entries
    ]

    for entry in entries:
        expires = datetime.fromisoformat(entry["expiry_date"].replace("Z", "+00:00"))
        assert now <= expires <= max_expiry
        assert entry["justification"]
        assert entry["tracking_id"]


def test_j15_frontend_source_maps_are_enabled_for_logged_errors() -> None:
    next_config = (ROOT / "apps/web/next.config.mjs").read_text(encoding="utf-8")

    assert "productionBrowserSourceMaps: true" in next_config


def test_j15_ci_gate_runs_journeys_with_html_report() -> None:
    workflow = (ROOT / ".github/workflows/e2e.yml").read_text(encoding="utf-8")

    assert "make e2e-journeys" in workflow
    assert "journeys-report.html" in (ROOT / "tests/e2e/Makefile").read_text(encoding="utf-8")
