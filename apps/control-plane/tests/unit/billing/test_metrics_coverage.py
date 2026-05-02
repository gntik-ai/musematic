from __future__ import annotations

from platform.billing import metrics as billing_metrics


class _Instrument:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def add(self, value: int, *, attributes: dict[str, str]) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, *, attributes: dict[str, str]) -> None:
        self.calls.append((value, attributes))


def test_billing_metrics_fallback_and_instrument_helpers(monkeypatch) -> None:
    monkeypatch.setattr(
        billing_metrics,
        "import_module",
        lambda name: (_ for _ in ()).throw(RuntimeError(name)),
    )
    fallback = billing_metrics.BillingMetrics()
    assert fallback.quota_checks is None
    fallback.record_quota_check(result="OK", plan_tier="free", seconds=0.1)
    fallback.record_overage_authorize("authorized")
    fallback.record_plan_publish()
    fallback.record_subscription_transition("trial", "active")
    fallback.record_metering_lag(0.2)

    counter = _Instrument()
    histogram = _Instrument()
    billing_metrics._add(counter, 1, {"key": "value"})
    billing_metrics._record(histogram, 0.25, {"key": "value"})

    assert counter.calls == [(1, {"key": "value"})]
    assert histogram.calls == [(0.25, {"key": "value"})]
