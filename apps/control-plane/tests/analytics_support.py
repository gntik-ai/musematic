from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.analytics.models import CostModel
from platform.analytics.schemas import (
    AgentCostQuality,
    ConfidenceLevel,
    CostIntelligenceResponse,
    ForecastPoint,
    Granularity,
    KpiDataPoint,
    KpiSeries,
    OptimizationRecommendation,
    RecommendationsResponse,
    RecommendationType,
    ResourcePrediction,
    UsageResponse,
    UsageRollupItem,
)
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.exceptions import ClickHouseClientError
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4


def build_cost_model(
    *,
    model_id: str = "gpt-4o",
    provider: str = "openai",
    input_cost: str = "0.0000025",
    output_cost: str = "0.0000100",
    per_second_cost: str | None = None,
    is_active: bool = True,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> CostModel:
    model = CostModel(
        model_id=model_id,
        provider=provider,
        display_name=model_id.upper(),
        input_token_cost_usd=Decimal(input_cost),
        output_token_cost_usd=Decimal(output_cost),
        per_second_cost_usd=None if per_second_cost is None else Decimal(per_second_cost),
        is_active=is_active,
        valid_from=valid_from or datetime.now(UTC) - timedelta(days=1),
        valid_until=valid_until,
    )
    model.id = uuid4()
    model.created_at = datetime.now(UTC)
    model.updated_at = datetime.now(UTC)
    return model


def build_envelope(
    *,
    event_type: str = "workflow.runtime.completed",
    workspace_id: UUID | None = None,
    execution_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source="tests.analytics",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            execution_id=execution_id,
        ),
        payload=payload or {},
    )


def build_usage_response(workspace_id: UUID) -> UsageResponse:
    now = datetime.now(UTC)
    return UsageResponse(
        items=[
            UsageRollupItem(
                period=now,
                workspace_id=workspace_id,
                agent_fqn="planner:daily",
                model_id="gpt-4o",
                provider="openai",
                execution_count=3,
                input_tokens=300,
                output_tokens=120,
                total_tokens=420,
                cost_usd=1.25,
                avg_duration_ms=250.0,
                self_correction_loops=1,
            )
        ],
        total=1,
        workspace_id=workspace_id,
        granularity=Granularity.DAILY,
        start_time=now - timedelta(days=1),
        end_time=now,
    )


def build_cost_intelligence_response(workspace_id: UUID) -> CostIntelligenceResponse:
    now = datetime.now(UTC)
    return CostIntelligenceResponse(
        workspace_id=workspace_id,
        period_start=now - timedelta(days=7),
        period_end=now,
        agents=[
            AgentCostQuality(
                agent_fqn="planner:daily",
                model_id="gpt-4o",
                provider="openai",
                total_cost_usd=3.5,
                avg_quality_score=0.8,
                cost_per_quality=4.375,
                execution_count=7,
                efficiency_rank=1,
            )
        ],
    )


def build_recommendations_response(workspace_id: UUID) -> RecommendationsResponse:
    return RecommendationsResponse(
        workspace_id=workspace_id,
        generated_at=datetime.now(UTC),
        recommendations=[
            OptimizationRecommendation(
                recommendation_type=RecommendationType.MODEL_SWITCH,
                agent_fqn="planner:daily",
                title="Switch models",
                description="Cheaper model available.",
                estimated_savings_usd_per_month=12.5,
                confidence=ConfidenceLevel.HIGH,
                data_points=120,
                supporting_data={"current_model": "gpt-4o", "suggested_model": "gemini-2.0-flash"},
            )
        ],
    )


def build_forecast_response(workspace_id: UUID, *, horizon_days: int = 30) -> ResourcePrediction:
    now = datetime.now(UTC)
    return ResourcePrediction(
        workspace_id=workspace_id,
        horizon_days=horizon_days,
        generated_at=now,
        trend_direction="increasing",
        high_volatility=False,
        data_points_used=30,
        warning=None,
        daily_forecast=[
            ForecastPoint(
                date=now + timedelta(days=1),
                projected_cost_usd_low=9.0,
                projected_cost_usd_expected=10.0,
                projected_cost_usd_high=11.0,
            )
        ],
        total_projected_low=9.0,
        total_projected_expected=10.0,
        total_projected_high=11.0,
    )


def build_kpi_series(workspace_id: UUID) -> KpiSeries:
    now = datetime.now(UTC)
    return KpiSeries(
        workspace_id=workspace_id,
        granularity=Granularity.DAILY,
        start_time=now - timedelta(days=7),
        end_time=now,
        items=[
            KpiDataPoint(
                period=now,
                total_cost_usd=6.5,
                execution_count=8,
                avg_duration_ms=325.0,
                avg_quality_score=0.81,
                cost_per_quality=8.0247,
            )
        ],
    )


