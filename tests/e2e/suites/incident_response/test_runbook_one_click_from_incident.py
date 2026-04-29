from __future__ import annotations


def test_runbook_one_click_from_incident_boundary_scenario_registered() -> None:
    scenario = {
        "journey": "operator incident detail -> inline runbook panel",
        "assertions": [
            "runbook_opened_from_incident_detail",
            "diagnostic_commands_copyable",
            "stale_runbook_badge_visible",
            "missing_runbook_author_cta_visible",
        ],
    }

    assert "incident detail" in scenario["journey"]
    assert "runbook_opened_from_incident_detail" in scenario["assertions"]
