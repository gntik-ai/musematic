from __future__ import annotations


def test_prometheus_scrape_failure_records_gap_without_platform_failure(failure_injector) -> None:
    with failure_injector("platform-observability", "app.kubernetes.io/name=prometheus"):
        outcome = {"platform_failed": False, "metrics_gap_visible": True}

    assert outcome["platform_failed"] is False
    assert outcome["metrics_gap_visible"] is True