@dataclass
class ClickHouseClientStub:
    query_responses: list[list[dict[str, Any]]] = field(default_factory=list)
    query_error: Exception | None = None
    insert_error: Exception | None = None
    command_error: Exception | None = None
    query_calls: list[tuple[str, dict[str, Any] | None]] = field(default_factory=list)
    insert_calls: list[tuple[str, list[dict[str, Any]], list[str]]] = field(default_factory=list)
    command_calls: list[tuple[str, dict[str, Any] | None]] = field(default_factory=list)
    connected: bool = False
    closed: bool = False

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.query_calls.append((sql, params))
        if self.query_error is not None:
            raise self.query_error
        return self.query_responses.pop(0) if self.query_responses else []

    async def insert(self, table: str, rows: list[dict[str, Any]], column_names: list[str]) -> None:
        self.insert_calls.append((table, rows, column_names))
        if self.insert_error is not None:
            raise self.insert_error

    async def execute_command(self, sql: str, params: dict[str, Any] | None = None) -> None:
        self.command_calls.append((sql, params))
        if self.command_error is not None:
            raise self.command_error

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True


class QueryResultStub:
    def __init__(self, *, one: Any = None, many: list[Any] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> Any:
        return self._one

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: list(self._many))


class SessionStub:
    def __init__(self, responses: list[QueryResultStub]) -> None:
        self._responses = list(responses)
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> QueryResultStub:
        self.executed.append(statement)
        return self._responses.pop(0)


class AsyncSessionContextStub:
    def __init__(self, session: Any) -> None:
        self.session = session

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False


class AsyncSessionFactoryStub:
    def __init__(self, session: Any) -> None:
        self.session = session

    def __call__(self) -> AsyncSessionContextStub:
        return AsyncSessionContextStub(self.session)


class WorkspacesServiceStub:
    def __init__(self, workspace_ids: list[UUID] | None = None) -> None:
        self.workspace_ids = workspace_ids or []
        self.calls: list[UUID] = []

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        self.calls.append(user_id)
        return list(self.workspace_ids)


@dataclass
class AnalyticsRepositoryStub:
    usage_rows: list[dict[str, Any]] = field(default_factory=list)
    usage_total: int = 0
    cost_quality_rows: list[dict[str, Any]] = field(default_factory=list)
    daily_cost_rows: list[dict[str, Any]] = field(default_factory=list)
    agent_metrics: list[dict[str, Any]] = field(default_factory=list)
    fleet_baselines: dict[str, float] = field(default_factory=dict)
    kpi_rows: list[dict[str, Any]] = field(default_factory=list)
    workspace_ids: list[UUID] = field(default_factory=list)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    async def query_usage_rollups(self, *args: Any) -> tuple[list[dict[str, Any]], int]:
        self.calls.append(("query_usage_rollups", args))
        return self.usage_rows, self.usage_total

    async def query_cost_quality_join(self, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("query_cost_quality_join", args))
        return self.cost_quality_rows

    async def query_daily_cost_series(self, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("query_daily_cost_series", args))
        return self.daily_cost_rows

    async def query_agent_metrics(self, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("query_agent_metrics", args))
        return self.agent_metrics

    async def query_fleet_baselines(self, *args: Any) -> dict[str, float]:
        self.calls.append(("query_fleet_baselines", args))
        return self.fleet_baselines

    async def query_kpi_series(self, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("query_kpi_series", args))
        return self.kpi_rows

    async def list_workspace_ids(self) -> list[UUID]:
        self.calls.append(("list_workspace_ids", ()))
        return self.workspace_ids


class RouterAnalyticsServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.calls: list[tuple[str, Any]] = []

    async def get_usage(self, params: Any, user_id: UUID) -> UsageResponse:
        self.calls.append(("get_usage", params))
        assert user_id
        return build_usage_response(self.workspace_id)

    async def get_cost_intelligence(self, params: Any, user_id: UUID) -> CostIntelligenceResponse:
        self.calls.append(("get_cost_intelligence", params))
        assert user_id
        return build_cost_intelligence_response(self.workspace_id)

    async def get_recommendations(self, params: Any, user_id: UUID) -> RecommendationsResponse:
        self.calls.append(("get_recommendations", params))
        assert user_id
        return build_recommendations_response(self.workspace_id)

    async def get_forecast(self, params: Any, user_id: UUID) -> ResourcePrediction:
        self.calls.append(("get_forecast", params))
        assert user_id
        return build_forecast_response(self.workspace_id, horizon_days=params.horizon_days)

    async def get_kpi_series(
        self,
        *,
        workspace_id: UUID,
        granularity: Granularity,
        start_time: datetime,
        end_time: datetime,
        user_id: UUID,
    ) -> KpiSeries:
        self.calls.append(
            (
                "get_kpi_series",
                {
                    "workspace_id": workspace_id,
                    "granularity": granularity,
                    "start_time": start_time,
                    "end_time": end_time,
                    "user_id": user_id,
                },
            )
        )
        return build_kpi_series(self.workspace_id)


class RetryHandlerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, EventEnvelope, Any]] = []

    async def handle(self, topic: str, envelope: EventEnvelope, handler: Any) -> None:
        self.calls.append((topic, envelope, handler))


def clickhouse_error(message: str = "boom") -> ClickHouseClientError:
    return ClickHouseClientError(message)
