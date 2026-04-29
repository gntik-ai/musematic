from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.logging import get_logger
from platform.incident_response.trigger_interface import get_incident_trigger
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.services.maintenance_mode_service import MaintenanceModeService
from typing import Any

LOGGER = get_logger(__name__)


def build_maintenance_window_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio", fromlist=["AsyncIOScheduler"]
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        settings = app.state.settings
        async with database.AsyncSessionLocal() as session:
            repository = MultiRegionOpsRepository(session)
            service = MaintenanceModeService(
                repository=repository,
                settings=settings,
                redis_client=app.state.clients.get("redis"),
                producer=app.state.clients.get("kafka"),
                incident_trigger=get_incident_trigger(),
                audit_chain_service=build_audit_chain_service(
                    session,
                    settings,
                    app.state.clients.get("kafka"),
                ),
            )
            now = datetime.now(UTC)
            scheduled = await repository.list_windows(status="scheduled", until=now)
            for window in scheduled:
                if window.starts_at <= now:
                    await service.enable(window.id)
            active = await repository.list_windows(status="active")
            for window in active:
                if window.ends_at <= now:
                    await service.disable(window.id, disable_kind="scheduled")
            await session.commit()

    scheduler.add_job(
        _run,
        "interval",
        seconds=30,
        id="multi-region-maintenance-window-runner",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
