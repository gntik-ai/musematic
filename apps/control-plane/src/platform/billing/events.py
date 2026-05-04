"""UPD-052 — `billing.events` Kafka envelopes and publish helper.

The 9 event types emitted by the Stripe webhook handlers, the cancel API,
and the failed-payment grace state machine. Partition key is ``tenant_id``
so per-tenant ordering is preserved.

The shape of each payload is documented in
``specs/105-billing-payment-provider/contracts/billing-events-kafka.md``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from typing import Final
from uuid import UUID

from pydantic import BaseModel, Field

KAFKA_TOPIC: Final[str] = "billing.events"


class BillingEventType(StrEnum):
    """The 9 event types published on `billing.events`."""

    subscription_created = "billing.subscription.created"
    subscription_updated = "billing.subscription.updated"
    subscription_cancelled = "billing.subscription.cancelled"
    invoice_paid = "billing.invoice.paid"
    invoice_failed = "billing.invoice.failed"
    payment_method_attached = "billing.payment_method.attached"
    payment_failure_grace_opened = "billing.payment_failure_grace.opened"
    payment_failure_grace_resolved = "billing.payment_failure_grace.resolved"
    dispute_opened = "billing.dispute.opened"


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


class SubscriptionCreatedPayload(BaseModel):
    subscription_id: UUID
    tenant_id: UUID
    workspace_id: UUID | None = None
    plan_slug: str
    stripe_customer_id: str
    stripe_subscription_id: str
    current_period_end: datetime
    trial_end: datetime | None = None
    correlation_context: CorrelationContext


class SubscriptionUpdatedPayload(BaseModel):
    subscription_id: UUID
    from_plan_slug: str | None = None
    to_plan_slug: str
    cancel_at_period_end: bool = False
    current_period_end: datetime
    correlation_context: CorrelationContext


class SubscriptionCancelledPayload(BaseModel):
    subscription_id: UUID
    scheduled_at: datetime
    effective_at: datetime
    reason: str | None = None
    correlation_context: CorrelationContext


class InvoicePaidPayload(BaseModel):
    invoice_id: UUID
    subscription_id: UUID
    amount_total_eur: Decimal
    amount_tax_eur: Decimal
    currency: str = Field(default="EUR")
    paid_at: datetime
    correlation_context: CorrelationContext


class InvoiceFailedPayload(BaseModel):
    invoice_id: UUID
    subscription_id: UUID
    amount_total_eur: Decimal
    currency: str = Field(default="EUR")
    attempt_count: int
    next_retry_at: datetime | None = None
    correlation_context: CorrelationContext


class PaymentMethodAttachedPayload(BaseModel):
    payment_method_id: UUID
    tenant_id: UUID
    workspace_id: UUID | None = None
    stripe_payment_method_id: str
    brand: str | None = None
    last4: str | None = None
    is_default: bool = False
    correlation_context: CorrelationContext


class PaymentFailureGraceOpenedPayload(BaseModel):
    grace_id: UUID
    subscription_id: UUID
    started_at: datetime
    grace_ends_at: datetime
    correlation_context: CorrelationContext


class PaymentFailureGraceResolvedPayload(BaseModel):
    grace_id: UUID
    subscription_id: UUID
    resolved_at: datetime
    resolution: str
    correlation_context: CorrelationContext


class DisputeOpenedPayload(BaseModel):
    stripe_charge_id: str
    stripe_dispute_id: str
    tenant_id: UUID
    subscription_id: UUID | None = None
    amount_eur: Decimal
    reason: str | None = None
    correlation_context: CorrelationContext


# ---------------------------------------------------------------------------
# Publish helper
# ---------------------------------------------------------------------------


async def publish_billing_event(
    producer: EventProducer | None,
    event_type: BillingEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    partition_key: str | UUID,
    source: str = "platform.billing",
) -> None:
    """Publish a `billing.events` event partitioned by ``partition_key``.

    Mirrors `publish_data_lifecycle_event` (UPD-051) so consumers and tests
    can rely on the same envelope shape across BCs.
    """
    if producer is None:
        return
    event_name = (
        event_type.value
        if isinstance(event_type, BillingEventType)
        else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=str(partition_key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
