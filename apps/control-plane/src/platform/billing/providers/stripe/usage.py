"""UPD-052 — Stripe Usage Records helper.

Reports metered overage usage to Stripe per the Usage Records API. Calls
are idempotent (Stripe enforces idempotency via the ``idempotency_key``)
so the existing UPD-047 OverageAuthorizationsService can call this every
time the execution engine reports an overage minute without worrying
about double-charging on retries.
"""

from __future__ import annotations

from datetime import datetime
from platform.billing.providers.stripe.client import StripeClient
from platform.common.logging import get_logger

LOGGER = get_logger(__name__)


async def report_usage_record(
    client: StripeClient,
    *,
    subscription_item_id: str,
    quantity: int,
    timestamp: datetime,
    idempotency_key: str,
    action: str = "increment",
) -> None:
    """Submit a single usage record to Stripe.

    Stripe's Usage Records API accepts ``increment`` (additive over the
    period) or ``set`` (absolute count). The default is ``increment``;
    callers reporting cumulative period totals should pass ``action="set"``.
    """
    await client.call(
        "subscription_item.usage_record.create",
        lambda: client.stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            quantity=quantity,
            timestamp=int(timestamp.timestamp()),
            action=action,
            idempotency_key=idempotency_key,
        ),
    )
    LOGGER.info(
        "billing.stripe_usage_reported",
        subscription_item_id=subscription_item_id,
        quantity=quantity,
        action=action,
    )
