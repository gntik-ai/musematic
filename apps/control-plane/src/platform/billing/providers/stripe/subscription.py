"""UPD-052 — Stripe subscription helpers.

Wraps the synchronous ``stripe.Subscription`` SDK calls. Subscriptions are
created with ``automatic_tax: { enabled: true }`` per research R7 so EU IVA
OSS is computed by Stripe Tax, not in-platform.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.billing.providers.protocol import ProviderSubscription
from platform.billing.providers.stripe.client import StripeClient
from platform.common.logging import get_logger
from typing import Any

LOGGER = get_logger(__name__)


async def create_subscription(
    client: StripeClient,
    *,
    customer_id: str,
    price_id: str,
    overage_price_id: str | None = None,
    trial_days: int = 0,
    idempotency_key: str | None = None,
    plan_slug: str | None = None,
) -> ProviderSubscription:
    items: list[dict[str, Any]] = [{"price": price_id}]
    if overage_price_id:
        items.append({"price": overage_price_id})

    payload: dict[str, Any] = {
        "customer": customer_id,
        "items": items,
        "automatic_tax": {"enabled": True},
        "expand": ["latest_invoice.payment_intent"],
    }
    if trial_days > 0:
        payload["trial_period_days"] = trial_days
    if plan_slug:
        payload["metadata"] = {"plan_slug": plan_slug}

    subscription = await client.call(
        "subscription.create",
        lambda: client.stripe.Subscription.create(
            **payload,
            **({"idempotency_key": idempotency_key} if idempotency_key else {}),
        ),
    )
    return _to_provider_subscription(subscription)


async def update_subscription(
    client: StripeClient,
    *,
    subscription_id: str,
    target_price_id: str | None = None,
    cancel_at_period_end: bool | None = None,
    proration_behavior: str = "create_prorations",
    idempotency_key: str | None = None,
) -> ProviderSubscription:
    update_kwargs: dict[str, Any] = {}
    if cancel_at_period_end is not None:
        update_kwargs["cancel_at_period_end"] = cancel_at_period_end
    if target_price_id:
        update_kwargs["items"] = [{"price": target_price_id}]
        update_kwargs["proration_behavior"] = proration_behavior
    sub = await client.call(
        "subscription.update",
        lambda: client.stripe.Subscription.modify(
            subscription_id,
            **update_kwargs,
            **({"idempotency_key": idempotency_key} if idempotency_key else {}),
        ),
    )
    return _to_provider_subscription(sub)


async def cancel_subscription(
    client: StripeClient,
    *,
    subscription_id: str,
    at_period_end: bool = True,
) -> ProviderSubscription:
    if at_period_end:
        sub = await client.call(
            "subscription.cancel_at_period_end",
            lambda: client.stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True,
            ),
        )
    else:
        sub = await client.call(
            "subscription.cancel_now",
            lambda: client.stripe.Subscription.delete(subscription_id),
        )
    return _to_provider_subscription(sub)


def _ts(value: Any) -> datetime:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(int(value), tz=UTC)
    return datetime.now(UTC)


def _to_provider_subscription(sub: Any) -> ProviderSubscription:
    sub_dict = dict(sub)
    plan_slug = (sub_dict.get("metadata", {}) or {}).get("plan_slug", "")
    return ProviderSubscription(
        provider_subscription_id=str(sub_dict.get("id", "")),
        status=str(sub_dict.get("status", "")),
        current_period_start=_ts(sub_dict.get("current_period_start")),
        current_period_end=_ts(sub_dict.get("current_period_end")),
        cancel_at_period_end=bool(sub_dict.get("cancel_at_period_end", False)),
        trial_end=_ts(sub_dict["trial_end"]) if sub_dict.get("trial_end") else None,
        plan_external_id=str(plan_slug or sub_dict.get("id", "")),
    )
