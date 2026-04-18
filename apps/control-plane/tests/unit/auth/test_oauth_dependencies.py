from __future__ import annotations

from platform.auth.dependencies_oauth import (
    build_oauth_service,
    get_oauth_service,
    rate_limit_callback,
)
from platform.auth.repository_oauth import OAuthRepository
from platform.auth.services.oauth_service import OAuthService
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from tests.auth_oauth_support import RateLimitRedisStub, RateLimitResultStub
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


def _request(settings, clients=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients=clients or {"redis": FakeAsyncRedisClient(), "kafka": RecordingProducer()},
            )
        ),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
    )


def test_build_oauth_service_returns_wired_service(auth_settings) -> None:
    request = _request(auth_settings)
    service = build_oauth_service(request, object())

    assert isinstance(service, OAuthService)
    assert isinstance(service.repository, OAuthRepository)
    assert service.redis_client is request.app.state.clients["redis"]
    assert service.producer is request.app.state.clients["kafka"]


@pytest.mark.asyncio
async def test_get_oauth_service_uses_builder(monkeypatch, auth_settings) -> None:
    sentinel = object()
    monkeypatch.setattr(
        "platform.auth.dependencies_oauth.build_oauth_service",
        lambda request, db: sentinel,
    )

    service = await get_oauth_service(request=_request(auth_settings), db=object())

    assert service is sentinel


@pytest.mark.asyncio
async def test_rate_limit_callback_allows_request(auth_settings) -> None:
    request = _request(
        auth_settings,
        clients={
            "redis": RateLimitRedisStub(RateLimitResultStub(True)),
            "kafka": RecordingProducer(),
        },
    )

    await rate_limit_callback(request)


@pytest.mark.asyncio
async def test_rate_limit_callback_raises_429_with_retry_after(auth_settings) -> None:
    redis = RateLimitRedisStub(RateLimitResultStub(False, retry_after_ms=1500))
    request = _request(auth_settings, clients={"redis": redis, "kafka": RecordingProducer()})

    with pytest.raises(HTTPException) as exc_info:
        await rate_limit_callback(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "2"}
    assert redis.calls[0][0] == "oauth-callback"
