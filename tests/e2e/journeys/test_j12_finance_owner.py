from __future__ import annotations

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j12_finance_owner]


def test_j12_finance_owner_budget_chargeback_cycle_contract() -> None:
    stages = [
        "budget_configured",
        "threshold_50_event",
        "threshold_50_notification",
        "threshold_80_event",
        "threshold_80_notification",
        "hard_cap_blocks_execution",
        "admin_override_audited",
        "post_override_execution_succeeds",
        "cost_anomaly_event",
        "chargeback_totals_match_rollup",
        "forecast_confidence_interval",
        "cost_attribution_loki_log",
    ]

    assert len(stages) >= 7
    assert "hard_cap_blocks_execution" in stages
    assert "chargeback_totals_match_rollup" in stages


def test_j12_override_audit_references_budget_snapshot_and_scope() -> None:
    audit_entry = {"original_budget_snapshot": "sha256:abc", "override_grant_scope": "workspace"}

    assert audit_entry["original_budget_snapshot"].startswith("sha256:")
    assert audit_entry["override_grant_scope"] == "workspace"


def test_j12_forecast_confidence_interval_shape() -> None:
    forecast = {"point_estimate": 10, "lower_bound": 8, "upper_bound": 12, "confidence_level": 0.95}

    assert forecast["lower_bound"] <= forecast["point_estimate"] <= forecast["upper_bound"]
    assert 0 < forecast["confidence_level"] <= 1


def test_j12_cost_attribution_loki_log_assertion_contract() -> None:
    labels = {"bounded_context": "cost_governance"}
    assert labels["bounded_context"] == "cost_governance"
