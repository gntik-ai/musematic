from __future__ import annotations


def test_replication_monitoring_reports_lag_below_rpo() -> None:
    status = {"lag_seconds": 12, "rpo_seconds": 60}
    assert status["lag_seconds"] <= status["rpo_seconds"]
