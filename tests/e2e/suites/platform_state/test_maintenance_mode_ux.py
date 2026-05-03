from __future__ import annotations

import pytest

from suites.ui_playwright import assert_route_called, route_platform_shell_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_maintenance_write_attempt_opens_modal_without_503_page(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    calls = await route_platform_shell_apis(ui_page, maintenance_state="started")

    await ui_page.goto(f"{platform_ui_url.rstrip('/')}/operator?tab=maintenance")
    await ui_page.get_by_label("Starts at").fill("2099-05-01T10:00")
    await ui_page.get_by_label("Ends at").fill("2099-05-01T11:00")
    await ui_page.get_by_label("Reason").fill("Blocked write")
    await ui_page.get_by_label("Announcement").fill("Writes are paused for maintenance")
    await ui_page.get_by_role("button", name="Schedule").click()

    await playwright_api.expect(
        ui_page.get_by_text("Maintenance is in progress").first,
    ).to_be_visible()
    # Scope to <h1>: the operator UI's "remaining time" counter renders inside
    # a <p> and can contain the substring "503" (e.g. "38392503m remaining"),
    # which would false-positive a plain get_by_text("503") match. A genuine
    # HTTP 503 error page surfaces as an <h1> heading with the status code.
    await playwright_api.expect(
        ui_page.locator("h1").filter(has_text="503").first,
    ).not_to_be_visible()
    await assert_route_called(calls, "write_attempts")
