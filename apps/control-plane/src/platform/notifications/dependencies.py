from __future__ import annotations

from platform.accounts.repository import AccountsRepository
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.repository import NotificationsRepository
from platform.notifications.service import AlertService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def build_notifications_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient,
    producer: EventProducer | None,
    workspaces_service: WorkspacesService | None,
) -> AlertService:
    return AlertService(
        repo=NotificationsRepository(session),
        accounts_repo=AccountsRepository(session),
        workspaces_service=workspaces_service,
        redis=redis_client,
        producer=producer,
        settings=settings,
        email_deliverer=EmailDeliverer(),
        webhook_deliverer=WebhookDeliverer(),
    )


async def get_notifications_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> AlertService:
    return build_notifications_service(
        session=session,
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        workspaces_service=workspaces_service,
    )
