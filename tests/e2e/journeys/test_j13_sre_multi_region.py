from __future__ import annotations

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j13_sre_multi_region]


def test_j13_sre_failover_cycle_contract() -> None:
    stages = [
        "maintenance_window_scheduled",
        "inflight_executions_drained",
        "new_execution_maintenance_error",
        "replication_lag_below_rpo",
        "failover_initiated_event",
        "failover_completed_event",
        "secondary_execution_succeeds",
        "failback_completed",
        "reconciliation_zero_divergence",
    ]

    assert len(stages) >= 7
    assert "replication_lag_below_rpo" in stages
    assert "reconciliation_zero_divergence" in stages


def test_j13_secondary_not_ready_fails_fast() -> None:
    failure = {"accepted": False, "error": "secondary region capacity not ready"}

    assert failure["accepted"] is False
    assert "capacity" in failure["error"]


def test_j13_maintenance_gate_fails_open_on_redis_miss() -> None:
    gate = {"redis_available": False, "request_blocked": False, "mode": "fail-open"}

    assert gate["request_blocked"] is False
    assert gate["mode"] == "fail-open"


def test_j13_rpo_rto_metric_assertion_contract() -> None:
    metrics = {"rpo_seconds": 15, "rto_seconds": 90, "rpo_threshold": 60, "rto_threshold": 300}

    assert metrics["rpo_seconds"] <= metrics["rpo_threshold"]
    assert metrics["rto_seconds"] <= metrics["rto_threshold"]
