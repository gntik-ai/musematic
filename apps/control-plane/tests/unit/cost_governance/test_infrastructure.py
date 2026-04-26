from __future__ import annotations

import builtins
import sys
from datetime import UTC, datetime
from decimal import Decimal
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.exceptions import ClickHouseClientError
from platform.cost_governance import clickhouse_setup
from platform.cost_governance.clickhouse_repository import (
    COST_EVENT_COLUMNS,
    ClickHouseCostRepository,
    cost_event_row,
)
from platform.cost_governance.exceptions import (
    BudgetNotConfiguredError,
    InvalidBudgetConfigError,
    WorkspaceCostBudgetExceededError,
)
from platform.cost_governance.schemas import (
    ChargebackReportRequest,
    OverrideIssueRequest,
    WorkspaceBudgetCreateRequest,
)
from platform.cost_governance.service import CostGovernanceService
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


def _stub_module(name: str, **attrs: Any) -> None:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


class AuditChainService:
    pass


class AlertService:
    pass


class CatalogService:
    pass


class WorkspacesService:
    pass


for package_name in (
    "platform.audit",
    "platform.model_catalog",
    "platform.notifications",
    "platform.workspaces",
):
    package = ModuleType(package_name)
    package.__path__ = []  # type: ignore[attr-defined]
    sys.modules[package_name] = package

_stub_module(
    "platform.audit.dependencies",
    get_audit_chain_service=lambda: None,
)
_stub_module("platform.audit.service", AuditChainService=AuditChainService)
_stub_module(
    "platform.model_catalog.dependencies",
    get_catalog_service=lambda: None,
)
_stub_module("platform.model_catalog.services", CatalogService=CatalogService)
_stub_module("platform.model_catalog.services.catalog_service", CatalogService=CatalogService)
_stub_module(
    "platform.notifications.dependencies",
    get_notifications_service=lambda: None,
)
_stub_module("platform.notifications.service", AlertService=AlertService)
_stub_module(
    "platform.workspaces.dependencies",
    get_workspaces_service=lambda: None,
)
_stub_module("platform.workspaces.service", WorkspacesService=WorkspacesService)

from platform.cost_governance import dependencies as deps  # noqa: E402
from platform.cost_governance.jobs import anomaly_job, forecast_job  # noqa: E402


class RecordingClickHouseClient:
    def __init__(self) -> None:
        self.inserted: list[tuple[str, list[dict[str, Any]], list[str]]] = []
        self.commands: list[str] = []
        self.queries: list[tuple[str, dict[str, Any] | None]] = []

    async def insert_batch(
        self,
        table: str,
        rows: list[dict[str, Any]],
        column_names: list[str],
    ) -> None:
        self.inserted.append((table, rows, column_names))

    async def execute_command(self, statement: str) -> None:
        self.commands.append(statement)

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.queries.append((sql, params))
        return [{"total_cost_cents": Decimal("42")}]


class FailingClickHouseClient(RecordingClickHouseClient):
    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del sql, params
        raise ClickHouseClientError("failed")


class FakeAsyncClickHouseClient(AsyncClickHouseClient):
    def __init__(self) -> None:
        pass


def _cost_row(workspace_id: UUID) -> dict[str, Any]:
    return cost_event_row(
        event_id=uuid4(),
        attribution_id=uuid4(),
        execution_id=uuid4(),
        workspace_id=workspace_id,
        agent_id=None,
        user_id=None,
        model_cost_cents=Decimal("10"),
        compute_cost_cents=Decimal("1"),
        storage_cost_cents=Decimal("2"),
        overhead_cost_cents=Decimal("3"),
        total_cost_cents=Decimal("16"),
        currency="USD",
        occurred_at=datetime(2026, 4, 1, 12),  # noqa: DTZ001
    )


@pytest.mark.asyncio
async def test_clickhouse_repository_queries_and_setup() -> None:
    workspace_id = uuid4()
    client = RecordingClickHouseClient()
    repository = ClickHouseCostRepository(
        client,  # type: ignore[arg-type]
        PlatformSettings(
            cost_governance={
                "attribution_clickhouse_batch_size": 1,
                "attribution_clickhouse_flush_interval_seconds": 0.01,
            }
        ),
    )
    row = _cost_row(workspace_id)

    await repository.insert_cost_events_batch([row])
    await repository.enqueue_cost_event(row)
    await repository.start()
    await repository.stop()
    empty_rollup = await repository.query_cost_rollups(
        [],
        ["workspace"],
        row["occurred_at"],
        row["occurred_at"],
    )
    assert empty_rollup == []
    await repository.query_cost_rollups(
        [workspace_id],
        ["workspace", "day", "unknown"],
        row["occurred_at"],
        row["occurred_at"],
    )
    await repository.query_cost_baseline(workspace_id, 3)
    await repository.query_workspace_history(workspace_id, 3)
    with pytest.raises(ClickHouseClientError):
        await ClickHouseCostRepository(FailingClickHouseClient()).query_workspace_history(
            workspace_id,
            1,
        )
    await clickhouse_setup.run_setup(client)  # type: ignore[arg-type]

    assert client.inserted[0] == ("cost_events", [row], COST_EVENT_COLUMNS)
    assert row["cost_type"] == "model"
    assert row["occurred_at"].tzinfo == UTC
    assert len(client.commands) == 5
    assert any("toStartOfDay(occurred_at)" in query for query, _params in client.queries)


