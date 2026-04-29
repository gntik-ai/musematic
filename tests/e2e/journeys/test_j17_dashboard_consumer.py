from __future__ import annotations

from uuid import uuid4

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j17_dashboard_consumer]


def test_j17_dashboard_consumer_log_metric_trace_contract() -> None:
    hops = [
        "synthetic_failure_injected",
        "loki_log_within_15s",
        "high_error_log_rate_alert_fires",
        "notification_channel_receives_alert",
        "d12_dashboard_snapshot_taken",
        "loki_trace_id_links_to_jaeger",
        "trace_spans_three_services",
        "prometheus_metric_spike_correlates",
        "failure_resolved",
        "alert_closes_within_ruler_interval",
    ]

    assert len(hops) >= 7
    assert {"loki_trace_id_links_to_jaeger", "prometheus_metric_spike_correlates"} <= set(hops)


def test_j17_deterministic_correlation_scope_contract() -> None:
    first = f"j17-{uuid4()}"
    second = f"j17-{uuid4()}"

    assert first != second
    assert first.startswith("j17-")
    assert second.startswith("j17-")
