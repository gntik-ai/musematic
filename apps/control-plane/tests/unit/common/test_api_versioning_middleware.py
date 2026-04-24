from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.api_versioning.decorator import deprecated_route
from platform.common.api_versioning.registry import clear_markers, mark_deprecated
from platform.common.middleware.api_versioning_middleware import ApiVersioningMiddleware

import httpx
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


def _build_app(*, legacy_sunset: datetime, successor: str | None = "/api/v2/new") -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiVersioningMiddleware)

    @app.get("/api/v1/current")
    async def current() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/legacy")
    @deprecated_route(sunset=legacy_sunset, successor=successor)
    async def legacy() -> dict[str, bool]:
        """Legacy route kept for compatibility."""
        return {"legacy": True}

    _register_deprecations(app)
    return app


@pytest.mark.asyncio
async def test_non_deprecated_route_has_no_headers() -> None:
    app = _build_app(legacy_sunset=datetime.now(UTC) + timedelta(hours=1))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/current")

    assert response.status_code == 200
    assert "Deprecation" not in response.headers
    assert "Sunset" not in response.headers
    assert "Link" not in response.headers


@pytest.mark.asyncio
async def test_deprecated_route_before_sunset_emits_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sunset = datetime.now(UTC) + timedelta(minutes=5)
    app = _build_app(legacy_sunset=sunset)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset - timedelta(minutes=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/legacy")

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"].endswith("GMT")
    assert response.headers["Link"] == '</api/v2/new>; rel="successor-version"'


@pytest.mark.asyncio
async def test_deprecated_route_without_successor_omits_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sunset = datetime.now(UTC) + timedelta(minutes=5)
    app = _build_app(legacy_sunset=sunset, successor=None)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset - timedelta(minutes=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/legacy")

    assert response.status_code == 200
    assert "Link" not in response.headers


@pytest.mark.asyncio
async def test_deprecated_route_after_sunset_returns_410(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sunset = datetime.now(UTC) + timedelta(minutes=5)
    app = _build_app(legacy_sunset=sunset)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset + timedelta(minutes=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/legacy")

    assert response.status_code == 410
    assert response.json()["error"] == "endpoint_sunset"
    assert response.json()["successor"] == "/api/v2/new"
    assert response.headers["Deprecation"] == "true"


@pytest.mark.asyncio
async def test_boundary_at_exact_sunset_returns_410(monkeypatch: pytest.MonkeyPatch) -> None:
    sunset = datetime.now(UTC) + timedelta(minutes=5)
    app = _build_app(legacy_sunset=sunset)
    monkeypatch.setattr(
        "platform.common.middleware.api_versioning_middleware.datetime",
        _FrozenDateTime,
    )
    _FrozenDateTime.current = sunset

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/legacy")

    assert response.status_code == 410


def test_openapi_marks_route_deprecated_and_mentions_successor() -> None:
    sunset = datetime.now(UTC) + timedelta(days=30)
    app = _build_app(legacy_sunset=sunset)

    operation = app.openapi()["paths"]["/api/v1/legacy"]["get"]
    assert operation["deprecated"] is True
    assert "Sunset on" in operation["description"]
    assert "/api/v2/new" in operation["description"]