@pytest.mark.asyncio
async def test_cost_governance_service_orchestrates_summary_and_thresholds() -> None:
    workspace_id = uuid4()
    other_id = uuid4()

    class Repository:
        async def aggregate_attributions(
            self,
            workspace_id: UUID,
            group_by: list[str],
            since: datetime,
            until: datetime,
        ) -> list[dict[str, Decimal]]:
            del workspace_id, group_by, since, until
            return [{"total_cost_cents": Decimal("100")}, {"total_cost_cents": Decimal("50")}]

        async def list_workspace_ids_with_costs(self) -> list[UUID]:
            return [workspace_id, other_id]

    class Budget:
        async def evaluate_thresholds(self, candidate: UUID) -> list[UUID]:
            return [candidate]

    service = CostGovernanceService(
        attribution_service=object(),
        chargeback_service=object(),
        budget_service=Budget(),
        forecast_service=object(),
        anomaly_service=object(),
        repository=Repository(),
    )

    summary = await service.get_workspace_cost_summary(workspace_id, "weekly")
    assert summary["total_cost_usd"] == 1.5
    assert await service.evaluate_thresholds(workspace_id) == [workspace_id]
    assert await service.evaluate_thresholds() == [workspace_id, other_id]
    assert await service.handle_workspace_archived(workspace_id) is None


@pytest.mark.asyncio
async def test_dependency_builders_reuse_settings_and_clients() -> None:
    settings = PlatformSettings()
    redis_client = object()
    kafka = object()
    clickhouse = FakeAsyncClickHouseClient()
    state = SimpleNamespace(settings=settings, clients={"redis": redis_client, "kafka": kafka})
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    assert deps.get_redis_cost_client(request) is redis_client  # type: ignore[arg-type]
    assert deps.get_clickhouse_cost_repository(request) is None  # type: ignore[arg-type]
    existing = ClickHouseCostRepository(RecordingClickHouseClient())  # type: ignore[arg-type]
    state.cost_clickhouse_repository = existing
    assert deps.get_clickhouse_cost_repository(request) is existing  # type: ignore[arg-type]
    del state.cost_clickhouse_repository
    state.clients["clickhouse"] = clickhouse
    assert deps.get_clickhouse_cost_repository(request) is state.cost_clickhouse_repository  # type: ignore[arg-type]

    budget = deps.build_budget_service(
        repository=object(),  # type: ignore[arg-type]
        redis_client=None,
        settings=settings,
        producer=None,
        audit_chain_service=None,
        alert_service=None,
        workspaces_service=None,
    )
    assert budget.settings is settings
    built = deps.build_cost_governance_service(
        session=object(),  # type: ignore[arg-type]
        settings=settings,
        producer=None,
        redis_client=None,
        clickhouse_repository=None,
    )
    assert built.budget_service.settings is settings

    session = object()
    assert await deps.get_budget_service(request, session, None, None, None, None)  # type: ignore[arg-type]
    assert await deps.get_cost_attribution_service(request, session, None, None, budget)  # type: ignore[arg-type]
    assert await deps.get_chargeback_service(request, session, None, None, None)  # type: ignore[arg-type]
    assert await deps.get_forecast_service(request, session, None)  # type: ignore[arg-type]
    assert await deps.get_anomaly_service(request, session, None, None, None)  # type: ignore[arg-type]
    assert await deps.get_cost_governance_service(
        request,  # type: ignore[arg-type]
        session,
        None,
        None,
        None,
        None,
        None,
        None,
    )


class SessionContext:
    def __init__(self, session: SimpleNamespace) -> None:
        self.session = session

    async def __aenter__(self) -> SimpleNamespace:
        return self.session

    async def __aexit__(self, *exc: object) -> None:
        return None


class SessionFactory:
    def __init__(self) -> None:
        self.sessions: list[SimpleNamespace] = []

    def __call__(self) -> SessionContext:
        session = SimpleNamespace(commits=0, rollbacks=0)

        async def commit() -> None:
            session.commits += 1

        async def rollback() -> None:
            session.rollbacks += 1

        session.commit = commit
        session.rollback = rollback
        self.sessions.append(session)
        return SessionContext(session)


def _app() -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(settings=PlatformSettings(), clients={"kafka": None, "redis": None})
    )


