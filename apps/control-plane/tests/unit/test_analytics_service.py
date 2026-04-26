from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.analytics.exceptions import AnalyticsError, WorkspaceAuthorizationError
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.schemas import (
    CostIntelligenceParams,
    ForecastParams,
    Granularity,
    RecommendationsParams,
    RecommendationType,
    UsageQueryParams,
)
from platform.analytics.service import AnalyticsService
from platform.common.config import PlatformSettings
from uuid import uuid4

import pytest

from tests.analytics_support import AnalyticsRepositoryStub, WorkspacesServiceStub
from tests.auth_support import RecordingProducer


class CostGovernanceAnalyticsStub:
    def __init__(self) -> None:
        self.workspace_summary_calls: list[tuple[object, object]] = []
        self.threshold_calls = 0
        self.threshold_workspace_id = uuid4()

    async def get_workspace_cost_summary(self, workspace_id, *, period_start):
        self.workspace_summary_calls.append((workspace_id, period_start))
        return {
            "total_cost_usd": 42.0,
            "period_start": period_start,
            "period_end": datetime.now(UTC),
            "execution_count": 7,
            "avg_daily_cost_usd": 6.0,
        }

    async def evaluate_thresholds(self):
        self.threshold_calls += 1
        return [self.threshold_workspace_id]


def _service(
    repo: AnalyticsRepositoryStub,
    *,
    workspace_ids: list[object] | None = None,
    producer: RecordingProducer | None = None,
    threshold: float = 0.0,
) -> AnalyticsService:
    return AnalyticsService(
        repo=repo,  # type: ignore[arg-type]
        cost_model_repo=object(),  # type: ignore[arg-type]
        workspaces_service=WorkspacesServiceStub(workspace_ids or []),  # type: ignore[arg-type]
        settings=PlatformSettings(ANALYTICS_BUDGET_THRESHOLD_USD=threshold),
        kafka_producer=producer,
        recommendation_engine=RecommendationEngine(),
        forecast_engine=ForecastEngine(),
    )


@pytest.mark.asyncio
async def test_get_usage_validates_window_and_workspace_access() -> None:
    workspace_id = uuid4()
    repo = AnalyticsRepositoryStub(
        usage_rows=[
            {
                "period": datetime.now(UTC),
                "workspace_id": workspace_id,
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "provider": "openai",
                "execution_count": 2,
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "cost_usd": 1.2,
                "avg_duration_ms": 20.0,
                "self_correction_loops": 1,
            }
        ],
        usage_total=1,
    )
    service = _service(repo, workspace_ids=[workspace_id])
    user_id = uuid4()
    now = datetime.now(UTC)

    response = await service.get_usage(
        UsageQueryParams(
            workspace_id=workspace_id,
            start_time=now - timedelta(days=1),
            end_time=now,
            granularity=Granularity.DAILY,
        ),
        user_id,
    )

    assert response.total == 1
    with pytest.raises(WorkspaceAuthorizationError):
        await service.get_usage(
            UsageQueryParams(
                workspace_id=uuid4(),
                start_time=now - timedelta(days=1),
                end_time=now,
                granularity=Granularity.DAILY,
            ),
            user_id,
        )
    with pytest.raises(AnalyticsError):
        await service.get_usage(
            UsageQueryParams(
                workspace_id=workspace_id,
                start_time=now,
                end_time=now - timedelta(days=1),
                granularity=Granularity.DAILY,
            ),
            user_id,
        )


@pytest.mark.asyncio
async def test_get_cost_intelligence_ranks_null_quality_last() -> None:
    workspace_id = uuid4()
    repo = AnalyticsRepositoryStub(
        cost_quality_rows=[
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "provider": "openai",
                "total_cost_usd": 10.0,
                "avg_quality_score": 0.5,
                "execution_count": 5,
            },
            {
                "agent_fqn": "writer:review",
                "model_id": "claude-3-5-sonnet",
                "provider": "anthropic",
                "total_cost_usd": 1.0,
                "avg_quality_score": None,
                "execution_count": 2,
            },
        ]
    )
    service = _service(repo, workspace_ids=[workspace_id])
    now = datetime.now(UTC)

    response = await service.get_cost_intelligence(
        CostIntelligenceParams(
            workspace_id=workspace_id,
            start_time=now - timedelta(days=7),
            end_time=now,
        ),
        uuid4(),
    )

    assert response.agents[0].agent_fqn == "planner:daily"
    assert response.agents[1].cost_per_quality is None
    assert response.agents[1].efficiency_rank == 2


@pytest.mark.asyncio
async def test_get_recommendations_emits_event_when_non_empty() -> None:
    workspace_id = uuid4()
    repo = AnalyticsRepositoryStub(
        agent_metrics=[
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "avg_cost_per_execution": 0.12,
                "avg_quality_score": 0.91,
                "execution_count": 120,
                "execution_count_last_30d": 100,
            },
            {
                "agent_fqn": "planner:daily",
                "model_id": "gemini-2.0-flash",
                "avg_cost_per_execution": 0.04,
                "avg_quality_score": 0.90,
                "execution_count": 130,
                "execution_count_last_30d": 100,
            },
        ],
        fleet_baselines={
            "avg_loops": 1.0,
            "median_quality": 0.8,
            "p95_input_output_ratio": 5.0,
        },
    )
    producer = RecordingProducer()
    service = _service(repo, workspace_ids=[workspace_id], producer=producer)

    response = await service.get_recommendations(
        RecommendationsParams(workspace_id=workspace_id),
        uuid4(),
    )

    assert response.recommendations
    assert response.recommendations[0].recommendation_type == RecommendationType.MODEL_SWITCH
    assert producer.events[0]["event_type"] == "analytics.recommendation.generated"


