from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform.common.config import PlatformSettings
from platform.main import _build_clients, _lifespan, create_app


class FakeClient:
    def __init__(self, *, has_close: bool = True, close_raises: bool = False) -> None:
        self.connected = False
        self.closed = False
        self.has_close = has_close
        self.close_raises = close_raises

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True
        if self.close_raises:
            raise RuntimeError("close failed")

    async def health_check(self) -> bool:
        return True


def test_build_clients_returns_expected_keys() -> None:
    clients = _build_clients(PlatformSettings())

    assert set(clients) >= {
        "redis",
        "kafka",
        "kafka_consumer",
        "qdrant",
        "runtime_controller",
        "simulation_controller",
    }


@pytest.mark.asyncio
async def test_lifespan_handles_clients_without_close_and_close_failures() -> None:
    app = SimpleNamespace(state=SimpleNamespace(clients={}))
    app.state.clients = {
        "redis": FakeClient(),
        "kafka_consumer": FakeClient(),
        "broken": SimpleNamespace(connect=lambda: _async_none()),
        "no_close": SimpleNamespace(connect=lambda: _async_none()),
        "close_error": FakeClient(close_raises=True),
    }

    async with _lifespan(app):
        assert app.state.degraded is False
        assert app.state.clients["redis"].connected is True


@pytest.mark.asyncio
async def test_create_app_non_api_profile_does_not_mount_protected_route(monkeypatch) -> None:
    monkeypatch.setattr("platform.main._build_clients", lambda settings: _fake_clients())
    monkeypatch.setattr("platform.api.health.database_health_check", lambda: _async_true())
    app = create_app(profile="worker", settings=PlatformSettings(PLATFORM_PROFILE="api"))

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/protected")

    assert app.state.settings.profile == "worker"
    assert "/api/v1/protected" not in {route.path for route in app.routes}
    assert response.status_code == 401


def _fake_clients() -> dict[str, FakeClient]:
    return {
        "redis": FakeClient(),
        "kafka": FakeClient(),
        "kafka_consumer": FakeClient(),
        "qdrant": FakeClient(),
        "neo4j": FakeClient(),
        "clickhouse": FakeClient(),
        "opensearch": FakeClient(),
        "minio": FakeClient(),
        "runtime_controller": FakeClient(),
        "reasoning_engine": FakeClient(),
        "sandbox_manager": FakeClient(),
        "simulation_controller": FakeClient(),
    }


async def _async_true() -> bool:
    return True


async def _async_none() -> None:
    return None
