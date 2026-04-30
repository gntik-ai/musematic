from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.secret_provider import MockSecretProvider, SecretProvider
from platform.connectors.repository import ConnectorsRepository
from platform.connectors.service import ConnectorsService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"])


def build_connectors_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
    secret_provider: SecretProvider | None = None,
) -> ConnectorsService:
    return ConnectorsService(
        repository=ConnectorsRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        secret_provider=secret_provider or MockSecretProvider(settings, validate_paths=False),
    )


async def get_connectors_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ConnectorsService:
    return build_connectors_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        object_storage=_get_object_storage(request),
        secret_provider=cast(
            SecretProvider,
            getattr(request.app.state, "secret_provider", None)
            or MockSecretProvider(_get_settings(request), validate_paths=False),
        ),
    )