@pytest.mark.asyncio
async def test_get_forecast_validates_horizon_and_publishes_event() -> None:
    workspace_id = uuid4()
    repo = AnalyticsRepositoryStub(
        daily_cost_rows=[
            {"day": datetime.now(UTC) - timedelta(days=2), "cost_usd": 10.0},
            {"day": datetime.now(UTC) - timedelta(days=1), "cost_usd": 12.0},
            {"day": datetime.now(UTC), "cost_usd": 14.0},
        ]
    )
    producer = RecordingProducer()
    service = _service(repo, workspace_ids=[workspace_id], producer=producer)

    with pytest.raises(AnalyticsError):
        await service.get_forecast(
            ForecastParams(workspace_id=workspace_id, horizon_days=8),
            uuid4(),
        )

    response = await service.get_forecast(
        ForecastParams(workspace_id=workspace_id, horizon_days=7),
        uuid4(),
    )

    assert response.horizon_days == 7
    assert producer.events[0]["event_type"] == "analytics.forecast.updated"


@pytest.mark.asyncio
async def test_get_kpi_summary_and_budget_thresholds() -> None:
    workspace_id = uuid4()
    repo = AnalyticsRepositoryStub(
        kpi_rows=[
            {
                "period": datetime.now(UTC) - timedelta(days=1),
                "total_cost_usd": 12.5,
                "execution_count": 5,
                "avg_duration_ms": 250.0,
                "avg_quality_score": 0.8,
                "cost_per_quality": 15.625,
            },
            {
                "period": datetime.now(UTC),
                "total_cost_usd": 20.0,
                "execution_count": 8,
                "avg_duration_ms": 200.0,
                "avg_quality_score": 0.9,
                "cost_per_quality": 22.2222,
            },
        ],
        workspace_ids=[workspace_id],
    )
    producer = RecordingProducer()
    service = _service(repo, workspace_ids=[workspace_id], producer=producer, threshold=25.0)
    user_id = uuid4()
    now = datetime.now(UTC)

    kpi = await service.get_kpi_series(
        workspace_id,
        Granularity.DAILY,
        now - timedelta(days=7),
        now,
        user_id,
    )
    summary = await service.get_workspace_cost_summary(workspace_id, 30)
    crossed = await service.check_budget_thresholds(30)

    assert len(kpi.items) == 2
    assert summary["total_cost_usd"] == 32.5
    assert summary["execution_count"] == 13
    assert crossed == [workspace_id]
    assert producer.events[-1]["event_type"] == "analytics.budget.threshold_crossed"


@pytest.mark.asyncio
async def test_recommendations_empty_threshold_zero_and_missing_workspace_service_paths() -> None:
    workspace_id = uuid4()
    service = _service(
        AnalyticsRepositoryStub(
            agent_metrics=[],
            fleet_baselines={},
        ),
        workspace_ids=[workspace_id],
        producer=RecordingProducer(),
        threshold=0.0,
    )

    response = await service.get_recommendations(
        RecommendationsParams(workspace_id=workspace_id),
        uuid4(),
    )
    crossed = await service.check_budget_thresholds(30)

    assert response.recommendations == []
    assert crossed == []

    service.workspaces_service = None
    with pytest.raises(AnalyticsError, match="Workspace service unavailable"):
        await service._assert_workspace_access(workspace_id, uuid4())


@pytest.mark.asyncio
async def test_budget_thresholds_skip_workspaces_below_limit() -> None:
    workspace_id = uuid4()
    service = _service(
        AnalyticsRepositoryStub(
            kpi_rows=[
                {
                    "period": datetime.now(UTC),
                    "total_cost_usd": 5.0,
                    "execution_count": 1,
                    "avg_duration_ms": 100.0,
                    "avg_quality_score": 0.8,
                    "cost_per_quality": 6.25,
                }
            ],
            workspace_ids=[workspace_id],
        ),
        workspace_ids=[workspace_id],
        producer=RecordingProducer(),
        threshold=25.0,
    )

    assert await service.check_budget_thresholds(30) == []


@pytest.mark.asyncio
async def test_cost_governance_delegation_paths() -> None:
    workspace_id = uuid4()
    delegate = CostGovernanceAnalyticsStub()
    service = _service(AnalyticsRepositoryStub(), workspace_ids=[workspace_id])
    service.cost_governance_service = delegate

    summary = await service.get_workspace_cost_summary(workspace_id, 14)
    crossed = await service.check_budget_thresholds(14)

    assert summary["total_cost_usd"] == 42.0
    assert summary["execution_count"] == 7
    assert delegate.workspace_summary_calls[0][0] == workspace_id
    assert crossed == [delegate.threshold_workspace_id]
    assert delegate.threshold_calls == 1


def test_rank_cost_quality_assigns_dense_ordering_with_nulls_last() -> None:
    service = _service(AnalyticsRepositoryStub(), workspace_ids=[])

    ranked = service._rank_cost_quality(
        [
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "provider": "openai",
                "total_cost_usd": 4.0,
                "avg_quality_score": 0.8,
                "execution_count": 2,
            },
            {
                "agent_fqn": "writer:review",
                "model_id": "claude",
                "provider": "anthropic",
                "total_cost_usd": 1.0,
                "avg_quality_score": None,
                "execution_count": 1,
            },
        ]
    )

    assert ranked[0].efficiency_rank == 1
    assert ranked[0].cost_per_quality == 5.0
    assert ranked[1].cost_per_quality is None
    assert ranked[1].avg_quality_score is None
