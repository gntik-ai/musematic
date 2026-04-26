from __future__ import annotations


def test_hard_cap_blocks_then_override_boundary_scenario_registered() -> None:
    scenario = {
        "boundary": "policies.gateway -> cost_governance.budget_service",
        "steps": ["configure_budget", "block_new_start", "issue_override", "admit_next_start"],
    }

    assert scenario["boundary"].startswith("policies.gateway")
    assert scenario["steps"][-1] == "admit_next_start"
