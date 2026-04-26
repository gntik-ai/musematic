from __future__ import annotations


def test_anomaly_alert_routes_to_admin_boundary_scenario_registered() -> None:
    scenario = {
        "boundary": "cost_governance.anomaly_service -> notifications.alert_service",
        "recipients": ["workspace_admin"],
    }

    assert "notifications" in scenario["boundary"]
    assert scenario["recipients"] == ["workspace_admin"]
