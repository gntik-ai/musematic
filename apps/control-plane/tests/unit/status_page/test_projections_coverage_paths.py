from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.status_page import projections
from platform.status_page.projections import (
    StatusPageProjectionConsumer,
    _health_targets_from_env,
    _poll_all_targets,
    _should_recompose,
    _status_event_kind,
    build_status_page_scheduler,
    compose_polled_snapshot,
    compute_30d_uptime_rollup,
)
from platform.status_page.schemas import (
    ComponentStatus,
    OverallState,
    PlatformStatusSnapshotRead,
    SourceKind,
    UptimeSummary,
)
from platform.status_page.service import SnapshotWithSource
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest


class _ManagerStub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group: str, handler: object) -> None:
        self.subscriptions.append((topic, group, handler))


class _SessionContext:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _SessionContext:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeStatusPageService:
    instances: ClassVar[list[_FakeStatusPageService]] = []
    fail = False

    def __init__(self, **_kwargs: object) -> None:
        self.composed = 0
        self.dispatched: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    async def compose_current_snapshot(self, **_kwargs: object) -> None:
        self.composed += 1
        if self.fail:
            raise RuntimeError("compose failed")

    async def dispatch_event(self, kind: str, payload: dict[str, object]) -> None:
        self.dispatched.append((kind, payload))


def test_projection_registration_and_event_filters() -> None:
    manager = _ManagerStub()
    consumer = StatusPageProjectionConsumer(
        settings=SimpleNamespace(kafka=SimpleNamespace(consumer_group="workers")),
    )

    consumer.register(manager)  # type: ignore[arg-type]

    assert len(manager.subscriptions) == len(projections.STATUS_EVENT_TOPICS)
    assert _should_recompose(SimpleNamespace(event_type="incident.created"))
    assert not _should_recompose(SimpleNamespace(event_type="billing.created"))
    assert _status_event_kind(SimpleNamespace(event_type="maintenance.mode.enabled")) == (
        "maintenance.started"
    )
    assert _status_event_kind(SimpleNamespace(event_type="unknown")) is None


@pytest.mark.asyncio
async def test_projection_consumer_commits_and_rolls_back(monkeypatch) -> None:
    context = _SessionContext()
    monkeypatch.setattr(projections.database, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(projections, "StatusPageRepository", lambda _session: object())
    monkeypatch.setattr(projections, "StatusPageService", _FakeStatusPageService)
    _FakeStatusPageService.instances.clear()
    _FakeStatusPageService.fail = False
    consumer = StatusPageProjectionConsumer(
        settings=SimpleNamespace(kafka=SimpleNamespace(consumer_group="workers")),
    )

    await consumer.handle_event(
        SimpleNamespace(
            event_type="incident_response.incident.created",
            payload={"incident_id": "incident-1"},
        )
    )

    assert context.committed
    assert _FakeStatusPageService.instances[-1].dispatched == [
        ("incident.created", {"incident_id": "incident-1"})
    ]

    rollback_context = _SessionContext()
    monkeypatch.setattr(projections.database, "AsyncSessionLocal", lambda: rollback_context)
    _FakeStatusPageService.fail = True
    await consumer.handle_event(SimpleNamespace(event_type="maintenance.scheduled", payload={}))
    assert rollback_context.rolled_back

    before = len(_FakeStatusPageService.instances)
    await consumer.handle_event(SimpleNamespace(event_type="ignored.event", payload={}))
    assert len(_FakeStatusPageService.instances) == before


class _ClientStub:
    async def get(self, url: str) -> SimpleNamespace:
        if "broken" in url:
            raise httpx.ConnectError("offline")
        if "server" in url:
            return SimpleNamespace(status_code=503)
        if "degraded" in url and url.endswith("/healthz"):
            return SimpleNamespace(status_code=404)
        return SimpleNamespace(status_code=200)


@pytest.mark.asyncio
async def test_polling_and_rollup_paths(monkeypatch) -> None:
    now = datetime.now(UTC)
    results = await _poll_all_targets(
        _ClientStub(),  # type: ignore[arg-type]
        {
            "api": "https://ok.example.test",
            "web": "https://degraded.example.test",
            "worker": "https://server.example.test",
            "broken": "https://broken.example.test",
        },
        now=now,
    )
    assert [item["state"] for item in results] == [
        "operational",
        "degraded",
        "partial_outage",
        "partial_outage",
    ]

    monkeypatch.delenv("STATUS_PAGE_HEALTH_TARGETS", raising=False)
    assert _health_targets_from_env() is None
    monkeypatch.setenv("STATUS_PAGE_HEALTH_TARGETS", "{bad")
    assert _health_targets_from_env() is None
    monkeypatch.setenv("STATUS_PAGE_HEALTH_TARGETS", json.dumps(["not", "a", "dict"]))
    assert _health_targets_from_env() is None
    monkeypatch.setenv("STATUS_PAGE_HEALTH_TARGETS", json.dumps({"api": "http://api"}))
    assert _health_targets_from_env() == {"api": "http://api"}

    service = SimpleNamespace(calls=[])

    async def compose_current_snapshot(**kwargs: object) -> None:
        service.calls.append(kwargs)

    service.compose_current_snapshot = compose_current_snapshot
    async def poll_component_health(_targets=None):
        return results

    monkeypatch.setattr(projections, "poll_component_health", poll_component_health)
    await compose_polled_snapshot(service, targets={"api": "http://api"})  # type: ignore[arg-type]
    assert service.calls[-1]["source_kind"] is SourceKind.poll

    snapshot = PlatformStatusSnapshotRead(
        generated_at=now,
        source_kind=SourceKind.poll,
        overall_state=OverallState.operational,
        components=[
            ComponentStatus(
                id="api",
                name="API",
                state=OverallState.operational,
                last_check_at=now,
                uptime_30d_pct=None,
            )
        ],
        uptime_30d={"api": UptimeSummary(pct=98.5, incidents=2)},
    )

    async def get_public_snapshot() -> SnapshotWithSource:
        return SnapshotWithSource(snapshot, "redis")

    service.get_public_snapshot = get_public_snapshot
    await compute_30d_uptime_rollup(service)  # type: ignore[arg-type]
    assert service.calls[-1]["component_health"][0]["uptime_30d_pct"] == 100


def test_scheduler_builder(monkeypatch) -> None:
    class _Scheduler:
        def __init__(self, *, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[dict[str, object]] = []

        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    monkeypatch.setattr(
        projections,
        "import_module",
        lambda _name: SimpleNamespace(AsyncIOScheduler=_Scheduler),
    )

    scheduler = build_status_page_scheduler(object())
    assert scheduler.timezone == "UTC"
    assert [job["id"] for job in scheduler.jobs] == [
        "status-page-snapshot-poll",
        "status-page-uptime-rollup",
    ]
