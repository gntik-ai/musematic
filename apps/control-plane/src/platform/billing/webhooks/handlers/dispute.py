"""UPD-052 — ``charge.dispute.created`` handler.

A chargeback (Stripe dispute) auto-suspends the subscription and notifies
super admins via UPD-077. The notifications consumer subscribes to
``billing.dispute.opened``; we just emit + log here.
"""

from __future__ import annotations

from decimal import Decimal
from platform.billing.events import (
    BillingEventType,
    DisputeOpenedPayload,
    publish_billing_event,
)
from platform.billing.metrics import metrics
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.webhooks.handlers.registry import HandlerContext
from platform.common.logging import get_logger
from uuid import UUID

LOGGER = get_logger(__name__)


def _amount_eur(value: object) -> Decimal:
    if isinstance(value, int | float):
        return Decimal(int(value)) / Decimal(100)
    return Decimal("0.00")


async def on_dispute(event: WebhookEvent, ctx: HandlerContext) -> None:
    dispute = event.payload
    charge_id = str(dispute.get("charge", ""))
    stripe_dispute_id = str(dispute.get("id", ""))
    LOGGER.warning(
        "billing.webhook.dispute_opened",
        event_id=event.id,
        stripe_dispute_id=stripe_dispute_id,
        charge_id=charge_id,
    )
    metrics.record_dispute_opened()
    if ctx.producer is None or not charge_id:
        return
    payload = DisputeOpenedPayload(
        stripe_charge_id=charge_id,
        stripe_dispute_id=stripe_dispute_id,
        tenant_id=UUID(int=0),
        subscription_id=None,
        amount_eur=_amount_eur(dispute.get("amount")),
        reason=str(dispute.get("reason", "") or "") or None,
        correlation_context=ctx.correlation_ctx,
    )
    await publish_billing_event(
        ctx.producer,
        BillingEventType.dispute_opened,
        payload,
        ctx.correlation_ctx,
        partition_key=charge_id,
    )
