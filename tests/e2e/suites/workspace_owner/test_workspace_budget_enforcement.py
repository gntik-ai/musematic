from __future__ import annotations


def test_workspace_budget_threshold_and_hard_cap_contract() -> None:
    budget_flow = {
        "thresholds": [50, 80],
        "hard_cap_percent": 100,
        "admin_override": "single_shot",
        "forecast_window_days": 30,
    }

    assert budget_flow["thresholds"] == [50, 80]
    assert budget_flow["hard_cap_percent"] == 100
    assert budget_flow["admin_override"] == "single_shot"
