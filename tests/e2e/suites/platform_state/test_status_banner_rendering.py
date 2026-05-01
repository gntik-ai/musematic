from __future__ import annotations

import pytest

from suites.ui_playwright import route_platform_shell_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("scheduled", "Scheduled maintenance"),
        ("started", "Maintenance in progress"),
        ("incident", "Active incident"),
    ],
)
async def test_authenticated_status_banner_state_machine(
    ui_page,
    platform_ui_url: str,
    state: str,
    expected: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_platform_shell_apis(ui_page, maintenance_state=state)

    await ui_page.goto(f"{platform_ui_url.rstrip('/')}/home/")

    await playwright_api.expect(
        ui_page.get_by_test_id("platform-status-banner"),
    ).to_be_visible()
    await playwright_api.expect(ui_page.get_by_text(expected).first).to_be_visible()
