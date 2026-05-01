from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any, cast
from uuid import uuid4

LOGGER = get_logger(__name__)


async def run_period_rollover(app: Any) -> None:
    now = datetime.now(UTC)
    producer = cast(EventProducer | None, app.state.clients.get("kafka"))
    async with database.AsyncSessionLocal() as session:
        repository = SubscriptionsRepository(session)
        due = await repository.list_due_for_period_rollover(now)
        for subscription in due:
            previous_start = subscription.current_period_start
            previous_end = subscription.current_period_end
            new_start = previous_end
            new_end = previous_end + timedelta(days=30)
            status = "canceled" if subscription.cancel_at_period_end else subscription.status
            await repository.advance_period(
                subscription,
                new_period_start=new_start,
                new_period_end=new_end,
                status=status,
            )
            if producer is not None:
                event_type = (
                    "billing.subscription.downgrade_effective"
                    if status == "canceled"
                    else "billing.subscription.period_renewed"
                )
                payload = (
                    {
                        "from_plan_slug": "unknown",
                        "from_plan_version": subscription.plan_version,
                        "to_plan_slug": "free",
                        "to_plan_version": 1,
                        "data_exceeding_free_limits": {},
                    }
                    if status == "canceled"
                    else {
                        "previous_period_start": previous_start.isoformat(),
                        "previous_period_end": previous_end.isoformat(),
                        "new_period_start": new_start.isoformat(),
                        "new_period_end": new_end.isoformat(),
                        "previous_period_overage_eur": "0.00",
                    }
                )
                await producer.publish(
                    "billing.lifecycle",
                    str(subscription.tenant_id),
                    event_type,
                    payload,
                    CorrelationContext(
                        correlation_id=uuid4(),
                        tenant_id=subscription.tenant_id,
                        workspace_id=(
                            subscription.scope_id
                            if subscription.scope_type == "workspace"
                            else None
                        ),
                    ),
                    "billing.period_scheduler",
                )
        await session.commit()
    if due:
        LOGGER.info("billing.period_rollover.completed", subscription_count=len(due))


def build_period_rollover_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    settings = cast(PlatformSettings, app.state.settings)
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_period_rollover(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=settings.BILLING_PERIOD_SCHEDULER_INTERVAL_SECONDS,
        id="billing.period_rollover",
        replace_existing=True,
    )
    return scheduler
