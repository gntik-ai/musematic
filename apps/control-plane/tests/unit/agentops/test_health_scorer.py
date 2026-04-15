from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from platform.agentops.health.dimensions import DimensionResult
from platform.agentops.health.scorer import HealthScorer
from platform.agentops.models import AgentHealthConfig, AgentHealthScore
from platform.agentops.service import AgentOpsService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


@dataclass
class _DimensionsStub:
    uptime: DimensionResult
    quality: DimensionResult
    safety: DimensionResult
    cost_efficiency: DimensionResult
    satisfaction: DimensionResult

    async def uptime_score(self, **_: Any) -> DimensionResult:
        return self.uptime

    async def quality_score(self, **_: Any) -> DimensionResult:
        return self.quality

    async def safety_score(self, **_: Any) -> DimensionResult:
        return self.safety

    async def cost_efficiency_score(self, **_: Any) -> DimensionResult:
        return self.cost_efficiency

    async def satisfaction_score(self, **_: Any) -> DimensionResult:
        return self.satisfaction


class _RepositoryStub:
    def __init__(self, config: AgentHealthConfig) -> None:
        self.config = config
        self.current_score: AgentHealthScore | None = None
        self.persisted: list[AgentHealthScore] = []

    async def get_health_config(self, workspace_id: UUID) -> AgentHealthConfig | None:
        assert workspace_id == self.config.workspace_id
        return self.config

    async def upsert_health_config(self, config: AgentHealthConfig) -> AgentHealthConfig:
        self.config = config
        return config

    async def get_current_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScore | None:
        if self.current_score is None:
            return None
        assert self.current_score.agent_fqn == agent_fqn
        assert self.current_score.workspace_id == workspace_id
        return self.current_score

    async def upsert_health_score(self, score: AgentHealthScore) -> AgentHealthScore:
        self.current_score = score
        self.persisted.append(score)
        return score


class _EventPublisherStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(self, **payload: Any) -> None:
        self.calls.append(payload)


class _RedisStub:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        del ttl
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _config(workspace_id: UUID, **overrides: Decimal | int) -> AgentHealthConfig:
    base = {
        "workspace_id": workspace_id,
        "weight_uptime": Decimal("20.00"),
        "weight_quality": Decimal("20.00"),
        "weight_safety": Decimal("20.00"),
        "weight_cost_efficiency": Decimal("20.00"),
        "weight_satisfaction": Decimal("20.00"),
        "warning_threshold": Decimal("60.00"),
        "critical_threshold": Decimal("40.00"),
        "scoring_interval_minutes": 15,
        "min_sample_size": 5,
        "rolling_window_days": 30,
    }
    base.update(overrides)
    return AgentHealthConfig(**base)


@pytest.mark.asyncio
async def test_health_scorer_computes_composite_score_with_full_dimensions() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(_config(workspace_id))
    events = _EventPublisherStub()
    scorer = HealthScorer(
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(90.0, 10),
            quality=DimensionResult(80.0, 10),
            safety=DimensionResult(70.0, 10),
            cost_efficiency=DimensionResult(60.0, 10),
            satisfaction=DimensionResult(50.0, 10),
        ),
        event_publisher=events,  # type: ignore[arg-type]
    )

    result = await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
        observation_end=datetime(2026, 4, 14, tzinfo=UTC),
    )

    assert float(result.composite_score) == pytest.approx(70.0)
    assert result.weights_snapshot == {
        "uptime": 20.0,
        "quality": 20.0,
        "safety": 20.0,
        "cost_efficiency": 20.0,
        "satisfaction": 20.0,
    }
    assert not result.below_warning
    assert not result.below_critical
    assert not result.insufficient_data
    assert events.calls == []


@pytest.mark.asyncio
async def test_health_scorer_redistributes_weights_for_missing_dimensions() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(
        _config(
            workspace_id,
            weight_uptime=Decimal("50.00"),
            weight_quality=Decimal("30.00"),
            weight_safety=Decimal("20.00"),
            weight_cost_efficiency=Decimal("0.00"),
            weight_satisfaction=Decimal("0.00"),
        )
    )
    scorer = HealthScorer(
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(None, 0),
            quality=DimensionResult(80.0, 10),
            safety=DimensionResult(50.0, 10),
            cost_efficiency=DimensionResult(None, 0),
            satisfaction=DimensionResult(None, 0),
        ),
        event_publisher=_EventPublisherStub(),  # type: ignore[arg-type]
    )

    result = await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert float(result.composite_score) == pytest.approx(68.0)
    assert result.weights_snapshot == {
        "uptime": 0.0,
        "quality": 60.0,
        "safety": 40.0,
        "cost_efficiency": 0.0,
        "satisfaction": 0.0,
    }
    assert result.missing_dimensions == ["uptime", "cost_efficiency", "satisfaction"]


