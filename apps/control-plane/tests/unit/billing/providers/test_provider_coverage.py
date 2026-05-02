from __future__ import annotations

from decimal import Decimal
from platform.billing.providers.exceptions import (
    IdempotencyConflict,
    PaymentMethodInvalid,
    ProviderUnavailable,
)
from platform.billing.providers.stub_provider import StubPaymentProvider
from uuid import uuid4

import pytest


class _Logger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, object]]] = []

    def info(self, message: str, **kwargs: object) -> None:
        self.messages.append((message, kwargs))


@pytest.mark.asyncio
async def test_stub_payment_provider_covers_all_provider_paths() -> None:
    logger = _Logger()
    provider = StubPaymentProvider(logger)
    workspace_id = uuid4()
    tenant_id = uuid4()

    customer_id = await provider.create_customer(workspace_id, tenant_id, "billing@example.test")
    payment_method_id = await provider.attach_payment_method(customer_id, "tok_visa")
    trial_subscription = await provider.create_subscription(customer_id, "pro:v1", 14, "create-1")
    active_subscription = await provider.create_subscription(customer_id, "pro:v1", 0, "create-2")
    updated = await provider.update_subscription(
        trial_subscription.provider_subscription_id,
        "enterprise:v2",
        True,
        "update-1",
    )
    scheduled_cancel = await provider.cancel_subscription(updated.provider_subscription_id, True)
    immediate_cancel = await provider.cancel_subscription(updated.provider_subscription_id, False)
    preview = await provider.preview_proration(updated.provider_subscription_id, "enterprise:v2")
    await provider.report_usage(updated.provider_subscription_id, Decimal("2.5"), "usage-1")
    await provider.detach_payment_method(customer_id, payment_method_id)

    assert customer_id.startswith("stub_cus_")
    assert payment_method_id.startswith("stub_pm_")
    assert trial_subscription.status == "trialing"
    assert trial_subscription.trial_end is not None
    assert active_subscription.status == "active"
    assert updated.plan_external_id == "enterprise:v2"
    assert scheduled_cancel.cancel_at_period_end is True
    assert immediate_cancel.status == "canceled"
    assert preview.prorated_charge_eur == Decimal("0.00")
    assert provider.reported_usage[0]["quantity"] == Decimal("2.5")
    assert await provider.list_invoices(customer_id, limit=2) == []
    assert [message for message, _ in logger.messages] == [
        "billing.stub_usage_reported",
        "billing.stub_payment_method_detached",
    ]


def test_payment_provider_exception_types_set_billing_codes_and_details() -> None:
    invalid = PaymentMethodInvalid("stripe", "card declined")
    unavailable = ProviderUnavailable("stripe")
    conflict = IdempotencyConflict("stripe", "idem-1")

    assert invalid.code == "BILLING_PAYMENT_METHOD_INVALID"
    assert invalid.status_code == 502
    assert unavailable.code == "BILLING_PAYMENT_PROVIDER_UNAVAILABLE"
    assert unavailable.status_code == 503
    assert conflict.code == "BILLING_PAYMENT_IDEMPOTENCY_CONFLICT"
    assert conflict.status_code == 409
    assert conflict.details["idempotency_key"] == "idem-1"
