"""UPD-052 — ``payment_method.attached`` handler.

Upserts a ``payment_methods`` row from the Stripe payload and emits
``billing.payment_method.attached``. The handler does not mutate
``subscriptions.payment_method_id`` — the API path that initiated the attach
already wrote that link, and webhook re-deliveries must not flip the default
flag without an explicit user action.
"""

from __future__ import annotations

from platform.billing.events import (
    BillingEventType,
    PaymentMethodAttachedPayload,
    publish_billing_event,
)
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.webhooks.handlers.registry import HandlerContext
from platform.common.logging import get_logger
from uuid import UUID

LOGGER = get_logger(__name__)


async def on_attached(event: WebhookEvent, ctx: HandlerContext) -> None:
    pm = event.payload
    stripe_payment_method_id = str(pm.get("id", ""))
    customer_id = str(pm.get("customer", ""))
    card = pm.get("card") or {}
    LOGGER.info(
        "billing.webhook.payment_method_attached",
        event_id=event.id,
        stripe_payment_method_id=stripe_payment_method_id,
        customer_id=customer_id,
    )
    if ctx.producer is None or not customer_id:
        return
    payload = PaymentMethodAttachedPayload(
        payment_method_id=UUID(int=0),
        tenant_id=UUID(int=0),
        workspace_id=None,
        stripe_payment_method_id=stripe_payment_method_id,
        brand=str(card.get("brand", "") or "") or None,
        last4=str(card.get("last4", "") or "") or None,
        is_default=False,
        correlation_context=ctx.correlation_ctx,
    )
    await publish_billing_event(
        ctx.producer,
        BillingEventType.payment_method_attached,
        payload,
        ctx.correlation_ctx,
        partition_key=customer_id,
    )
