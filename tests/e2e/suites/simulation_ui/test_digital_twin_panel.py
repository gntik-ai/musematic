from __future__ import annotations

import pytest

from suites.ui_playwright import REPORT_ID, RUN_ID, route_simulation_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_digital_twin_panel_renders_divergence_and_empty_reference_state(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_simulation_apis(ui_page)

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/evaluation-testing/simulations/{RUN_ID}?report={REPORT_ID}",
    )
    await playwright_api.expect(
        ui_page.get_by_text("Digital twin divergence"),
    ).to_be_visible()
    await playwright_api.expect(ui_page.get_by_text("Mock components")).to_be_visible()
    await playwright_api.expect(ui_page.get_by_text("Real components")).to_be_visible()
    await playwright_api.expect(ui_page.get_by_text("latency_ms")).to_be_visible()
    await playwright_api.expect(ui_page.get_by_text("Reference prod-exec-1")).to_be_visible()

    await ui_page.goto(f"{platform_ui_url.rstrip('/')}/evaluation-testing/simulations/{RUN_ID}")
    await playwright_api.expect(ui_page.get_by_text("No reference available.")).to_be_visible()
