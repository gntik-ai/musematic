from __future__ import annotations

from platform.api import health as health_module
from platform.common.config import PlatformSettings
from platform.main import create_app

import httpx
import pytest


class FakeClient:
    def __init__(self, healthy: bool = True, fail_connect: bool = False) -> None:
        self.healthy = healthy
        self.fail_connect = fail_connect
        self.closed = False

    async def connect(self) -> None:
        if self.fail_connect:
            raise RuntimeError("connect failed")

    async def close(self) -> None:
        self.closed = True

    async def health_check(self) -> bool:
        return self.healthy


def _clients(
    *,
    redis: bool = True,
    postgres: bool = True,
    fail_connect: str | None = None,
) -> dict[str, FakeClient]:
    names = [
        "redis",
        "kafka",
        "kafka_consumer",
        "qdrant",
        "neo4j",
        "clickhouse",
        "opensearch",
        "object_storage",
        "runtime_controller",
        "reasoning_engine",
        "sandbox_manager",
        "simulation_controller",
    ]
    clients: dict[str, FakeClient] = {}
    for name in names:
        clients[name] = FakeClient(healthy=True, fail_connect=name == fail_connect)
    clients["redis"].healthy = redis
    return clients


@pytest.mark.asyncio
async def test_health_endpoint_reports_healthy(monkeypatch) -> None:
    monkeypatch.setattr("platform.main._build_clients", lambda settings: _clients())
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(True))
    app = create_app(settings=PlatformSettings(PLATFORM_PROFILE="api"))

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")
            response_healthz = await client.get("/healthz")
            response_api_healthz = await client.get("/api/v1/healthz")

    payload = response.json()
    assert response.status_code == 200
    assert response_healthz.status_code == 200
    assert response_api_healthz.status_code == 200
    assert response_healthz.json() == payload
    assert response_api_healthz.json() == payload
    assert payload["status"] == "healthy"
    assert payload["profile"] == "api"
    assert set(payload["dependencies"]) >= {"postgresql", "redis", "kafka"}


@pytest.mark.asyncio
async def test_health_endpoint_reports_degraded_and_unhealthy(monkeypatch) -> None:
    monkeypatch.setattr("platform.main._build_clients", lambda settings: _clients(redis=False))
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(True))
    app = create_app(settings=PlatformSettings())

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            degraded = (await client.get("/health")).json()

    monkeypatch.setattr("platform.main._build_clients", lambda settings: _clients())
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(False))
    app = create_app(settings=PlatformSettings())

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            unhealthy = (await client.get("/health")).json()

    assert degraded["status"] == "degraded"
    assert degraded["dependencies"]["redis"]["status"] == "unhealthy"
    assert unhealthy["status"] == "unhealthy"
    assert unhealthy["dependencies"]["postgresql"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_lifespan_marks_degraded_when_startup_connect_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda settings: _clients(fail_connect="redis"),
    )
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_bool(True))
    app = create_app(settings=PlatformSettings())

    async with app.router.lifespan_context(app):
        assert app.state.degraded is True
        assert "redis" in app.state.startup_errors


@pytest.mark.asyncio
async def test_health_helpers_cover_error_and_status_normalization() -> None:
    async def raises() -> bool:
        raise RuntimeError("boom")

    unhealthy = await health_module._run_check(raises)

    class StatusObject:
        status = "green"

    assert unhealthy.status == "unhealthy"
    assert health_module._is_healthy({"status": "ok"}) is True
    assert health_module._is_healthy({"status": "down"}) is False
    assert health_module._is_healthy(StatusObject()) is True
    assert health_module._is_healthy(1) is True


async def _async_bool(value: bool) -> bool:
    return value
