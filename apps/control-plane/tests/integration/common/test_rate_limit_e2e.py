from __future__ import annotations

import asyncio
from platform.common import database
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.middleware.rate_limit_middleware import RateLimitMiddleware
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


def _settings(
    auth_settings, *, database_url: str, redis_client, fail_open: bool = False
) -> PlatformSettings:
    return auth_settings.model_copy(
        update={
            "db": auth_settings.db.model_copy(update={"dsn": database_url}),
            "redis": auth_settings.redis.model_copy(
                update={"url": _redis_url(redis_client), "test_mode": "standalone"}
            ),
            "auth": auth_settings.auth.model_copy(
                update={
                    "jwt_secret_key": "b" * 32,
                    "jwt_private_key": "",
                    "jwt_public_key": "",
                    "jwt_algorithm": "HS256",
                }
            ),
            "api_governance": auth_settings.api_governance.model_copy(
                update={"rate_limiting_enabled": True, "rate_limiting_fail_open": fail_open}
            ),
        }
    )


def _token(secret: str, sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "principal_id": sub, "type": "access"}, secret, algorithm="HS256"
    )


def _build_app(settings: PlatformSettings, redis_client) -> FastAPI:
    database.configure_database(settings)
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {"redis": redis_client}
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sequential_default_tier_requests_hit_429(
    auth_settings,
    redis_client,
    migrated_database_url: str,
) -> None:
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client)
    token = _token(settings.auth.signing_key, str(uuid4()))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        responses = []
        for _ in range(320):
            responses.append(
                await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})
            )

    assert responses[299].status_code == 200
    assert responses[300].status_code == 429
    assert responses[318].status_code == 429
    assert responses[319].status_code == 429
    assert int(responses[300].headers["Retry-After"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_principals_are_isolated_under_concurrency(
    auth_settings,
    redis_client,
    migrated_database_url: str,
) -> None:
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client)
    token_a = _token(settings.auth.signing_key, str(uuid4()))
    token_b = _token(settings.auth.signing_key, str(uuid4()))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:

        async def _burst(token: str) -> list[int]:
            calls = [
                client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})
                for _ in range(10)
            ]
            responses = await asyncio.gather(*calls)
            return [response.status_code for response in responses]

        results_a, results_b = await asyncio.gather(_burst(token_a), _burst(token_b))

    assert results_a == [200] * 10
    assert results_b == [200] * 10


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fail_closed_and_fail_open_match_config(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    redis_client,
    migrated_database_url: str,
) -> None:
    settings_closed = _settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        fail_open=False,
    )
    app_closed = _build_app(settings_closed, redis_client)
    token_closed = _token(settings_closed.auth.verification_key, str(uuid4()))

    async def _raise(*args, **kwargs):
        raise RedisError("down")

    monkeypatch.setattr(redis_client, "check_multi_window_rate_limit", _raise)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_closed), base_url="http://testserver"
    ) as client:
        closed = await client.get(
            "/api/v1/limited", headers={"Authorization": f"Bearer {token_closed}"}
        )

    assert closed.status_code == 503
    assert closed.headers["Retry-After"] == "30"

    settings_open = _settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        fail_open=True,
    )
    app_open = _build_app(settings_open, redis_client)
    token_open = _token(settings_open.auth.verification_key, str(uuid4()))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_open), base_url="http://testserver"
    ) as client:
        opened = await client.get(
            "/api/v1/limited", headers={"Authorization": f"Bearer {token_open}"}
        )

    assert opened.status_code == 200
    assert opened.headers["X-RateLimit-Remaining"] == "unknown"
