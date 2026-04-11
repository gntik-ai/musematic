from __future__ import annotations

from platform.accounts.dependencies import (
    _get_producer,
    _get_redis,
    _get_settings,
    get_accounts_repository,
    get_accounts_service,
)
from platform.accounts.repository import AccountsRepository
from platform.accounts.service import AccountsService
from platform.common.config import PlatformSettings
from types import SimpleNamespace

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


def _request(settings: PlatformSettings, redis_client, producer) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"redis": redis_client, "kafka": producer},
            )
        )
    )


def test_internal_dependency_helpers_read_from_app_state(auth_settings) -> None:
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    request = _request(auth_settings, redis_client, producer)

    assert _get_settings(request) is auth_settings
    assert _get_redis(request) is redis_client
    assert _get_producer(request) is producer


@pytest.mark.asyncio
async def test_accounts_dependency_factories_build_repository_and_service(auth_settings) -> None:
    session = object()
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    auth_service = object()
    request = _request(auth_settings, redis_client, producer)

    repository = await get_accounts_repository(session=session)
    service = await get_accounts_service(
        request=request,
        repository=repository,
        auth_service=auth_service,
    )

    assert isinstance(repository, AccountsRepository)
    assert repository.session is session
    assert isinstance(service, AccountsService)
    assert service.repo is repository
    assert service.redis is redis_client
    assert service.kafka_producer is producer
    assert service.auth_service is auth_service
