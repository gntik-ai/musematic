from __future__ import annotations

import pytest

from suites.ui_playwright import route_simulation_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_scenario_editor_validation_and_real_llm_confirmation(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_simulation_apis(ui_page)

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/evaluation-testing/simulations/scenarios/new",
    )
    await ui_page.get_by_label("Name").fill("Plaintext secret guard")
    await ui_page.get_by_label("Agents").fill("ops:triage")
    await ui_page.get_by_label("Mock set").fill('{"api_key":"plaintext_secret_123456"}')
    await ui_page.get_by_role("button", name="Create Scenario").click()

    await playwright_api.expect(
        ui_page.get_by_text("Plaintext secrets are not allowed").first,
    ).to_be_visible()

    await ui_page.get_by_role("button", name="Real LLM Preview").click()
    await playwright_api.expect(
        ui_page.get_by_text("Confirm Real LLM Preview"),
    ).to_be_visible()
    await playwright_api.expect(
        ui_page.get_by_role("button", name="Confirm"),
    ).to_be_disabled()
    await ui_page.get_by_placeholder("USE_REAL_LLM").fill("USE_REAL_LLM")
    await playwright_api.expect(
        ui_page.get_by_role("button", name="Confirm"),
    ).to_be_enabled()