@pytest.mark.asyncio
async def test_health_scorer_sets_threshold_flags_and_publishes_warning_then_critical() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(_config(workspace_id))
    events = _EventPublisherStub()
    scorer = HealthScorer(
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(55.0, 10),
            quality=DimensionResult(55.0, 10),
            safety=DimensionResult(55.0, 10),
            cost_efficiency=DimensionResult(55.0, 10),
            satisfaction=DimensionResult(55.0, 10),
        ),
        event_publisher=events,  # type: ignore[arg-type]
    )

    warning_score = await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert warning_score.below_warning
    assert not warning_score.below_critical
    assert events.calls[-1]["event_type"] == "agentops.health.warning"

    scorer.dimensions = _DimensionsStub(
        uptime=DimensionResult(35.0, 10),
        quality=DimensionResult(35.0, 10),
        safety=DimensionResult(35.0, 10),
        cost_efficiency=DimensionResult(35.0, 10),
        satisfaction=DimensionResult(35.0, 10),
    )
    critical_score = await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert critical_score.below_warning
    assert critical_score.below_critical
    assert events.calls[-1]["event_type"] == "agentops.health.critical"
    assert len(events.calls) == 2


@pytest.mark.asyncio
async def test_health_scorer_marks_insufficient_data_when_all_dimensions_are_missing() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(_config(workspace_id))
    events = _EventPublisherStub()
    scorer = HealthScorer(
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(None, 0),
            quality=DimensionResult(None, 0),
            safety=DimensionResult(None, 0),
            cost_efficiency=DimensionResult(None, 0),
            satisfaction=DimensionResult(None, 0),
        ),
        event_publisher=events,  # type: ignore[arg-type]
    )

    result = await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert result.insufficient_data
    assert float(result.composite_score) == 0.0
    assert not result.below_warning
    assert not result.below_critical
    assert events.calls == []


@pytest.mark.asyncio
async def test_health_scorer_publishes_retirement_trigger_after_threshold_intervals() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(_config(workspace_id))
    events = _EventPublisherStub()
    redis = _RedisStub()
    scorer = HealthScorer(
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(35.0, 10),
            quality=DimensionResult(35.0, 10),
            safety=DimensionResult(35.0, 10),
            cost_efficiency=DimensionResult(35.0, 10),
            satisfaction=DimensionResult(35.0, 10),
        ),
        event_publisher=events,  # type: ignore[arg-type]
        redis_client=redis,
        critical_interval_threshold=2,
    )

    await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )
    await scorer.compute(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert events.calls[-1]["event_type"] == "agentops.retirement.trigger"
    assert events.calls[-1]["payload"]["critical_intervals"] == 2


@pytest.mark.asyncio
async def test_score_all_agents_task_scores_targets_from_registry_service() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(_config(workspace_id))
    events = _EventPublisherStub()
    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=events,  # type: ignore[arg-type]
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=SimpleNamespace(
            list_active_agents=lambda requested_workspace_id=None: _active_targets(
                workspace_id if requested_workspace_id is None else requested_workspace_id
            )
        ),
    )

    service._health_scorer = lambda: HealthScorer(  # type: ignore[method-assign]
        repository=repository,  # type: ignore[arg-type]
        dimensions=_DimensionsStub(
            uptime=DimensionResult(58.0, 10),
            quality=DimensionResult(58.0, 10),
            safety=DimensionResult(58.0, 10),
            cost_efficiency=DimensionResult(58.0, 10),
            satisfaction=DimensionResult(58.0, 10),
        ),
        event_publisher=events,  # type: ignore[arg-type]
    )

    items = await service.score_all_agents_task()

    assert len(items) == 1
    assert items[0].agent_fqn == "finance:agent"
    assert repository.persisted
    assert events.calls[-1]["event_type"] == "agentops.health.warning"


async def _active_targets(workspace_id: UUID) -> list[dict[str, str]]:
    return [
        {
            "agent_fqn": "finance:agent",
            "workspace_id": str(workspace_id),
            "revision_id": str(uuid4()),
        }
    ]
