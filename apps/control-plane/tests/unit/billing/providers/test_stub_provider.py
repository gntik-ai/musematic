from __future__ import annotations

from decimal import Decimal
from platform.billing.providers.protocol import PaymentProvider, ProrationPreview
from platform.billing.providers.stub_provider import StubPaymentProvider
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_stub_provider_satisfies_protocol_and_records_usage() -> None:
    provider = StubPaymentProvider()

    assert isinstance(provider, PaymentProvider)

    workspace_id = uuid4()
    tenant_id = uuid4()
    customer_id = await provider.create_customer(workspace_id, tenant_id, "owner@example.com")
    other_customer_id = await provider.create_customer(uuid4(), tenant_id, "owner@example.com")
    method_id = await provider.attach_payment_method(customer_id, "stub_pm_test")
    subscription = await provider.create_subscription(
        customer_id,
        "pro:v1",
        trial_days=14,
        idempotency_key="subscription-key",
    )
    preview = await provider.preview_proration(subscription.provider_subscription_id, "pro:v2")
    await provider.report_usage(
        subscription.provider_subscription_id,
        Decimal("12.5000"),
        "usage-key",
    )

    assert customer_id.startswith("stub_cus_")
    assert other_customer_id != customer_id
    assert method_id.startswith("stub_pm_")
    assert subscription.status == "trialing"
    assert isinstance(preview, ProrationPreview)
    assert preview.prorated_charge_eur == Decimal("0.00")
    assert provider.reported_usage == [
        {
            "provider_subscription_id": subscription.provider_subscription_id,
            "quantity": Decimal("12.5000"),
            "idempotency_key": "usage-key",
        }
    ]
