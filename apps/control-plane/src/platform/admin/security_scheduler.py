from __future__ import annotations

import time
from platform.admin.impersonation_service import ImpersonationService
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.notifications.dependencies import build_notifications_service
from typing import Any, cast

LOGGER = get_logger(__name__)

ADMIN_SECURITY_EXPIRY_INTERVAL_SECONDS = 60


async def run_admin_security_expiry_scan(app: Any) -> tuple[int, int]:
    started = time.perf_counter()
    settings = cast(PlatformSettings, app.state.settings)
    async with database.AsyncSessionLocal() as session:
        notifications = build_notifications_service(
            session=session,
            settings=settings,
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            workspaces_service=None,
            channel_router=None,
            secret_provider=getattr(app.state, "secret_provider", None),
        )
        two_person_auth = TwoPersonAuthService(session, settings)
        impersonation = ImpersonationService(
            session,
            settings,
            two_person_auth,
            notifications,
        )
        expired_2pa = await two_person_auth.expire_requests()
        expired_impersonations = await impersonation.expire_sessions()
        await session.commit()
    LOGGER.info(
        "admin_security_expiry_scan_completed",
        extra={
            "expired_2pa_requests": expired_2pa,
            "expired_impersonation_sessions": expired_impersonations,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    return expired_2pa, expired_impersonations


def build_admin_security_expiry_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_admin_security_expiry_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=ADMIN_SECURITY_EXPIRY_INTERVAL_SECONDS,
        id="admin-security-expiry-scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
