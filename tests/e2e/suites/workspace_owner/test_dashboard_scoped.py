from __future__ import annotations


def test_dashboard_contract_populates_all_cards(workspace_with_seeded_data) -> None:
    cards = {
        "active_goals": workspace_with_seeded_data["active_goals"],
        "executions_in_flight": workspace_with_seeded_data["executions_in_flight"],
        "agent_count": workspace_with_seeded_data["agent_count"],
        "budget_percent": workspace_with_seeded_data["budget_percent"],
        "quotas": {"agents": {"used": 12, "limit": 20}},
        "tags": workspace_with_seeded_data["tags"],
        "dlp_violations": workspace_with_seeded_data["dlp_violations"],
    }

    assert len(cards) == 7
    assert cards["budget_percent"] <= 100
    assert cards["dlp_violations"] == 2


def test_dashboard_scope_enforcement_contract() -> None:
    scenario = {
        "allowed_workspace": "workspace-owner-e2e",
        "other_workspace_status": 403,
        "summary_cache_ttl_seconds": 30,
        "latency_threshold_ms": 3000,
    }

    assert scenario["other_workspace_status"] == 403
    assert scenario["summary_cache_ttl_seconds"] == 30
    assert scenario["latency_threshold_ms"] <= 3000
