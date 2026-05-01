from __future__ import annotations

import pytest

from journeys.helpers.narrative import journey_step
from suites.ui_playwright import (
    RUN_ID,
    route_simulation_apis,
    ui_page as ui_page,  # noqa: F401
)

JOURNEY_ID = "j07-ui"
TIMEOUT_SECONDS = 180


@pytest.mark.journey
@pytest.mark.j07_evaluator
@pytest.mark.j07_evaluator_ui
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j07_evaluator_scenario_workbench_loop(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    state = await route_simulation_apis(ui_page)

    with journey_step("Evaluator opens the scenario library"):
        await ui_page.goto(
            f"{platform_ui_url.rstrip('/')}/evaluation-testing/simulations/scenarios",
        )
        await playwright_api.expect(ui_page.get_by_text("Simulation scenarios")).to_be_visible()

    with journey_step("Evaluator creates and saves a reusable scenario"):
        await ui_page.get_by_role("button", name="New Scenario").click()
        await ui_page.get_by_label("Name").fill("Evaluator UI scenario")
        await ui_page.get_by_label("Description").fill("Created by J07 evaluator UI journey.")
        await ui_page.get_by_label("Agents").fill("ops:triage")
        await ui_page.get_by_role("button", name="Create Scenario").click()
        await ui_page.wait_for_url("**/evaluation-testing/simulations/scenarios/**")
        assert state["created"][0]["name"] == "Evaluator UI scenario"

    with journey_step("Evaluator launches two scenario iterations"):
        await ui_page.get_by_role("button", name="Launch").click()
        await ui_page.get_by_label("Iterations").fill("2")
        await ui_page.get_by_role("button", name="Queue Runs").click()
        await ui_page.wait_for_url(f"**/evaluation-testing/simulations/{RUN_ID}")
        assert state["runs"][0]["iterations"] == 2

    with journey_step("Evaluator inspects digital-twin divergence"):
        await playwright_api.expect(
            ui_page.get_by_text("Digital twin divergence"),
        ).to_be_visible()
        await playwright_api.expect(ui_page.get_by_text("Mock components")).to_be_visible()
        await playwright_api.expect(ui_page.get_by_text("Real components")).to_be_visible()
