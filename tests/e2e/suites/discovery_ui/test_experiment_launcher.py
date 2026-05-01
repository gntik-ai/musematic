from __future__ import annotations

import pytest

from suites.ui_playwright import (
    DISCOVERY_SESSION_ID,
    EXPERIMENT_ID,
    HYPOTHESIS_ID,
    route_discovery_apis,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_experiment_launcher_posts_and_shows_returned_experiment(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    state = await route_discovery_apis(ui_page)

    await ui_page.goto(
        f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/experiments/new"
        f"?hypothesis={HYPOTHESIS_ID}",
    )
    await ui_page.get_by_label("Experiment notes").fill("Validate alpha catalyst.")
    await ui_page.get_by_role("button", name="Launch Experiment").click()

    await playwright_api.expect(ui_page.get_by_text(EXPERIMENT_ID)).to_be_visible()
    assert state["experiments"][0]["experiment_id"] == EXPERIMENT_ID
    assert state["experiments"][0]["execution_status"] == "running"
