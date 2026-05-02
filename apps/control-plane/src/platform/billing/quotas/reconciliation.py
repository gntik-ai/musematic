from __future__ import annotations

from dataclasses import dataclass
from platform.billing.quotas.models import ProcessedEventID
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

from sqlalchemy import select

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    expected_count: int
    missing_count: int
    mismatch_rate: float


class BillingReconciliationJob:
    def __init__(self, *, session: Any) -> None:
        self.session = session

    async def run_once(self, expected_event_ids: list[UUID]) -> ReconciliationResult:
        if not expected_event_ids:
            return ReconciliationResult(expected_count=0, missing_count=0, mismatch_rate=0.0)
        result = await self.session.execute(
            select(ProcessedEventID.event_id).where(ProcessedEventID.event_id.in_(expected_event_ids))
        )
        processed = set(result.scalars().all())
        missing = [event_id for event_id in expected_event_ids if event_id not in processed]
        mismatch_rate = len(missing) / len(expected_event_ids)
        if missing:
            LOGGER.warning(
                "billing.reconciliation.missing_events",
                expected_count=len(expected_event_ids),
                missing_count=len(missing),
                mismatch_rate=mismatch_rate,
            )
        if mismatch_rate > 0.001:
            LOGGER.error(
                "billing.reconciliation.threshold_exceeded",
                expected_count=len(expected_event_ids),
                missing_count=len(missing),
                mismatch_rate=mismatch_rate,
            )
        return ReconciliationResult(
            expected_count=len(expected_event_ids),
            missing_count=len(missing),
            mismatch_rate=mismatch_rate,
        )


async def run_billing_reconciliation(app: Any) -> ReconciliationResult:
    del app
    async with database.PlatformStaffAsyncSessionLocal() as session:
        return await BillingReconciliationJob(session=session).run_once([])


def build_billing_reconciliation_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    settings = app.state.settings
    if not isinstance(settings, PlatformSettings):
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_billing_reconciliation(app)

    scheduler.add_job(
        _run,
        "cron",
        hour=2,
        minute=0,
        id="billing.reconciliation",
        replace_existing=True,
    )
    return scheduler
