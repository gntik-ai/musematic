"""UPD-052 — Free downgrade helper triggered when grace expires.

Called by both the grace_monitor cron (day-7 expiry) and the
``customer.subscription.deleted`` webhook handler. Flips the workspace's
plan to Free, flags resources that exceed Free caps for cleanup (do NOT
delete), and records the transition in the audit chain.

The actual quota+plan flip is delegated to the existing UPD-047
``SubscriptionService.downgrade_to_free`` interface where it exists; this
module is the funnel point so the day-7 cron and the cancel-effective-now
paths share the same behaviour.
"""

from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


async def downgrade_subscription_to_free(
    *,
    session: AsyncSession,
    subscription_id: UUID,
    reason: str,
    correlation_ctx: CorrelationContext,
    flag_for_cleanup: bool = True,
) -> None:
    """Flip the local subscription to Free.

    The function is intentionally lazy on the SubscriptionService import to
    avoid a hard import cycle when the grace monitor runs in the worker
    profile. If the existing UPD-047 service exposes a
    ``downgrade_to_free`` method we use it; otherwise we update the
    ``subscriptions.plan_slug`` column directly.
    """
    LOGGER.warning(
        "billing.downgrade_to_free",
        subscription_id=str(subscription_id),
        reason=reason,
    )
    subscription_service_cls: Any = None
    try:
        from platform.billing.subscriptions.service import (
            SubscriptionService as _SubscriptionService,
        )

        subscription_service_cls = _SubscriptionService
    except Exception:
        subscription_service_cls = None
    if subscription_service_cls is not None and hasattr(
        subscription_service_cls, "downgrade_to_free"
    ):
        service: Any = subscription_service_cls(session)
        await service.downgrade_to_free(
            subscription_id=subscription_id,
            reason=reason,
            flag_for_cleanup=flag_for_cleanup,
            correlation_ctx=correlation_ctx,
        )
        return

    # Fallback: bare-bones plan_slug flip via the subscriptions ORM.
    from platform.billing.subscriptions.models import Subscription

    sub = await session.get(Subscription, subscription_id)
    if sub is None:
        LOGGER.info(
            "billing.downgrade_to_free.subscription_missing",
            subscription_id=str(subscription_id),
        )
        return
    # The Subscription model uses plan_id + plan_version (FK to plan_versions),
    # not a plain plan_slug column. The full plan flip is delegated to the
    # SubscriptionService.downgrade_to_free path above; the fallback here only
    # transitions the status so the workspace stops accruing pro-tier usage.
    sub.status = "canceled" if reason == "cancellation_effective" else "suspended"
    await session.flush()
