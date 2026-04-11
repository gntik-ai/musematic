from __future__ import annotations

from platform.accounts.repository import AccountsRepository
from platform.accounts.service import AccountsService
from platform.auth.dependencies import get_auth_service
from platform.auth.service import AuthService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_producer(request: Request) -> EventProducer | None:
    producer = request.app.state.clients.get("kafka")
    return cast(EventProducer | None, producer)


async def get_accounts_repository(
    session: AsyncSession = Depends(get_db),
) -> AccountsRepository:
    return AccountsRepository(session)


async def get_accounts_service(
    request: Request,
    repository: AccountsRepository = Depends(get_accounts_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> AccountsService:
    return AccountsService(
        repo=repository,
        redis=_get_redis(request),
        kafka_producer=_get_producer(request),
        auth_service=auth_service,
        settings=_get_settings(request),
    )
