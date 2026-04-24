from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.api_versioning.decorator import deprecated_route
from platform.common.api_versioning.registry import clear_markers, mark_deprecated
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.middleware.api_versioning_middleware import ApiVersioningMiddleware

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute


class _FrozenDateTime(datetime):
    current: datetime = datetime.now(UTC)

    @classmethod
    def now(cls, tz: UTC | None = None) -> datetime:
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def _settings(auth_settings) -> PlatformSettings:
    return auth_settings.model_copy(
        update={
            "auth": auth_settings.auth.model_copy(
                update={
                    "jwt_secret_key": "c" * 32,
                    "jwt_private_key": "",
                    "jwt_public_key": "",
                    "jwt_algorithm": "HS256",
                }
            )
        }
    )


def _token(secret: str) -> str:
    return jwt.encode({"sub": "user-1", "type": "access"}, secret, algorithm="HS256")


def _register_deprecations(app: FastAPI) -> None:
    clear_markers()
    for route in app.routes:
        if isinstance(route, APIRoute):
            marker = getattr(route.endpoint, "__deprecated_marker__", None)
            if marker is None:
                continue
            sunset, successor = marker
            mark_deprecated(route.unique_id, sunset=sunset, successor=successor)
            route.deprecated = True


def _build_app(settings: PlatformSettings, sunset: datetime) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {}
    app.add_middleware(ApiVersioningMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/legacy-test")
    @deprecated_route(sunset=sunset, successor="/api/v2/new-test")
    async def legacy_test() -> dict[str, bool]:
        """Legacy integration endpoint."""
        return {"ok": True}

    _register_deprecations(app)
    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deprecation_headers_and_openapi_reflection(
    auth_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sunset = datetime.now(UTC) + timedelta(hours=1)
    settings = _settings(auth_settings)
    app = _build_app(settings, sunset)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset - timedelta(minutes=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/legacy-test",
            headers={"Authorization": f"Bearer {_token(settings.auth.signing_key)}"},
        )
        openapi = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == '</api/v2/new-test>; rel="successor-version"'
    operation = openapi.json()["paths"]["/api/v1/legacy-test"]["get"]
    assert operation["deprecated"] is True
    assert "Sunset on" in operation["description"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sunset_route_returns_410(
    auth_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sunset = datetime.now(UTC) + timedelta(minutes=10)
    settings = _settings(auth_settings)
    app = _build_app(settings, sunset)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset + timedelta(minutes=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/legacy-test",
            headers={"Authorization": f"Bearer {_token(settings.auth.signing_key)}"},
        )

    assert response.status_code == 410
    assert response.json() == {
        "error": "endpoint_sunset",
        "successor": "/api/v2/new-test",
        "sunset_date": sunset.isoformat(),
    }
