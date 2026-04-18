from __future__ import annotations

import platform.main as main_module
from platform.common.config import PlatformSettings
from platform.main import (
    _build_clients,
    _build_ibor_sync_scheduler,
    _lifespan,
    _refresh_ibor_sync_scheduler,
    create_app,
)
from types import SimpleNamespace

import httpx
import pytest


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
        "object_storage",
    }


@pytest.mark.asyncio
async def test_lifespan_handles_clients_without_close_and_close_failures(monkeypatch) -> None:
    app = SimpleNamespace(state=SimpleNamespace(clients={}))
    app.state.settings = PlatformSettings()
    app.state.clients = {
        "redis": FakeClient(),
        "kafka_consumer": FakeClient(),
        "broken": SimpleNamespace(connect=lambda: _async_none()),
        "no_close": SimpleNamespace(connect=lambda: _async_none()),
        "close_error": FakeClient(close_raises=True),
    }

    monkeypatch.setattr(main_module, "_load_trust_runtime_assets", _async_none_with_app)
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
        "object_storage": FakeClient(),
        "runtime_controller": FakeClient(),
        "reasoning_engine": FakeClient(),
        "sandbox_manager": FakeClient(),
        "simulation_controller": FakeClient(),
    }


async def _async_true() -> bool:
    return True


async def _async_none() -> None:
    return None


async def _async_none_with_app(app) -> None:
    del app
    return None


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs = [SimpleNamespace(id="ibor-sync-old"), SimpleNamespace(id="other-job")]
        self.removed: list[str] = []
        self.added: list[dict[str, object]] = []

    def get_jobs(self):
        return list(self.jobs)

    def remove_job(self, job_id: str) -> None:
        self.removed.append(job_id)
        self.jobs = [job for job in self.jobs if job.id != job_id]

    def add_job(self, func, trigger, **kwargs):
        self.added.append({"func": func, "trigger": trigger, **kwargs})


@pytest.mark.asyncio
async def test_refresh_ibor_sync_scheduler_reloads_enabled_connectors(monkeypatch) -> None:
    scheduler = FakeScheduler()
    connectors = [
        SimpleNamespace(id="11111111-1111-1111-1111-111111111111", cadence_seconds=300),
        SimpleNamespace(id="22222222-2222-2222-2222-222222222222", cadence_seconds=600),
    ]

    class SessionCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    app = SimpleNamespace(state=SimpleNamespace(ibor_sync_scheduler=scheduler))
    monkeypatch.setattr(main_module.database, "AsyncSessionLocal", lambda: SessionCtx())
    monkeypatch.setattr(
        main_module,
        "AuthRepository",
        lambda session: SimpleNamespace(list_enabled_connectors=lambda: _return(connectors)),
    )

    await _refresh_ibor_sync_scheduler(app)

    assert scheduler.removed == ["ibor-sync-old"]
    assert [item["id"] for item in scheduler.added] == [
        "ibor-sync-11111111-1111-1111-1111-111111111111",
        "ibor-sync-22222222-2222-2222-2222-222222222222",
    ]


def test_build_ibor_sync_scheduler_registers_loader_job() -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    scheduler = _build_ibor_sync_scheduler(app)

    if scheduler is None:
        pytest.skip("apscheduler is not installed in this environment")

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "ibor-sync-loader" in job_ids


async def _return(value):
    return value
