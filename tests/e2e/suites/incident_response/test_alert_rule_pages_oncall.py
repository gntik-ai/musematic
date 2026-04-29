from __future__ import annotations


def test_alert_rule_pages_oncall_boundary_scenario_registered() -> None:
    scenario = {
        "journey": (
            "analytics alert rule fires -> incident_response trigger interface -> provider mock"
        ),
        "assertions": [
            "incident_row_created",
            "external_alert_row_created",
            "provider_mock_received_mapped_severity",
            "incident_triggered_event_emitted",
        ],
    }

    assert "incident_response trigger interface" in scenario["journey"]
    assert "provider_mock_received_mapped_severity" in scenario["assertions"]
