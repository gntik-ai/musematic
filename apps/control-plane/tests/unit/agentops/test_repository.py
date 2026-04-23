from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.agentops.models import (
    AgentHealthConfig,
    AgentHealthScore,
    RegressionAlertStatus,
    RetirementWorkflowStatus,
)
from platform.agentops.repository import (
    AgentOpsRepository,
    GovernanceSummaryRepository,
    _coerce_tier,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


def _session(*, dialect: str = "sqlite") -> SimpleNamespace:
    return SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name=dialect)),
        add=Mock(),
        delete=AsyncMock(),
        flush=AsyncMock(),
        execute=AsyncMock(),
        scalar=AsyncMock(),
    )


def _health_config(workspace_id: UUID) -> AgentHealthConfig:
    now = datetime.now(UTC)
    return AgentHealthConfig(
        id=uuid4(),
        workspace_id=workspace_id,
        weight_uptime=Decimal("20.00"),
        weight_quality=Decimal("35.00"),
        weight_safety=Decimal("25.00"),
        weight_cost_efficiency=Decimal("10.00"),
        weight_satisfaction=Decimal("10.00"),
        warning_threshold=Decimal("60.00"),
        critical_threshold=Decimal("40.00"),
        scoring_interval_minutes=15,
        min_sample_size=50,
        rolling_window_days=30,
        created_at=now,
        updated_at=now,
    )


