from __future__ import annotations

from platform.accounts.dependencies import get_accounts_service
from platform.accounts.service import AccountsService
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    producer = request.app.state.clients.get("kafka")
    return cast(EventProducer | None, producer)


def build_workspaces_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    accounts_service: AccountsService | None = None,
) -> WorkspacesService:
    return WorkspacesService(
        repo=WorkspacesRepository(session),
        settings=settings,
        kafka_producer=producer,
        accounts_service=accounts_service,
    )


async def get_workspaces_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> WorkspacesService:
    return build_workspaces_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        accounts_service=accounts_service,
    )
