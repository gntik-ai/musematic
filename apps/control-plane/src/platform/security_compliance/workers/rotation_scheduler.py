from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.security_compliance.services.secret_rotation_service import SecretRotationService


async def run_due_rotations(service: SecretRotationService) -> int:
    return len(await service.trigger_due())


def build_rotation_scheduler(
    service_factory: Callable[[], Awaitable[SecretRotationService]],
    *,
    interval_seconds: int,
) -> object:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone="UTC")

    async def _job() -> None:
        service = await service_factory()
        await run_due_rotations(service)

    scheduler.add_job(
        _job,
        "interval",
        seconds=interval_seconds,
        id="security-compliance-rotation-scheduler",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