def _health_score(agent_fqn: str, workspace_id: UUID) -> AgentHealthScore:
    now = datetime.now(UTC)
    return AgentHealthScore(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn=agent_fqn,
        revision_id=uuid4(),
        composite_score=Decimal("90.00"),
        uptime_score=Decimal("91.00"),
        quality_score=Decimal("89.00"),
        safety_score=Decimal("94.00"),
        cost_efficiency_score=Decimal("70.00"),
        satisfaction_score=Decimal("88.00"),
        weights_snapshot={"uptime": 20.0},
        missing_dimensions=[],
        sample_counts={"uptime": 100},
        computed_at=now,
        observation_window_start=now - timedelta(days=30),
        observation_window_end=now,
        below_warning=False,
        below_critical=False,
        insufficient_data=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_repository_upserts_health_entities_and_supports_postgres_upsert() -> None:
    workspace_id = uuid4()
    config = _health_config(workspace_id)
    score = _health_score("finance:agent", workspace_id)
    session = _session()
    session.execute.side_effect = [
        object(),
        _ScalarResult(config),
        _ScalarResult(config),
        object(),
        _ScalarResult(score),
        _ScalarResult(score),
    ]
    repository = AgentOpsRepository(session)  # type: ignore[arg-type]

    assert await repository.upsert_health_config(config) is config
    assert await repository.get_health_config(workspace_id) is config
    assert await repository.upsert_health_score(score) is score
    assert await repository.get_current_health_score("finance:agent", workspace_id) is score

    postgres_session = _session(dialect="postgresql")
    postgres_repository = AgentOpsRepository(postgres_session)  # type: ignore[arg-type]
    stmt = postgres_repository._upsert_stmt(
        AgentHealthConfig,
        {
            "id": config.id,
            "workspace_id": config.workspace_id,
            "weight_uptime": config.weight_uptime,
            "weight_quality": config.weight_quality,
            "weight_safety": config.weight_safety,
            "weight_cost_efficiency": config.weight_cost_efficiency,
            "weight_satisfaction": config.weight_satisfaction,
            "warning_threshold": config.warning_threshold,
            "critical_threshold": config.critical_threshold,
            "scoring_interval_minutes": config.scoring_interval_minutes,
            "min_sample_size": config.min_sample_size,
            "rolling_window_days": config.rolling_window_days,
        },
        conflict_columns=["workspace_id"],
    )

    assert stmt is not None


@pytest.mark.asyncio
async def test_repository_upsert_health_config_applies_defaults_for_empty_model() -> None:
    workspace_id = uuid4()
    config = AgentHealthConfig(workspace_id=workspace_id)
    persisted = _health_config(workspace_id)
    session = _session()
    session.execute.side_effect = [object(), _ScalarResult(persisted)]
    repository = AgentOpsRepository(session)  # type: ignore[arg-type]

    result = await repository.upsert_health_config(config)

    assert result is persisted
    stmt = session.execute.await_args_list[0].args[0]
    params = stmt.compile().params
    assert params["weight_uptime"] == Decimal("20.00")
    assert params["weight_quality"] == Decimal("35.00")
    assert params["warning_threshold"] == Decimal("60.00")


@pytest.mark.asyncio
async def test_repository_list_methods_delegate_to_paginate_for_all_resources() -> None:
    workspace_id = uuid4()
    now = datetime.now(UTC)
    item = SimpleNamespace(id=uuid4(), created_at=now)
    repository = AgentOpsRepository(_session())  # type: ignore[arg-type]
    repository._paginate = AsyncMock(return_value=([item], "next"))  # type: ignore[method-assign]

    assert await repository.list_health_history(
        "finance:agent",
        workspace_id,
        start_time=now - timedelta(days=1),
        end_time=now,
    ) == ([item], "next")
    assert await repository.list_baselines("finance:agent", workspace_id) == ([item], "next")
    assert await repository.list_regression_alerts(
        "finance:agent",
        workspace_id,
        status=RegressionAlertStatus.active.value,
        new_revision_id=uuid4(),
    ) == ([item], "next")
    assert await repository.list_gate_results(
        "finance:agent",
        workspace_id,
        revision_id=uuid4(),
    ) == ([item], "next")
    assert await repository.list_canaries("finance:agent", workspace_id) == ([item], "next")
    assert await repository.list_retirements(
        "finance:agent",
        workspace_id,
        status=RetirementWorkflowStatus.grace_period.value,
    ) == ([item], "next")
    assert await repository.list_governance_events(
        "finance:agent",
        workspace_id,
        event_type="agentops.gate.checked",
        since=now - timedelta(days=7),
    ) == ([item], "next")
    assert await repository.list_adaptations(
        "finance:agent",
        workspace_id,
        status="testing",
    ) == ([item], "next")

    assert repository._paginate.await_count == 8  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_repository_crud_helpers_cover_regression_canary_retirement_governance_and_adaptation() -> (
    None
):
    workspace_id = uuid4()
    now = datetime.now(UTC)
    baseline = SimpleNamespace(id=uuid4(), revision_id=uuid4())
    alert = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        new_revision_id=uuid4(),
        status=RegressionAlertStatus.active.value,
        created_at=now,
    )
    gate_result = SimpleNamespace(id=uuid4())
    canary = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        status="active",
        started_at=now,
        created_at=now,
    )
    retirement = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        status=RetirementWorkflowStatus.grace_period.value,
        grace_period_ends_at=now,
        created_at=now,
    )
    governance_event = SimpleNamespace(id=uuid4(), created_at=now)
    adaptation = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        status="testing",
        evaluation_run_id=uuid4(),
        created_at=now,
    )
    session = _session()
    session.execute.side_effect = [
        _ScalarResult(baseline),
        _ScalarResult(alert),
        _ScalarResult(canary),
        _ScalarResult(canary),
        _ScalarsResult([canary]),
        _ScalarResult(retirement),
        _ScalarResult(retirement),
        _ScalarResult(retirement),
        _ScalarsResult([retirement]),
        _ScalarResult(governance_event),
        _ScalarResult(adaptation),
        _ScalarResult(adaptation),
    ]
    session.scalar.return_value = 3
    repository = AgentOpsRepository(session)  # type: ignore[arg-type]

    assert await repository.create_baseline(baseline) is baseline
    assert await repository.get_baseline_by_revision(baseline.revision_id) is baseline
    assert await repository.create_regression_alert(alert) is alert
    assert await repository.get_regression_alert(alert.id) is alert
    assert await repository.update_regression_alert(alert) is alert
    assert await repository.create_gate_result(gate_result) is gate_result
    assert await repository.create_canary(canary) is canary
    assert await repository.get_canary(canary.id) is canary
    assert await repository.get_active_canary("finance:agent", workspace_id) is canary
    assert await repository.list_active_canaries(workspace_id=workspace_id) == [canary]
    assert await repository.update_canary(canary) is canary
    assert await repository.create_retirement(retirement) is retirement
    assert await repository.get_retirement(retirement.id) is retirement
    assert await repository.get_active_retirement("finance:agent", workspace_id) is retirement
    assert await repository.has_active_retirement("finance:agent", workspace_id) is True
    assert await repository.list_due_retirements(now, workspace_id=workspace_id) == [retirement]
    assert await repository.update_retirement(retirement) is retirement
    assert await repository.insert_governance_event(governance_event) is governance_event
    assert await repository.get_governance_event(governance_event.id) is governance_event
    assert await repository.create_adaptation(adaptation) is adaptation
    assert await repository.get_adaptation(adaptation.id) is adaptation
    assert (
        await repository.get_adaptation_by_evaluation_run_id(adaptation.evaluation_run_id)
        is adaptation
    )
    assert await repository.update_adaptation(adaptation) is adaptation
    assert (
        await repository.count_active_regression_alerts(
            "finance:agent",
            workspace_id,
            alert.new_revision_id,
        )
        == 3
    )

    assert session.add.call_count == 7


