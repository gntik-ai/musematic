from __future__ import annotations

import pytest

from suites.ui_playwright import DISCOVERY_SESSION_ID, route_discovery_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_hypothesis_library_filter_sort_and_empty_state(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_discovery_apis(ui_page)

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/hypotheses",
    )
    await playwright_api.expect(
        ui_page.get_by_text("Catalyst alpha improves yield"),
    ).to_be_visible()

    await ui_page.get_by_label("Confidence").select_option("low")
    await playwright_api.expect(
        ui_page.get_by_text("Control catalyst is stable"),
    ).to_be_visible()
    await ui_page.get_by_label("Sort").select_option("created_at")

    await ui_page.get_by_label("State").select_option("merged")
    await playwright_api.expect(ui_page.get_by_text("No hypotheses")).to_be_visible()
