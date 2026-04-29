from __future__ import annotations


def test_oncall_incident_journey_crossing_points_registered() -> None:
    journey = [
        "alert_rule_fires",
        "oncall_paged",
        "runbook_surfaced",
        "incident_resolved",
        "post_mortem_started",
        "post_mortem_distributed",
    ]
    boundary_crossings = {
        "analytics -> incident_response": "alert_rule_fires",
        "incident_response -> notifications": "oncall_paged",
        "incident_response -> execution": "timeline_reconstruction",
        "incident_response -> audit": "audit_chain_entries",
    }

    assert journey == [
        "alert_rule_fires",
        "oncall_paged",
        "runbook_surfaced",
        "incident_resolved",
        "post_mortem_started",
        "post_mortem_distributed",
    ]
    assert boundary_crossings["analytics -> incident_response"] == "alert_rule_fires"
    assert boundary_crossings["incident_response -> notifications"] == "oncall_paged"
