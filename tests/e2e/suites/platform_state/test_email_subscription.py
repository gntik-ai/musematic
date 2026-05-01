from __future__ import annotations

import pytest

from suites.ui_playwright import route_status_app_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_email_subscription_confirm_and_unsubscribe_pages(
    ui_page,
    platform_status_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_status_app_apis(ui_page)

    await ui_page.goto(f"{platform_status_url.rstrip('/')}/subscribe/")
    await ui_page.get_by_label("Email").fill("status-subscriber@example.com")
    await ui_page.get_by_label("Component scope").fill("control-plane-api")
    await ui_page.get_by_role("button", name="Subscribe").click()
    await playwright_api.expect(
        ui_page.get_by_text("confirmation link has been sent").first,
    ).to_be_visible()

    await ui_page.goto(f"{platform_status_url.rstrip('/')}/subscribe/confirm?token=test-token")
    await playwright_api.expect(ui_page.get_by_text("Request completed.")).to_be_visible()

    await ui_page.goto(f"{platform_status_url.rstrip('/')}/unsubscribe?token=test-token")
    await playwright_api.expect(ui_page.get_by_text("Request completed.")).to_be_visible()
