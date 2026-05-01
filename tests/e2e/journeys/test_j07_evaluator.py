from __future__ import annotations

from typing import Any

import pytest

from journeys.helpers.narrative import journey_step
from suites.ui_playwright import (
    RUN_ID,
    route_simulation_apis,
    ui_page as ui_page,  # noqa: F401
)

# Cross-context inventory:
# - evaluation
# - execution
# - runtime
# - workflows
# - workspaces

JOURNEY_ID = "j07"
TIMEOUT_SECONDS = 180


def assert_scenario_created(state: dict[str, list[dict[str, Any]]]) -> None:
    assert len(state["created"]) == 1
    assert state["created"][0]["name"] == "Evaluator UI scenario"
    assert state["created"][0]["agents_config"]["agents"] == ["ops:triage"]


def assert_run_batch_queued(state: dict[str, list[dict[str, Any]]]) -> None:
    assert len(state["runs"]) == 1
    assert state["runs"][0]["iterations"] == 2
    assert RUN_ID in state["runs"][0]["queued"]


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

    with journey_step("Evaluator opens the evaluation workbench"):
        await ui_page.goto(
            f"{platform_ui_url.rstrip('/')}/evaluation-testing/simulations/scenarios",
        )

    with journey_step("Evaluator verifies the scenario library loaded"):
        await playwright_api.expect(ui_page.get_by_text("Simulation scenarios")).to_be_visible()

    with journey_step("Evaluator opens the reusable scenario form"):
        await ui_page.get_by_role("button", name="New Scenario").click()

    with journey_step("Evaluator captures the scenario identity"):
        await ui_page.get_by_label("Name").fill("Evaluator UI scenario")
        await ui_page.get_by_label("Description").fill("Created by J07 evaluator UI journey.")

    with journey_step("Evaluator binds the scenario to an agent roster"):
        await ui_page.get_by_label("Agents").fill("ops:triage")

    with journey_step("Evaluator saves the reusable scenario"):
        await ui_page.get_by_role("button", name="Create Scenario").click()
        await ui_page.wait_for_url("**/evaluation-testing/simulations/scenarios/**")
        assert_scenario_created(state)

    with journey_step("Evaluator opens the launch controls"):
        await ui_page.get_by_role("button", name="Launch").click()

    with journey_step("Evaluator configures two scenario iterations"):
        await ui_page.get_by_label("Iterations").fill("2")

    with journey_step("Evaluator queues the run batch"):
        await ui_page.get_by_role("button", name="Queue Runs").click()
        await ui_page.wait_for_url(f"**/evaluation-testing/simulations/{RUN_ID}")
        assert_run_batch_queued(state)

    with journey_step("Evaluator inspects digital-twin divergence"):
        await playwright_api.expect(
            ui_page.get_by_text("Digital twin divergence"),
        ).to_be_visible()
        await playwright_api.expect(ui_page.get_by_text("Mock components")).to_be_visible()
        await playwright_api.expect(ui_page.get_by_text("Real components")).to_be_visible()
