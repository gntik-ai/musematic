from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from platform.incident_response.repository import IncidentResponseRepository
from typing import Any, cast

LOGGER = get_logger(__name__)


async def run_runbook_freshness_scan(app: Any) -> int:
    settings = cast(PlatformSettings, app.state.settings)
    threshold = datetime.now(UTC) - timedelta(
        days=settings.incident_response.runbook_freshness_window_days
    )
    async with database.AsyncSessionLocal() as session:
        stale = await IncidentResponseRepository(session).mark_runbooks_stale(threshold)
    for runbook in stale:
        LOGGER.warning(
            "incident_response_runbook_stale",
            extra={
                "runbook_id": str(runbook.id),
                "scenario": runbook.scenario,
                "last_updated": runbook.updated_at.isoformat(),
            },
        )
    return len(stale)


def build_runbook_freshness_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_runbook_freshness_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        days=1,
        id="incident-response-runbook-freshness",
        replace_existing=True,
    )
    return scheduler
