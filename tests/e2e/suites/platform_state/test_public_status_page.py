from __future__ import annotations

import pytest

from suites.ui_playwright import (
    assert_no_serious_axe_violations,
    route_status_app_apis,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_public_status_pages_render_and_pass_serious_axe(
    ui_page,
    platform_status_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_status_app_apis(ui_page)

    for path, expected_text in [
        ("/", "Elevated API latency"),
        ("/components/control-plane-api/", "Control Plane API"),
        ("/history/", "Webhook delivery delay"),
    ]:
        await ui_page.goto(f"{platform_status_url.rstrip('/')}{path}")
        await playwright_api.expect(
            ui_page.get_by_text(expected_text).first,
        ).to_be_visible()
        await assert_no_serious_axe_violations(ui_page)