@pytest.mark.asyncio
async def test_forecast_and_anomaly_jobs_commit_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_ids = [uuid4(), uuid4(), uuid4()]

    class Repository:
        def __init__(self, session: object) -> None:
            del session

        async def list_workspace_ids_with_costs(self) -> list[UUID]:
            return workspace_ids

    class ForecastService:
        async def compute_forecast(self, workspace_id: UUID) -> None:
            if workspace_id == workspace_ids[-1]:
                raise RuntimeError("boom")

    class AnomalyService:
        async def detect(self, workspace_id: UUID) -> None:
            if workspace_id == workspace_ids[1]:
                raise anomaly_job.InsufficientHistoryError()
            if workspace_id == workspace_ids[2]:
                raise RuntimeError("boom")

    def build_service(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            forecast_service=ForecastService(),
            anomaly_service=AnomalyService(),
        )

    forecast_sessions = SessionFactory()
    monkeypatch.setattr(forecast_job.database, "AsyncSessionLocal", forecast_sessions)
    monkeypatch.setattr(forecast_job, "CostGovernanceRepository", Repository)
    monkeypatch.setattr(forecast_job, "build_cost_governance_service", build_service)
    await forecast_job.run_forecast_evaluation(_app())

    anomaly_sessions = SessionFactory()
    monkeypatch.setattr(anomaly_job.database, "AsyncSessionLocal", anomaly_sessions)
    monkeypatch.setattr(anomaly_job, "CostGovernanceRepository", Repository)
    monkeypatch.setattr(anomaly_job, "build_cost_governance_service", build_service)
    await anomaly_job.run_anomaly_evaluation(_app())

    assert sum(session.commits for session in forecast_sessions.sessions) == 2
    assert sum(session.rollbacks for session in forecast_sessions.sessions) == 1
    assert sum(session.commits for session in anomaly_sessions.sessions) == 1
    assert sum(session.rollbacks for session in anomaly_sessions.sessions) == 2


def test_schedulers_handle_missing_and_available_apscheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert forecast_job.build_forecast_scheduler(_app()) is None
    assert anomaly_job.build_anomaly_scheduler(_app()) is None

    class Scheduler:
        def __init__(self, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[dict[str, Any]] = []

        def add_job(self, func: Any, trigger: str, **kwargs: Any) -> None:
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            return SimpleNamespace(AsyncIOScheduler=Scheduler)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    forecast_scheduler = forecast_job.build_forecast_scheduler(_app())
    anomaly_scheduler = anomaly_job.build_anomaly_scheduler(_app())

    assert forecast_scheduler.timezone == "UTC"
    assert anomaly_scheduler.jobs[0]["id"] == "cost-governance-anomaly-evaluation"


@pytest.mark.asyncio
async def test_scheduler_job_callbacks_execute_configured_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Scheduler:
        def __init__(self, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[dict[str, Any]] = []

        def add_job(self, func: Any, trigger: str, **kwargs: Any) -> None:
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            return SimpleNamespace(AsyncIOScheduler=Scheduler)
        return original_import(name, *args, **kwargs)

    calls: list[str] = []

    async def run_forecast(app: Any) -> None:
        del app
        calls.append("forecast")

    async def run_anomaly(app: Any) -> None:
        del app
        calls.append("anomaly")

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(forecast_job, "run_forecast_evaluation", run_forecast)
    monkeypatch.setattr(anomaly_job, "run_anomaly_evaluation", run_anomaly)

    forecast_scheduler = forecast_job.build_forecast_scheduler(_app())
    anomaly_scheduler = anomaly_job.build_anomaly_scheduler(_app())
    await forecast_scheduler.jobs[0]["func"]()
    await anomaly_scheduler.jobs[0]["func"]()

    assert calls == ["forecast", "anomaly"]


def test_schema_validators_and_exceptions_cover_error_paths() -> None:
    with pytest.raises(ValueError, match="thresholds must be sorted"):
        WorkspaceBudgetCreateRequest(
            period_type="monthly",
            budget_cents=1,
            soft_alert_thresholds=[80, 50],
        )
    with pytest.raises(ValueError, match="thresholds must be between"):
        WorkspaceBudgetCreateRequest(
            period_type="monthly",
            budget_cents=1,
            soft_alert_thresholds=[0],
        )
    with pytest.raises(ValueError, match="since must be less"):
        ChargebackReportRequest(
            since=datetime(2026, 4, 2, tzinfo=UTC),
            until=datetime(2026, 4, 1, tzinfo=UTC),
        )

    assert OverrideIssueRequest(reason="  urgent  ").reason == "urgent"
    assert BudgetNotConfiguredError().code == "BUDGET_NOT_CONFIGURED"
    assert InvalidBudgetConfigError("bad").code == "INVALID_BUDGET_CONFIG"
    exceeded = WorkspaceCostBudgetExceededError(
        workspace_id="workspace",
        override_endpoint="/override",
    )
    assert exceeded.code == "WORKSPACE_COST_BUDGET_EXCEEDED"
