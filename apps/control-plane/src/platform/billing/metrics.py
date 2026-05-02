from __future__ import annotations

from importlib import import_module
from typing import Any


class BillingMetrics:
    def __init__(self) -> None:
        try:
            meter = import_module("opentelemetry.metrics").get_meter(__name__)
            self.quota_checks = meter.create_counter("billing_quota_check_total")
            self.quota_latency = meter.create_histogram("billing_quota_check_seconds")
            self.overage_authorize = meter.create_counter("billing_overage_authorize_total")
            self.plan_publish = meter.create_counter("billing_plan_publish_total")
            self.subscription_transition = meter.create_counter(
                "billing_subscription_state_transition_total"
            )
            self.metering_lag = meter.create_histogram("billing_metering_lag_seconds")
        except Exception:
            self.quota_checks = None
            self.quota_latency = None
            self.overage_authorize = None
            self.plan_publish = None
            self.subscription_transition = None
            self.metering_lag = None

    def record_quota_check(self, *, result: str, plan_tier: str, seconds: float) -> None:
        attrs = {"result": result, "plan_tier": plan_tier}
        _add(self.quota_checks, 1, attrs)
        _record(self.quota_latency, seconds, attrs)

    def record_overage_authorize(self, outcome: str) -> None:
        _add(self.overage_authorize, 1, {"outcome": outcome})

    def record_plan_publish(self) -> None:
        _add(self.plan_publish, 1, {})

    def record_subscription_transition(self, from_status: str, to_status: str) -> None:
        _add(
            self.subscription_transition,
            1,
            {"from_status": from_status, "to_status": to_status},
        )

    def record_metering_lag(self, seconds: float) -> None:
        _record(self.metering_lag, seconds, {})


metrics = BillingMetrics()


def _add(instrument: Any | None, value: int, attributes: dict[str, str]) -> None:
    if instrument is not None:
        instrument.add(value, attributes=attributes)


def _record(instrument: Any | None, value: float, attributes: dict[str, str]) -> None:
    if instrument is not None:
        instrument.record(value, attributes=attributes)
