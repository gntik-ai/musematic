from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.main import create_app
from uuid import UUID

import httpx
import jwt
import pytest
from fastapi import FastAPI


class FakeClient:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


def _fake_clients() -> dict[str, FakeClient]:
    return {
        "redis": FakeClient(),
        "kafka": FakeClient(),
        "kafka_consumer": FakeClient(),
        "qdrant": FakeClient(),
        "neo4j": FakeClient(),
        "clickhouse": FakeClient(),
        "opensearch": FakeClient(),
        "object_storage": FakeClient(),
        "runtime_controller": FakeClient(),
        "reasoning_engine": FakeClient(),
        "sandbox_manager": FakeClient(),
        "simulation_controller": FakeClient(),
    }


def _app(monkeypatch, settings: PlatformSettings):
    monkeypatch.setattr("platform.main._build_clients", lambda resolved: _fake_clients())
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(True))
    return create_app(settings=settings)


@pytest.mark.asyncio
async def test_health_is_auth_exempt_and_generates_correlation_headers(monkeypatch) -> None:
    app = _app(
        monkeypatch, PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    UUID(response.headers["X-Correlation-ID"])
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_correlation_header_is_propagated(monkeypatch) -> None:
    app = _app(
        monkeypatch, PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health", headers={"X-Correlation-ID": "test-123"})

    assert response.headers["X-Correlation-ID"] == "test-123"


@pytest.mark.asyncio
async def test_protected_route_requires_auth(monkeypatch) -> None:
    app = _app(
        monkeypatch, PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_valid_and_expired_jwts(monkeypatch) -> None:
    secret = "a" * 32
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY=secret, AUTH_JWT_ALGORITHM="HS256")
    app = _app(monkeypatch, settings)
    valid_token = jwt.encode({"sub": "user-1"}, secret, algorithm="HS256")
    expired_token = jwt.encode(
        {"sub": "user-1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        secret,
        algorithm="HS256",
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            success = await client.get(
                "/api/v1/protected", headers={"Authorization": f"Bearer {valid_token}"}
            )
            expired = await client.get(
                "/api/v1/protected", headers={"Authorization": f"Bearer {expired_token}"}
            )

    assert success.status_code == 200
    assert success.json()["user"]["sub"] == "user-1"
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_invalid_jwt_returns_unauthorized(monkeypatch) -> None:
    app = _app(
        monkeypatch, PlatformSettings(AUTH_JWT_SECRET_KEY="a" * 32, AUTH_JWT_ALGORITHM="HS256")
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/protected", headers={"Authorization": "Bearer invalid"}
            )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def _async_bool(value: bool) -> bool:
    return value


@pytest.mark.asyncio
async def test_public_oauth_routes_are_auth_exempt_but_link_remains_protected() -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/auth/oauth/providers")
    async def oauth_providers() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/auth/oauth/google/authorize")
    async def oauth_authorize() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/auth/oauth/google/callback")
    async def oauth_callback() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/auth/oauth/google/link")
    async def oauth_link() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        providers = await client.get("/api/v1/auth/oauth/providers")
        authorize = await client.get("/api/v1/auth/oauth/google/authorize")
        callback = await client.get("/api/v1/auth/oauth/google/callback")
        link = await client.post("/api/v1/auth/oauth/google/link")

    assert providers.status_code == 200
    assert authorize.status_code == 200
    assert callback.status_code == 200
    assert link.status_code == 401
    assert link.json()["error"]["code"] == "UNAUTHORIZED"
