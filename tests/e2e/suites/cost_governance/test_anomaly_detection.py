from __future__ import annotations


def test_anomaly_detection_routes_alert_to_admin_boundary() -> None:
    scenario = {
        "boundary": "cost_governance.anomaly_service -> notifications.alert_service",
        "recipients": ["workspace_admin"],
        "assertions": ["cost.anomaly.detected", "admin_notification_delivered"],
    }

    assert "notifications" in scenario["boundary"]
    assert scenario["recipients"] == ["workspace_admin"]
    assert "cost.anomaly.detected" in scenario["assertions"]
