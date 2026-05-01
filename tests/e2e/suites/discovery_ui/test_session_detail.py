from __future__ import annotations

import pytest

from suites.ui_playwright import DISCOVERY_SESSION_ID, route_discovery_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_discovery_session_tabs_and_network_deep_link(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_discovery_apis(ui_page)

    await ui_page.goto(f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}")
    for tab in ["Overview", "Hypotheses", "Experiments", "Evidence", "Network"]:
        await playwright_api.expect(ui_page.get_by_role("link", name=tab)).to_be_visible()

    await ui_page.get_by_role("link", name="Network").click()
    await playwright_api.expect(
        ui_page.get_by_text("Scientific discovery network"),
    ).to_be_visible()
