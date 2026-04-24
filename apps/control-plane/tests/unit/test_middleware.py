from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.main import create_app
from typing import Any
from uuid import UUID

import httpx
import jwt
import pytest
from fastapi import FastAPI, Request


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
    if monkeypatch is not None:
        monkeypatch.setattr("platform.main._build_clients", lambda resolved: _fake_clients())
        monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(True))
    else:
        import platform.main as main_module

        main_module._build_clients = lambda resolved: _fake_clients()
        import platform.api.health as health_module

        health_module.database_health_check = lambda: _async_bool(True)
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
    settings = PlatformSettings(
        AUTH_JWT_SECRET_KEY=secret,
        AUTH_JWT_ALGORITHM="HS256",
        api_governance={"rate_limiting_enabled": False},
    )
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
    assert success.json()["user"]["principal_type"] == "user"
    assert success.json()["user"]["principal_id"] == "user-1"
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


@pytest.mark.asyncio
async def test_api_key_and_invitation_paths_in_auth_middleware(monkeypatch) -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/accounts/invitations/{token}")
    async def invitation_get(token: str) -> dict[str, str]:
        return {"token": token}

    @app.post("/api/v1/accounts/invitations/{token}/accept")
    async def invitation_accept(token: str) -> dict[str, str]:
        return {"token": token}

    @app.get("/api/v1/protected")
    async def protected(request: Request):
        return {"user": request.state.user}

    async def _valid_identity(request, api_key: str):
        del request, api_key
        return {"sub": "api-key-user"}

    async def _invalid_identity(request, api_key: str):
        del request, api_key
        return None

    monkeypatch.setattr("platform.common.auth_middleware.resolve_api_key_identity", _valid_identity)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        invitation = await client.get("/api/v1/accounts/invitations/demo-token")
        accepted = await client.post("/api/v1/accounts/invitations/demo-token/accept")
        api_key_ok = await client.get("/api/v1/protected", headers={"X-API-Key": "valid"})

    monkeypatch.setattr(
        "platform.common.auth_middleware.resolve_api_key_identity",
        _invalid_identity,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        api_key_bad = await client.get("/api/v1/protected", headers={"X-API-Key": "bad"})

    assert invitation.status_code == 200
    assert accepted.status_code == 200
    assert api_key_ok.status_code == 200
    assert api_key_ok.json()["user"]["sub"] == "api-key-user"
    assert api_key_ok.json()["user"]["principal_type"] == "service_account"
    assert api_key_ok.json()["user"]["principal_id"] == "api-key-user"
    assert api_key_bad.status_code == 401
    assert api_key_bad.json()["error"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_refresh_token_type_is_rejected_by_auth_middleware() -> None:
    secret = "a" * 32
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY=secret, AUTH_JWT_ALGORITHM="HS256")
    app = _app(None, settings)
    refresh_token = jwt.encode({"sub": "user-1", "type": "refresh"}, secret, algorithm="HS256")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/protected", headers={"Authorization": f"Bearer {refresh_token}"}
            )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_a2a_paths_are_auth_exempt_in_middleware() -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(AuthMiddleware)

    @app.get("/.well-known/agent.json")
    async def agent_card() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/a2a/tasks")
    async def create_task() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/a2a/tasks/demo/stream")
    async def stream_task() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        card = await client.get("/.well-known/agent.json")
        task = await client.post("/api/v1/a2a/tasks")
        stream = await client.get("/api/v1/a2a/tasks/demo/stream")

    assert card.status_code == 200
    assert task.status_code == 200
    assert stream.status_code == 200


@pytest.mark.asyncio
async def test_new_openapi_paths_are_auth_exempt() -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(AuthMiddleware)

    @app.get("/api/openapi.json")
    async def openapi_json() -> dict[str, str]:
        return {"schema": "ok"}

    @app.get("/api/docs")
    async def docs() -> dict[str, str]:
        return {"docs": "ok"}

    @app.get("/api/redoc")
    async def redoc() -> dict[str, str]:
        return {"redoc": "ok"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        openapi_response = await client.get("/api/openapi.json")
        docs_response = await client.get("/api/docs")
        redoc_response = await client.get("/api/redoc")

    assert openapi_response.status_code == 200
    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200


@pytest.mark.asyncio
async def test_a2a_paths_capture_external_principal_type_when_client_cert_present() -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(AuthMiddleware)

    @app.post("/api/v1/a2a/tasks")
    async def create_task(
        request: Request,
    ) -> dict[str, Any] | None:
        return getattr(request.state, "user", None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/a2a/tasks",
            headers={"X-Forwarded-Client-Cert": "demo-cert"},
        )

    assert response.status_code == 200
    assert response.json()["principal_type"] == "external_a2a"
    assert response.json()["identity_type"] == "external_a2a"
    assert response.json()["principal_id"]
