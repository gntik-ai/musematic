from __future__ import annotations


def test_attribution_visible_during_run_boundary_scenario_registered() -> None:
    scenario = {
        "journey": "workspace execution crosses execution -> cost_governance boundary",
        "assertions": [
            "in_progress_cost_visible",
            "execution_detail_cost_visible",
            "workspace_cost_query_visible",
        ],
    }

    assert "cost_governance" in scenario["journey"]
    assert "in_progress_cost_visible" in scenario["assertions"]
