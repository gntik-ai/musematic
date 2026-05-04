"""UPD-052 — handlers for ``invoice.payment_succeeded`` and
``invoice.payment_failed`` events.

The success path closes any open ``payment_failure_grace`` row for the
subscription and emits ``billing.invoice.paid``. The failure path opens (or
extends) the grace window and emits ``billing.invoice.failed``.

The actual subscription/grace state mutation is delegated to the dedicated
service layer (Phase 5); this handler is the thin Kafka emitter + bookkeeper.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.events import (
    BillingEventType,
    InvoiceFailedPayload,
    InvoicePaidPayload,
    publish_billing_event,
)
from platform.billing.payment_failure_grace.repository import (
    PaymentFailureGraceRepository,
)
from platform.billing.payment_failure_grace.service import (
    PaymentFailureGraceService,
)
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.subscriptions.models import Subscription
from platform.billing.webhooks.handlers.registry import HandlerContext
from platform.common.logging import get_logger
from uuid import UUID

from sqlalchemy import select

LOGGER = get_logger(__name__)


def _ts(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(int(value), tz=UTC)
    return None


def _amount(value: object) -> Decimal:
    """Stripe amounts arrive as integer cents — convert to EUR Decimal."""
    if isinstance(value, int | float):
        return Decimal(int(value)) / Decimal(100)
    return Decimal("0.00")


async def _resolve_local_subscription(
    ctx: HandlerContext,
    *,
    stripe_subscription_id: str,
    stripe_customer_id: str,
) -> Subscription | None:
    """Look up the local subscription row by Stripe ids."""
    if not stripe_subscription_id and not stripe_customer_id:
        return None
    stmt = select(Subscription).where(
        (Subscription.stripe_subscription_id == stripe_subscription_id)
        | (Subscription.stripe_customer_id == stripe_customer_id)
    )
    result = await ctx.session.execute(stmt)
    return result.scalars().first()


async def on_paid(event: WebhookEvent, ctx: HandlerContext) -> None:
    invoice = event.payload
    stripe_invoice_id = str(invoice.get("id", ""))
    customer_id = str(invoice.get("customer", ""))
    stripe_subscription_id = str(invoice.get("subscription", ""))
    LOGGER.info(
        "billing.webhook.invoice_paid",
        event_id=event.id,
        stripe_invoice_id=stripe_invoice_id,
        customer_id=customer_id,
    )

    # Resolve the local subscription so the grace state machine can close
    # any open grace row (research R8).
    sub = await _resolve_local_subscription(
        ctx,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=customer_id,
    )
    subscription_uuid = sub.id if sub is not None else UUID(int=0)
    if sub is not None:
        grace_service = PaymentFailureGraceService(
            repository=PaymentFailureGraceRepository(ctx.session),
            producer=ctx.producer,
        )
        await grace_service.resolve_payment_recovered(
            subscription_id=sub.id,
            correlation_ctx=ctx.correlation_ctx,
        )

    payload = InvoicePaidPayload(
        invoice_id=UUID(int=0),
        subscription_id=subscription_uuid,
        amount_total_eur=_amount(invoice.get("total")),
        amount_tax_eur=_amount(invoice.get("tax")),
        currency=str(invoice.get("currency", "eur")).upper() or "EUR",
        paid_at=_ts(invoice.get("status_transitions", {}).get("paid_at"))
        or datetime.now(UTC),
        correlation_context=ctx.correlation_ctx,
    )
    if ctx.producer is not None and customer_id:
        await publish_billing_event(
            ctx.producer,
            BillingEventType.invoice_paid,
            payload,
            ctx.correlation_ctx,
            partition_key=customer_id,
        )


async def on_failed(event: WebhookEvent, ctx: HandlerContext) -> None:
    invoice = event.payload
    stripe_invoice_id = str(invoice.get("id", ""))
    customer_id = str(invoice.get("customer", ""))
    stripe_subscription_id = str(invoice.get("subscription", ""))
    attempt_count = int(invoice.get("attempt_count", 1))
    LOGGER.warning(
        "billing.webhook.invoice_failed",
        event_id=event.id,
        stripe_invoice_id=stripe_invoice_id,
        customer_id=customer_id,
        attempt_count=attempt_count,
    )

    # Resolve local subscription and start the grace state machine.
    sub = await _resolve_local_subscription(
        ctx,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=customer_id,
    )
    subscription_uuid = sub.id if sub is not None else UUID(int=0)
    if sub is not None:
        # Transition to past_due before opening the grace row so consumers
        # that subscribe to billing.events see consistent state.
        sub.status = "past_due"
        await ctx.session.flush()
        grace_service = PaymentFailureGraceService(
            repository=PaymentFailureGraceRepository(ctx.session),
            producer=ctx.producer,
        )
        await grace_service.start_grace(
            tenant_id=sub.tenant_id,
            subscription_id=sub.id,
            correlation_ctx=ctx.correlation_ctx,
        )

    payload = InvoiceFailedPayload(
        invoice_id=UUID(int=0),
        subscription_id=subscription_uuid,
        amount_total_eur=_amount(invoice.get("total")),
        currency=str(invoice.get("currency", "eur")).upper() or "EUR",
        attempt_count=attempt_count,
        next_retry_at=_ts(invoice.get("next_payment_attempt")),
        correlation_context=ctx.correlation_ctx,
    )
    if ctx.producer is not None and customer_id:
        await publish_billing_event(
            ctx.producer,
            BillingEventType.invoice_failed,
            payload,
            ctx.correlation_ctx,
            partition_key=customer_id,
        )
