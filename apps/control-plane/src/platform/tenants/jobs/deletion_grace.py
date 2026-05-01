from __future__ import annotations

from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.tenants.dns_automation import MockDnsAutomationClient
from platform.tenants.repository import TenantsRepository
from platform.tenants.service import TenantsService
from typing import Any, cast

from sqlalchemy import text

LOGGER = get_logger(__name__)


async def run_tenant_deletion_grace_scan(app: Any, *, limit: int = 50) -> int:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id
                    FROM tenants
                    WHERE status = 'pending_deletion'
                      AND scheduled_deletion_at <= now()
                    ORDER BY scheduled_deletion_at ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                    """
                ),
                {"limit": limit},
            )
        ).scalars().all()
        if not rows:
            return 0
        clients = getattr(app.state, "clients", {})
        producer = clients.get("kafka") if isinstance(clients, dict) else None
        service = TenantsService(
            session=session,
            repository=TenantsRepository(session),
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, producer),
            audit_chain=AuditChainService(
                AuditChainRepository(session),
                cast(PlatformSettings, app.state.settings),
                producer=producer if isinstance(producer, EventProducer) else None,
            ),
            dns_automation=MockDnsAutomationClient(),
            notifications=None,
            object_storage=None,
            redis_client=(
                cast(AsyncRedisClient | None, clients.get("redis"))
                if isinstance(clients, dict)
                else None
            ),
        )
        completed = 0
        for tenant_id in rows:
            try:
                await service.complete_deletion(tenant_id)
                completed += 1
            except Exception:
                await session.rollback()
                LOGGER.exception("Tenant deletion cascade failed", tenant_id=str(tenant_id))
        return completed


def build_tenant_deletion_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_tenant_deletion_grace_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=60,
        id="tenants-deletion-grace-scan",
        replace_existing=True,
    )
    return scheduler