@pytest.mark.asyncio
async def test_repository_paginate_and_governance_summary_helpers_cover_cursor_and_tiers() -> None:
    workspace_id = uuid4()
    now = datetime.now(UTC)
    item_a = SimpleNamespace(id=uuid4(), created_at=now)
    item_b = SimpleNamespace(id=uuid4(), created_at=now + timedelta(seconds=1))
    session = _session()
    session.execute.side_effect = [
        _ScalarsResult([item_a, item_b]),
        _ScalarsResult([item_a]),
    ]
    repository = AgentOpsRepository(session)  # type: ignore[arg-type]

    paged_items, next_cursor = await repository._paginate(
        select(AgentHealthScore),
        limit=1,
        cursor=None,
    )
    last_page_items, last_cursor = await repository._paginate(
        select(AgentHealthScore),
        limit=5,
        cursor=None,
    )

    trust_service = SimpleNamespace(
        get_latest_certification=AsyncMock(return_value=SimpleNamespace(status="active")),
        get_agent_trust_tier=AsyncMock(return_value=SimpleNamespace(tier="certified")),
        list_pending_triggers=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=uuid4(),
                    trigger_type="policy_changed",
                    status="pending",
                    created_at=now,
                )
            ]
        ),
        list_upcoming_expirations=AsyncMock(
            return_value=[SimpleNamespace(id=uuid4(), expires_at=now, status="active")]
        ),
    )
    repository.list_regression_alerts = AsyncMock(return_value=([item_a], None))  # type: ignore[method-assign]
    repository.get_active_retirement = AsyncMock(return_value=item_b)  # type: ignore[method-assign]
    summary_repository = GovernanceSummaryRepository(repository)

    summary = await summary_repository.get_summary(
        "finance:agent",
        workspace_id,
        trust_service=trust_service,
    )
    no_trust_summary = await summary_repository.get_summary(
        "finance:agent",
        workspace_id,
        trust_service=None,
    )

    assert paged_items == [item_a]
    assert next_cursor is not None
    assert last_page_items == [item_a]
    assert last_cursor is None
    assert summary["certification_status"] == "active"
    assert summary["trust_tier"] == 3
    assert summary["pending_triggers"]
    assert summary["upcoming_expirations"]
    assert summary["active_alerts"] == [item_a]
    assert summary["active_retirement"] is item_b
    assert no_trust_summary["trust_tier"] is None
    assert _coerce_tier(True, None) == 1
    assert _coerce_tier(None, 2.8) == 2
    assert _coerce_tier(None, "provisional") == 1


@pytest.mark.asyncio
async def test_repository_adaptation_snapshot_outcome_and_proficiency_helpers() -> None:
    workspace_id = uuid4()
    now = datetime.now(UTC)
    proposal = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        status="approved",
        applied_at=now - timedelta(hours=72),
        created_at=now,
    )
    snapshot = SimpleNamespace(
        id=uuid4(),
        proposal_id=proposal.id,
        created_at=now,
        retention_expires_at=now + timedelta(days=7),
    )
    outcome = SimpleNamespace(id=uuid4(), proposal_id=proposal.id)
    proficiency = SimpleNamespace(
        id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        assessed_at=now,
        level="competent",
    )
    session = _session()
    session.execute.side_effect = [
        _ScalarResult(proposal),
        _ScalarsResult([snapshot]),
        _ScalarsResult([snapshot]),
        _ScalarResult(outcome),
        _ScalarsResult([proposal]),
        _ScalarsResult([proposal]),
        _ScalarsResult([proposal]),
        _ScalarsResult([snapshot]),
        _ScalarResult(proficiency),
        _ScalarsResult([proficiency]),
    ]
    repository = AgentOpsRepository(session)  # type: ignore[arg-type]

    assert await repository.get_open_adaptation("finance:agent", workspace_id) is proposal
    created_snapshot = await repository.create_snapshot(snapshot)
    fetched_snapshot = await repository.get_snapshot_by_proposal(proposal.id)
    listed_snapshots = await repository.list_snapshots_by_proposal(proposal.id)
    created_outcome = await repository.create_outcome(outcome)
    fetched_outcome = await repository.get_outcome_by_proposal(proposal.id)
    expired = await repository.list_proposals_past_ttl(now)
    orphaned = await repository.list_orphaned_proposals()
    pending = await repository.list_proposals_pending_outcome(now)
    stale_snapshots = await repository.list_snapshots_past_retention(now)
    created_proficiency = await repository.create_proficiency_assessment(proficiency)
    latest_proficiency = await repository.get_latest_proficiency_assessment(
        "finance:agent",
        workspace_id,
    )
    fleet = await repository.list_proficiency_fleet(workspace_id, levels=["competent"])
    await repository.delete_snapshot(snapshot)

    assert created_snapshot is snapshot
    assert fetched_snapshot is snapshot
    assert listed_snapshots == [snapshot]
    assert created_outcome is outcome
    assert fetched_outcome is outcome
    assert expired == [proposal]
    assert orphaned == [proposal]
    assert pending == [proposal]
    assert stale_snapshots == [snapshot]
    assert created_proficiency is proficiency
    assert latest_proficiency is proficiency
    assert fleet == [proficiency]
    session.delete.assert_awaited_once_with(snapshot)
