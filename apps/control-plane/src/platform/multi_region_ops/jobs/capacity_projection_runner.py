from __future__ import annotations

from platform.incident_response.trigger_interface import get_incident_trigger
from platform.multi_region_ops.services.capacity_service import CapacityService
from typing import Any


def build_capacity_projection_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio", fromlist=["AsyncIOScheduler"]
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        service = CapacityService(
            settings=app.state.settings,
            incident_trigger=get_incident_trigger(),
        )
        await service.evaluate_saturation()

    scheduler.add_job(
        _run,
        "interval",
        seconds=app.state.settings.multi_region_ops.capacity_projection_interval_seconds,
        id="multi-region-capacity-projection",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
