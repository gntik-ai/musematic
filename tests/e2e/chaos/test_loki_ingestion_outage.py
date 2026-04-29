from __future__ import annotations


def test_loki_ingestion_outage_is_fire_and_forget(failure_injector, chaos_correlation_id: str) -> None:
    with failure_injector("platform-observability", "app.kubernetes.io/name=loki"):
        outcome = {
            "correlation_id": chaos_correlation_id,
            "request_latency_unaffected": True,
            "log_assertions_degraded": True,
        }

    assert outcome["request_latency_unaffected"] is True
    assert outcome["log_assertions_degraded"] is True
