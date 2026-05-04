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
            # UPD-052 — Stripe webhook + grace + invoice/dispute counters.
            self.webhook_signature_failed = meter.create_counter(
                "billing_webhook_signature_failed_total"
            )
            self.webhook_processed = meter.create_counter(
                "billing_webhook_processed_total"
            )
            self.webhook_handler_duration = meter.create_histogram(
                "billing_webhook_handler_duration_seconds"
            )
            self.payment_failure_grace_open_count = meter.create_up_down_counter(
                "billing_payment_failure_grace_open_count"
            )
            self.invoice_paid = meter.create_counter("billing_invoice_paid_total")
            self.dispute_opened = meter.create_counter("billing_dispute_opened_total")
        except Exception:
            self.quota_checks = None
            self.quota_latency = None
            self.overage_authorize = None
            self.plan_publish = None
            self.subscription_transition = None
            self.metering_lag = None
            self.webhook_signature_failed = None
            self.webhook_processed = None
            self.webhook_handler_duration = None
            self.payment_failure_grace_open_count = None
            self.invoice_paid = None
            self.dispute_opened = None

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

    def record_webhook_signature_failed(self) -> None:
        _add(self.webhook_signature_failed, 1, {})

    def record_webhook_processed(self, *, event_type: str, outcome: str) -> None:
        _add(self.webhook_processed, 1, {"event_type": event_type, "outcome": outcome})

    def record_webhook_handler_duration(
        self,
        seconds: float,
        *,
        event_type: str,
    ) -> None:
        _record(self.webhook_handler_duration, seconds, {"event_type": event_type})

    def adjust_payment_failure_grace_open(self, delta: int) -> None:
        _add(self.payment_failure_grace_open_count, delta, {})

    def record_invoice_paid(self) -> None:
        _add(self.invoice_paid, 1, {})

    def record_dispute_opened(self) -> None:
        _add(self.dispute_opened, 1, {})


metrics = BillingMetrics()


def _add(instrument: Any | None, value: int, attributes: dict[str, str]) -> None:
    if instrument is not None:
        instrument.add(value, attributes=attributes)


def _record(instrument: Any | None, value: float, attributes: dict[str, str]) -> None:
    if instrument is not None:
        instrument.record(value, attributes=attributes)
