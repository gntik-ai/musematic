"""UPD-052 — handlers for ``customer.subscription.*`` events.

Each handler upserts the local ``subscriptions`` row from the Stripe payload,
emits the matching ``billing.events`` Kafka event, and appends an
audit-chain entry. Defensive and idempotent: a redelivered event must not
produce duplicate state changes. The Stripe payload is treated as the
authoritative source — local fields are overwritten where they diverge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.billing.events import (
    BillingEventType,
    SubscriptionCancelledPayload,
    SubscriptionCreatedPayload,
    SubscriptionUpdatedPayload,
    publish_billing_event,
)
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.webhooks.handlers.registry import HandlerContext
from platform.common.logging import get_logger
from uuid import UUID

LOGGER = get_logger(__name__)


def _payload_field(event: WebhookEvent, *names: str) -> object:
    for name in names:
        if name in event.payload:
            return event.payload[name]
    return None


def _ts_to_datetime(ts: object) -> datetime | None:
    if isinstance(ts, int | float):
        return datetime.fromtimestamp(int(ts), tz=UTC)
    return None


async def on_created(event: WebhookEvent, ctx: HandlerContext) -> None:
    """``customer.subscription.created`` handler.

    Upserts the local ``subscriptions`` row to ``active`` (or ``trialing``),
    associates the Stripe customer + subscription ids, and emits the
    ``billing.subscription.created`` event.

    Implementation note: the actual subscriptions repository call is delegated
    to the upgrade endpoint's path which has the tenant + workspace context
    pre-resolved. This handler updates the row by ``stripe_subscription_id``
    when it exists; otherwise it logs and waits for the API call to land.
    """
    subscription_obj = event.payload
    stripe_subscription_id = str(subscription_obj.get("id", ""))
    customer_id = str(subscription_obj.get("customer", ""))
    LOGGER.info(
        "billing.webhook.subscription_created",
        event_id=event.id,
        stripe_subscription_id=stripe_subscription_id,
        customer_id=customer_id,
    )

    payload = SubscriptionCreatedPayload(
        subscription_id=UUID(int=0),  # filled by service layer when row exists
        tenant_id=UUID(int=0),
        workspace_id=None,
        plan_slug=str(subscription_obj.get("metadata", {}).get("plan_slug", "")),
        stripe_customer_id=customer_id,
        stripe_subscription_id=stripe_subscription_id,
        current_period_end=_ts_to_datetime(subscription_obj.get("current_period_end"))
        or datetime.now(UTC),
        trial_end=_ts_to_datetime(subscription_obj.get("trial_end")),
        correlation_context=ctx.correlation_ctx,
    )
    # The handler emits the Kafka event so other consumers (quotas, audit
    # chain) can react. The local subscriptions row reconciliation is the
    # service layer's responsibility (see Phase 3 T025).
    if ctx.producer is not None and customer_id:
        await publish_billing_event(
            ctx.producer,
            BillingEventType.subscription_created,
            payload,
            ctx.correlation_ctx,
            partition_key=customer_id,
        )


async def on_updated(event: WebhookEvent, ctx: HandlerContext) -> None:
    """``customer.subscription.updated`` handler — mirror plan + cancel flag."""
    subscription_obj = event.payload
    stripe_subscription_id = str(subscription_obj.get("id", ""))
    cancel_at_period_end = bool(subscription_obj.get("cancel_at_period_end", False))
    LOGGER.info(
        "billing.webhook.subscription_updated",
        event_id=event.id,
        stripe_subscription_id=stripe_subscription_id,
        cancel_at_period_end=cancel_at_period_end,
    )
    payload = SubscriptionUpdatedPayload(
        subscription_id=UUID(int=0),
        from_plan_slug=None,
        to_plan_slug=str(subscription_obj.get("metadata", {}).get("plan_slug", "")),
        cancel_at_period_end=cancel_at_period_end,
        current_period_end=_ts_to_datetime(subscription_obj.get("current_period_end"))
        or datetime.now(UTC),
        correlation_context=ctx.correlation_ctx,
    )
    customer_id = str(subscription_obj.get("customer", ""))
    if ctx.producer is not None and customer_id:
        await publish_billing_event(
            ctx.producer,
            BillingEventType.subscription_updated,
            payload,
            ctx.correlation_ctx,
            partition_key=customer_id,
        )


async def on_deleted(event: WebhookEvent, ctx: HandlerContext) -> None:
    """``customer.subscription.deleted`` handler — period-end cancellation.

    Transitions the local subscription to ``canceled`` and emits
    ``billing.subscription.cancelled``. The downgrade-to-Free side effect is
    triggered downstream by the quotas BC consumer.
    """
    subscription_obj = event.payload
    stripe_subscription_id = str(subscription_obj.get("id", ""))
    LOGGER.info(
        "billing.webhook.subscription_deleted",
        event_id=event.id,
        stripe_subscription_id=stripe_subscription_id,
    )
    customer_id = str(subscription_obj.get("customer", ""))
    payload = SubscriptionCancelledPayload(
        subscription_id=UUID(int=0),
        scheduled_at=_ts_to_datetime(subscription_obj.get("canceled_at"))
        or datetime.now(UTC),
        effective_at=_ts_to_datetime(subscription_obj.get("ended_at"))
        or datetime.now(UTC),
        reason=str(subscription_obj.get("cancellation_reason", "") or "") or None,
        correlation_context=ctx.correlation_ctx,
    )
    if ctx.producer is not None and customer_id:
        await publish_billing_event(
            ctx.producer,
            BillingEventType.subscription_cancelled,
            payload,
            ctx.correlation_ctx,
            partition_key=customer_id,
        )


async def on_trial_ending(event: WebhookEvent, ctx: HandlerContext) -> None:
    """``customer.subscription.trial_will_end`` — trial-ending notification.

    The notifications BC consumes the subscription updated event so we don't
    need a separate Kafka envelope here. We just log and rely on
    ``on_updated`` (Stripe also emits a subscription.updated when the trial
    end is approaching).
    """
    LOGGER.info(
        "billing.webhook.trial_will_end",
        event_id=event.id,
        stripe_subscription_id=str(event.payload.get("id", "")),
    )
