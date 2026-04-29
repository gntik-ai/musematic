from __future__ import annotations

import builtins
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.multi_region_ops.jobs import (
    capacity_projection_runner,
    maintenance_window_runner,
    replication_probe_runner,
)
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


class FakeScheduler:
    def __init__(self, *, timezone: str) -> None:
        self.timezone = timezone
        self.jobs: list[dict[str, Any]] = []

    def add_job(self, func: Any, trigger: str, **kwargs: Any) -> None:
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


def _install_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            return SimpleNamespace(AsyncIOScheduler=FakeScheduler)
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def _block_scheduler_import(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            raise ImportError("apscheduler unavailable")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_scheduler_builders_return_none_without_apscheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_scheduler_import(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings()))

    assert capacity_projection_runner.build_capacity_projection_scheduler(app) is None
    assert replication_probe_runner.build_replication_probe_scheduler(app) is None


@pytest.mark.asyncio
async def test_maintenance_window_scheduler_enables_and_disables_due_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scheduler(monkeypatch)
    now = datetime.now(UTC)
    scheduled = SimpleNamespace(id=uuid4(), starts_at=now - timedelta(minutes=1))
    active = SimpleNamespace(id=uuid4(), ends_at=now - timedelta(seconds=1))
    enabled: list[Any] = []
    disabled: list[tuple[Any, str]] = []
    session = FakeSession()

    class FakeRepository:
        def __init__(self, db_session: FakeSession) -> None:
            assert db_session is session

        async def list_windows(self, *, status: str, until: datetime | None = None) -> list[Any]:
            if status == "scheduled":
                assert until is not None
                return [scheduled]
            if status == "active":
                return [active]
            return []

    class FakeMaintenanceService:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["settings"].feature_multi_region is False

        async def enable(self, window_id: Any) -> None:
            enabled.append(window_id)

        async def disable(self, window_id: Any, *, disable_kind: str) -> None:
            disabled.append((window_id, disable_kind))

    monkeypatch.setattr(maintenance_window_runner.database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(maintenance_window_runner, "MultiRegionOpsRepository", FakeRepository)
    monkeypatch.setattr(maintenance_window_runner, "MaintenanceModeService", FakeMaintenanceService)
    monkeypatch.setattr(maintenance_window_runner, "get_incident_trigger", lambda: object())
    monkeypatch.setattr(
        maintenance_window_runner, "build_audit_chain_service", lambda *args: object()
    )
    app = SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings(), clients={}))

    scheduler = maintenance_window_runner.build_maintenance_window_scheduler(app)
    assert isinstance(scheduler, FakeScheduler)
    await scheduler.jobs[0]["func"]()

    assert enabled == [scheduled.id]
    assert disabled == [(active.id, "scheduled")]
    assert session.committed is True


@pytest.mark.asyncio
async def test_replication_probe_scheduler_builds_registry_and_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scheduler(monkeypatch)
    session = FakeSession()
    probed: list[bool] = []

    class FakeMonitor:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["probe_registry"].missing_components() == ()

        async def probe_all(self) -> None:
            probed.append(True)

    monkeypatch.setattr(replication_probe_runner.database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(replication_probe_runner, "ReplicationMonitor", FakeMonitor)
    monkeypatch.setattr(replication_probe_runner, "get_incident_trigger", lambda: object())
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=PlatformSettings(feature_multi_region=True),
            clients={"redis": object(), "kafka": object(), "clickhouse": object()},
        )
    )

    scheduler = replication_probe_runner.build_replication_probe_scheduler(app)
    assert isinstance(scheduler, FakeScheduler)
    await scheduler.jobs[0]["func"]()

    assert probed == [True]
    assert session.committed is True


@pytest.mark.asyncio
async def test_capacity_projection_scheduler_runs_capacity_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scheduler(monkeypatch)
    evaluated: list[bool] = []

    class FakeCapacityService:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["settings"].feature_multi_region is False

        async def evaluate_saturation(self) -> None:
            evaluated.append(True)

    monkeypatch.setattr(capacity_projection_runner, "CapacityService", FakeCapacityService)
    monkeypatch.setattr(capacity_projection_runner, "get_incident_trigger", lambda: object())
    app = SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings()))

    scheduler = capacity_projection_runner.build_capacity_projection_scheduler(app)
    assert isinstance(scheduler, FakeScheduler)
    await scheduler.jobs[0]["func"]()

    assert evaluated == [True]
