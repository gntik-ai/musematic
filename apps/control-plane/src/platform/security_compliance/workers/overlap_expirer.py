from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.security_compliance.services.secret_rotation_service import SecretRotationService


async def run_overlap_expiry(service: SecretRotationService) -> int:
    return len(await service.expire_overlaps())


def build_overlap_expirer(
    service_factory: Callable[[], Awaitable[SecretRotationService]],
) -> object:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone="UTC")

    async def _job() -> None:
        service = await service_factory()
        await run_overlap_expiry(service)

    scheduler.add_job(
        _job,
        "interval",
        seconds=30,
        id="security-compliance-overlap-expirer",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
