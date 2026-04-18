from __future__ import annotations

from datetime import UTC, datetime
from platform.analytics.exceptions import AnalyticsStoreUnavailableError
from platform.analytics.repository import (
    AnalyticsRepository,
    CostModelRepository,
    _quality_period_expr,
    _rollup_target,
    _utc,
)
from platform.analytics.schemas import Granularity
from uuid import uuid4

import pytest

from tests.analytics_support import (
    ClickHouseClientStub,
    QueryResultStub,
    SessionStub,
    build_cost_model,
    clickhouse_error,
)


@pytest.mark.asyncio
async def test_cost_model_repository_fetches_active_pricing_and_all_models() -> None:
    model = build_cost_model()
    session = SessionStub(
        [
            QueryResultStub(one=model),
            QueryResultStub(many=[model]),
        ]
    )
    repository = CostModelRepository(session)  # type: ignore[arg-type]

    active = await repository.get_active_pricing(model.model_id)
    listed = await repository.list_all()

    assert active is model
    assert listed == [model]
    assert len(session.executed) == 2


@pytest.mark.asyncio
async def test_repository_inserts_and_queries_usage_rollups() -> None:
    workspace_id = uuid4()
    client = ClickHouseClientStub(
        query_responses=[
            [
                {
                    "period": datetime.now(UTC),
                    "workspace_id": workspace_id,
                    "agent_fqn": "planner:daily",
                    "model_id": "gpt-4o",
                    "provider": "openai",
                    "execution_count": 2,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "cost_usd": 1.2,
                    "avg_duration_ms": 10.0,
                    "self_correction_loops": 0,
                }
            ],
            [{"total": 1}],
        ]
    )
    repository = AnalyticsRepository(client)  # type: ignore[arg-type]
    row = {"event_id": uuid4()}

    await repository.insert_usage_events_batch([row])
    await repository.insert_quality_events_batch([row])
    rows, total = await repository.query_usage_rollups(
        workspace_id,
        Granularity.MONTHLY,
        datetime.now(UTC),
        datetime.now(UTC),
        "planner:daily",
        "gpt-4o",
        50,
        10,
    )

    assert client.insert_calls[0][0] == "analytics_usage_events"
    assert client.insert_calls[1][0] == "analytics_quality_events"
    assert client.insert_calls[0][2][3] == "goal_id"
    assert "analytics_usage_monthly" in client.query_calls[0][0]
    assert "agent_fqn = {agent_fqn:String}" in client.query_calls[0][0]
    assert rows[0]["workspace_id"] == workspace_id
    assert total == 1


@pytest.mark.asyncio
async def test_repository_exposes_cost_quality_metrics_and_kpis() -> None:
    workspace_id = uuid4()
    client = ClickHouseClientStub(
        query_responses=[
            [{"agent_fqn": "planner:daily", "model_id": "gpt-4o", "provider": "openai"}],
            [{"day": datetime.now(UTC), "cost_usd": 2.5}],
            [{"agent_fqn": "planner:daily", "execution_count": 40}],
            [{"avg_loops": 1.2, "median_quality": 0.8, "p95_input_output_ratio": 6.0}],
            [{"period": datetime.now(UTC), "total_cost_usd": 4.0, "execution_count": 4}],
            [{"workspace_id": str(workspace_id)}],
        ]
    )
    repository = AnalyticsRepository(client)  # type: ignore[arg-type]

    cost_quality = await repository.query_cost_quality_join(
        workspace_id,
        datetime.now(UTC),
        datetime.now(UTC),
    )
    daily = await repository.query_daily_cost_series(workspace_id, 30)
    metrics = await repository.query_agent_metrics(workspace_id)
    baselines = await repository.query_fleet_baselines(workspace_id)
    kpis = await repository.query_kpi_series(
        workspace_id,
        Granularity.HOURLY,
        datetime.now(UTC),
        datetime.now(UTC),
    )
    workspace_ids = await repository.list_workspace_ids()

    assert cost_quality[0]["provider"] == "openai"
    assert daily[0]["cost_usd"] == 2.5
    assert metrics[0]["execution_count"] == 40
    assert baselines["median_quality"] == 0.8
    assert kpis[0]["execution_count"] == 4
    assert workspace_ids == [workspace_id]
    assert "toStartOfHour(timestamp)" in client.query_calls[4][0]


@pytest.mark.asyncio
async def test_repository_translates_clickhouse_failures() -> None:
    repository = AnalyticsRepository(ClickHouseClientStub(query_error=clickhouse_error()))  # type: ignore[arg-type]

    with pytest.raises(AnalyticsStoreUnavailableError):
        await repository.query_fleet_baselines(uuid4())

    failing_insert = AnalyticsRepository(ClickHouseClientStub(insert_error=clickhouse_error()))  # type: ignore[arg-type]
    with pytest.raises(AnalyticsStoreUnavailableError):
        await failing_insert.insert_usage_events_batch([{"event_id": uuid4()}])


def test_repository_helpers_resolve_views_and_utc_conversion() -> None:
    naive = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None)

    assert _rollup_target(Granularity.HOURLY) == ("analytics_usage_hourly_v2", "hour")
    assert _rollup_target(Granularity.MONTHLY) == ("analytics_usage_monthly", "month")
    assert _quality_period_expr(Granularity.DAILY) == "toStartOfDay(timestamp)"
    assert _utc(naive).tzinfo is UTC
