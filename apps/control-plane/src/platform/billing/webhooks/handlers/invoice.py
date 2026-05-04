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
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.webhooks.handlers.registry import HandlerContext
from platform.common.logging import get_logger
from uuid import UUID

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


async def on_paid(event: WebhookEvent, ctx: HandlerContext) -> None:
    invoice = event.payload
    stripe_invoice_id = str(invoice.get("id", ""))
    customer_id = str(invoice.get("customer", ""))
    LOGGER.info(
        "billing.webhook.invoice_paid",
        event_id=event.id,
        stripe_invoice_id=stripe_invoice_id,
        customer_id=customer_id,
    )
    payload = InvoicePaidPayload(
        invoice_id=UUID(int=0),
        subscription_id=UUID(int=0),
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
    attempt_count = int(invoice.get("attempt_count", 1))
    LOGGER.warning(
        "billing.webhook.invoice_failed",
        event_id=event.id,
        stripe_invoice_id=stripe_invoice_id,
        customer_id=customer_id,
        attempt_count=attempt_count,
    )
    payload = InvoiceFailedPayload(
        invoice_id=UUID(int=0),
        subscription_id=UUID(int=0),
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
