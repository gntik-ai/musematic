from __future__ import annotations

from platform.agentops.health.dimensions import (
    DimensionResult,
    HealthDimensionProvider,
    _coerce_float,
    _coerce_int,
    _extract_score_and_samples,
    _normalize_score,
    _parse_availability_score,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class _RedisWrapper:
    def __init__(self, raw_client: object) -> None:
        self._raw_client = raw_client

    async def _get_client(self) -> object:
        return self._raw_client


@pytest.mark.asyncio
async def test_uptime_score_returns_dimension_result() -> None:
    raw_client = SimpleNamespace(
        scan=AsyncMock(side_effect=[(0, ["fleet:member:avail:fleet-a:finance:agent"])]),
        get=AsyncMock(return_value='{"availability_ratio": 0.82}'),
    )
    provider = HealthDimensionProvider(
        redis_client=_RedisWrapper(raw_client),
        clickhouse_client=None,
        trust_service=None,
        eval_suite_service=None,
    )

    result = await provider.uptime_score(agent_fqn="finance:agent", minimum_sample_size=1)

    assert result == DimensionResult(score=82.0, sample_count=1)


@pytest.mark.asyncio
async def test_quality_score_returns_dimension_result() -> None:
    clickhouse_client = SimpleNamespace(
        execute_query=AsyncMock(return_value=[{"average_quality": 0.91, "sample_count": 64}])
    )
    provider = HealthDimensionProvider(
        redis_client=None,
        clickhouse_client=clickhouse_client,
        trust_service=None,
        eval_suite_service=None,
    )

    result = await provider.quality_score(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        window_days=30,
        minimum_sample_size=10,
    )

    assert result == DimensionResult(score=91.0, sample_count=64)


@pytest.mark.asyncio
async def test_safety_score_returns_dimension_result() -> None:
    trust_service = SimpleNamespace(
        get_guardrail_pass_rate=AsyncMock(return_value={"pass_rate": 0.88, "sample_count": 40})
    )
    provider = HealthDimensionProvider(
        redis_client=None,
        clickhouse_client=None,
        trust_service=trust_service,
        eval_suite_service=None,
    )

    result = await provider.safety_score(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        window_days=30,
        minimum_sample_size=10,
    )

    assert result == DimensionResult(score=88.0, sample_count=40)


@pytest.mark.asyncio
async def test_cost_efficiency_score_returns_dimension_result() -> None:
    clickhouse_client = SimpleNamespace(
        execute_query=AsyncMock(
            return_value=[
                {
                    "cost_per_quality": 2.0,
                    "workspace_cost_per_quality": 1.0,
                    "sample_count": 32,
                }
            ]
        )
    )
    provider = HealthDimensionProvider(
        redis_client=None,
        clickhouse_client=clickhouse_client,
        trust_service=None,
        eval_suite_service=None,
    )

    result = await provider.cost_efficiency_score(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        window_days=30,
        minimum_sample_size=10,
    )

    assert result == DimensionResult(score=50.0, sample_count=32)


@pytest.mark.asyncio
async def test_satisfaction_score_returns_dimension_result() -> None:
    eval_suite_service = SimpleNamespace(
        get_human_grade_aggregate=AsyncMock(
            return_value={"aggregate_grade": 4.5, "sample_count": 18}
        )
    )
    provider = HealthDimensionProvider(
        redis_client=None,
        clickhouse_client=None,
        trust_service=None,
        eval_suite_service=eval_suite_service,
    )

    result = await provider.satisfaction_score(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        window_days=30,
        minimum_sample_size=10,
    )

    assert result == DimensionResult(score=90.0, sample_count=18)


@pytest.mark.parametrize(
    ("name", "provider", "kwargs"),
    [
        (
            "uptime",
            HealthDimensionProvider(
                redis_client=_RedisWrapper(
                    SimpleNamespace(
                        scan=AsyncMock(
                            side_effect=[(0, ["fleet:member:avail:fleet-a:finance:agent"])]
                        ),
                        get=AsyncMock(return_value="0.9"),
                    )
                ),
                clickhouse_client=None,
                trust_service=None,
                eval_suite_service=None,
            ),
            {"agent_fqn": "finance:agent", "minimum_sample_size": 2},
        ),
        (
            "quality",
            HealthDimensionProvider(
                redis_client=None,
                clickhouse_client=SimpleNamespace(
                    execute_query=AsyncMock(
                        return_value=[{"average_quality": 0.9, "sample_count": 3}]
                    )
                ),
                trust_service=None,
                eval_suite_service=None,
            ),
            {
                "agent_fqn": "finance:agent",
                "workspace_id": uuid4(),
                "window_days": 30,
                "minimum_sample_size": 5,
            },
        ),
        (
            "safety",
            HealthDimensionProvider(
                redis_client=None,
                clickhouse_client=None,
                trust_service=SimpleNamespace(
                    get_guardrail_pass_rate=AsyncMock(
                        return_value={"pass_rate": 0.9, "sample_count": 4}
                    )
                ),
                eval_suite_service=None,
            ),
            {
                "agent_fqn": "finance:agent",
                "workspace_id": uuid4(),
                "window_days": 30,
                "minimum_sample_size": 5,
            },
        ),
        (
            "cost_efficiency",
            HealthDimensionProvider(
                redis_client=None,
                clickhouse_client=SimpleNamespace(
                    execute_query=AsyncMock(
                        return_value=[
                            {
                                "cost_per_quality": 1.5,
                                "workspace_cost_per_quality": 1.0,
                                "sample_count": 2,
                            }
                        ]
                    )
                ),
                trust_service=None,
                eval_suite_service=None,
            ),
            {
                "agent_fqn": "finance:agent",
                "workspace_id": uuid4(),
                "window_days": 30,
                "minimum_sample_size": 5,
            },
        ),
        (
            "satisfaction",
            HealthDimensionProvider(
                redis_client=None,
                clickhouse_client=None,
                trust_service=None,
                eval_suite_service=SimpleNamespace(
                    get_human_grade_aggregate=AsyncMock(
                        return_value={"aggregate_grade": 4.7, "sample_count": 1}
                    )
                ),
            ),
            {
                "agent_fqn": "finance:agent",
                "workspace_id": uuid4(),
                "window_days": 30,
                "minimum_sample_size": 5,
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_dimension_returns_none_when_sample_count_is_below_minimum(
    name: str,
    provider: HealthDimensionProvider,
    kwargs: dict[str, object],
) -> None:
    result = await getattr(provider, f"{name}_score")(**kwargs)

    assert result.score is None
    assert result.sample_count < kwargs["minimum_sample_size"]


@pytest.mark.asyncio
async def test_dimension_provider_handles_missing_clients_and_non_callable_eval_method() -> None:
    workspace_id = uuid4()
    provider = HealthDimensionProvider(
        redis_client=None,
        clickhouse_client=None,
        trust_service=None,
        eval_suite_service=SimpleNamespace(get_human_grade_aggregate="not-callable"),
    )

    assert await provider.uptime_score(agent_fqn="finance:agent", minimum_sample_size=1) == (
        DimensionResult(None, 0)
    )
    assert await provider.quality_score(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        window_days=30,
        minimum_sample_size=1,
    ) == DimensionResult(None, 0)
    assert await provider.safety_score(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        window_days=30,
        minimum_sample_size=1,
    ) == DimensionResult(None, 0)
    assert await provider.cost_efficiency_score(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        window_days=30,
        minimum_sample_size=1,
    ) == DimensionResult(None, 0)
    assert await provider.satisfaction_score(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        window_days=30,
        minimum_sample_size=1,
    ) == DimensionResult(None, 0)


@pytest.mark.asyncio
async def test_dimension_provider_uses_sample_defaults_and_multiple_response_shapes() -> None:
    workspace_id = uuid4()
    trust_service = SimpleNamespace(
        get_guardrail_pass_rate=AsyncMock(return_value=SimpleNamespace(pass_rate=0.92))
    )
    eval_suite_service = SimpleNamespace(
        get_human_grade_aggregate=AsyncMock(return_value=(4.8, 0))
    )
    clickhouse_client = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                [{"average_quality": None, "sample_count": "bad"}],
                [{"cost_per_quality": 0.5, "workspace_cost_per_quality": 1.0, "sample_count": 9}],
            ]
        )
    )
    provider = HealthDimensionProvider(
        redis_client=SimpleNamespace(client=SimpleNamespace()),
        clickhouse_client=clickhouse_client,
        trust_service=trust_service,
        eval_suite_service=eval_suite_service,
    )

    assert (
        await provider.quality_score(
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            window_days=30,
            minimum_sample_size=1,
        )
    ) == DimensionResult(None, 0)
    assert (
        await provider.safety_score(
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            window_days=30,
            minimum_sample_size=4,
        )
    ) == DimensionResult(92.0, 4)
    assert (
        await provider.satisfaction_score(
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            window_days=30,
            minimum_sample_size=3,
        )
    ) == DimensionResult(96.0, 3)
    assert (
        await provider.cost_efficiency_score(
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            window_days=30,
            minimum_sample_size=5,
        )
    ) == DimensionResult(100.0, 9)
    assert await provider._get_redis_client() is provider.redis_client.client


def test_dimension_helper_functions_cover_parsing_and_normalization() -> None:
    assert _parse_availability_score('{"availability_ratio": 0.8}') == 80.0
    assert _parse_availability_score(b'{"uptime_ratio": 0.7}') == 70.0
    assert _parse_availability_score("  ") is None
    assert _parse_availability_score("{bad json") is None
    assert _parse_availability_score({"value": 110}) == 100.0

    assert _extract_score_and_samples((0.75, 4), value_keys=("score",), scale="ratio") == (75.0, 4)
    assert _extract_score_and_samples(
        {"average_grade": 4.0, "samples": "3"},
        value_keys=("average_grade",),
        scale="stars",
    ) == (80.0, 3)
    assert _extract_score_and_samples(
        SimpleNamespace(score=0.25, count=2),
        value_keys=("score",),
        scale="ratio",
    ) == (25.0, 2)
    assert _extract_score_and_samples(None, value_keys=("score",), scale="ratio") == (None, 0)

    assert _normalize_score(0.5, scale="ratio") == 50.0
    assert _normalize_score(4.5, scale="stars") == 90.0
    assert _normalize_score(120, scale="other") == 100.0
    assert _coerce_float("1.5") == 1.5
    assert _coerce_float(object()) is None
    assert _coerce_int("7") == 7
    assert _coerce_int(None) == 0
