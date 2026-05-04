"""UPD-052 — payment_failure_grace cron monitor.

APScheduler job that runs every ``BILLING_GRACE_MONITOR_INTERVAL_SECONDS``
(default 6 hours). Each tick:

1. Calls :meth:`PaymentFailureGraceService.tick_reminders` to dispatch
   day-1/3/5 reminders for any open grace whose interval is due.
2. Calls :meth:`PaymentFailureGraceService.tick_expiries` to downgrade any
   open grace whose ``grace_ends_at`` has passed.

The cron is registered alongside the existing data-lifecycle and other
worker-profile schedulers in ``platform.main`` (see Phase 2 wiring).
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.billing.payment_failure_grace.repository import (
    PaymentFailureGraceRepository,
)
from platform.billing.payment_failure_grace.service import (
    PaymentFailureGraceService,
)
from platform.common.database import AsyncSessionLocal
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler

LOGGER = get_logger(__name__)

JOB_ID = "billing.payment_failure_grace_monitor"


def build_grace_monitor_scheduler(
    *,
    interval_seconds: int,
    producer: EventProducer | None,
) -> AsyncIOScheduler:
    """Return an AsyncIOScheduler that fires the grace tick on a fixed interval.

    Caller MUST ``start()`` the scheduler when the worker profile boots.
    Idempotent: running multiple workers is safe because the database
    transaction in ``service.tick_*`` only modifies one row at a time and
    each repo update is keyed on the row id.
    """
    scheduler = AsyncIOScheduler(timezone=UTC)

    async def tick() -> None:
        try:
            async with AsyncSessionLocal() as session:
                repo = PaymentFailureGraceRepository(session)
                service = PaymentFailureGraceService(
                    repository=repo,
                    producer=producer,
                )
                correlation = CorrelationContext(correlation_id=uuid4())
                now = datetime.now(UTC)
                await service.tick_reminders(
                    correlation_ctx=correlation,
                    now=now,
                )
                await service.tick_expiries(
                    correlation_ctx=correlation,
                    now=now,
                )
                await session.commit()
        except Exception:  # pragma: no cover - defensive
            LOGGER.exception("billing.grace_monitor_tick_failed")

    scheduler.add_job(
        tick,
        trigger="interval",
        seconds=interval_seconds,
        id=JOB_ID,
        replace_existing=True,
        coalesce=True,
    )
    return scheduler
