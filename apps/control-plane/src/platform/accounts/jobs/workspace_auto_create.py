"""Deferred default-workspace auto-creation retry for UPD-048 FR-004."""

from __future__ import annotations

from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.service import WorkspacesService
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text

LOGGER = get_logger(__name__)


async def run_workspace_auto_create_retry(app: Any) -> None:
    settings = cast(PlatformSettings, app.state.settings)
    async with database.AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT au.id, au.display_name
                    FROM accounts_users au
                    WHERE au.status = 'active'
                      AND NOT EXISTS (
                        SELECT 1
                        FROM workspaces_workspaces ww
                        WHERE ww.owner_id = au.id
                          AND ww.is_default = true
                      )
                    LIMIT 100
                    """
                )
            )
        ).mappings().all()
        service = WorkspacesService(
            repo=WorkspacesRepository(session),
            settings=settings,
            kafka_producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            subscription_service=SubscriptionService(
                session=session,
                subscriptions=SubscriptionsRepository(session),
                plans=PlansRepository(session),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            ),
        )
        created = 0
        for row in rows:
            try:
                await service.create_default_workspace(
                    UUID(str(row["id"])),
                    str(row["display_name"]),
                )
                created += 1
            except Exception:
                LOGGER.exception(
                    "Default workspace retry failed",
                    extra={"user_id": str(row["id"])},
                )
        await session.commit()
    if created:
        LOGGER.info(
            "Default workspace retry completed",
            extra={"workspace_created_count": created},
        )


def build_workspace_auto_create_retry(app: Any) -> Any | None:
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
        await run_workspace_auto_create_retry(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=settings.SIGNUP_AUTO_CREATE_RETRY_SECONDS,
        id="accounts-default-workspace-auto-create",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
