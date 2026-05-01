from __future__ import annotations

import pytest

from suites.ui_playwright import DISCOVERY_SESSION_ID, HYPOTHESIS_ID, route_discovery_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_evidence_inspector_source_links_and_deleted_source_state(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_discovery_apis(ui_page)

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/evidence/{HYPOTHESIS_ID}",
    )
    await playwright_api.expect(ui_page.get_by_text("Aggregated evidence")).to_be_visible()
    source = ui_page.get_by_role("link", name="Source hypothesis").first
    await playwright_api.expect(source).to_be_visible()
    await source.click()
    assert f"/discovery/{HYPOTHESIS_ID}/hypotheses" in ui_page.url

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/evidence/missing-source",
    )
    await playwright_api.expect(
        ui_page.get_by_text("Source unavailable").first,
    ).to_be_visible()
