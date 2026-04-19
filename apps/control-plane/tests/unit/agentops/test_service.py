from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.agentops.health.scorer import AgentHealthTarget
from platform.agentops.models import (
    AdaptationProposal,
    AgentHealthConfig,
    AgentHealthScore,
    CanaryDeployment,
    CiCdGateResult,
    GovernanceEvent,
    RetirementWorkflow,
)
from platform.agentops.repository import GovernanceSummaryRepository
from platform.agentops.schemas import (
    AdaptationReviewRequest,
    AdaptationTriggerRequest,
    CanaryDeploymentCreateRequest,
    CiCdGateResultResponse,
    GovernanceSummaryResponse,
    RetirementConfirmRequest,
    RetirementHaltRequest,
    RetirementInitiateRequest,
)
from platform.agentops.service import AgentOpsService, _coerce_target, _gate_summary
from platform.common.exceptions import NotFoundError, ValidationError
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from tests.agentops_support import build_adaptation_outcome


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
        composite_score=Decimal("88.00"),
        uptime_score=Decimal("90.00"),
        quality_score=Decimal("87.00"),
        safety_score=Decimal("92.00"),
        cost_efficiency_score=Decimal("70.00"),
        satisfaction_score=Decimal("85.00"),
        weights_snapshot={"uptime": 20.0},
        missing_dimensions=[],
        sample_counts={"uptime": 50},
        computed_at=now,
        observation_window_start=now - timedelta(days=30),
        observation_window_end=now,
        below_warning=False,
        below_critical=False,
        insufficient_data=False,
        created_at=now,
        updated_at=now,
    )


def _gate_result(workspace_id: UUID) -> CiCdGateResult:
    now = datetime.now(UTC)
    return CiCdGateResult(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        requested_by=uuid4(),
        overall_passed=True,
        policy_gate_passed=True,
        policy_gate_detail={},
        policy_gate_remediation=None,
        evaluation_gate_passed=True,
        evaluation_gate_detail={},
        evaluation_gate_remediation=None,
        certification_gate_passed=True,
        certification_gate_detail={},
        certification_gate_remediation=None,
        regression_gate_passed=True,
        regression_gate_detail={},
        regression_gate_remediation=None,
        trust_tier_gate_passed=True,
        trust_tier_gate_detail={},
        trust_tier_gate_remediation=None,
        evaluated_at=now,
        evaluation_duration_ms=10,
        created_at=now,
        updated_at=now,
    )


def _governance_event(workspace_id: UUID) -> GovernanceEvent:
    return GovernanceEvent(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        event_type="agentops.gate.checked",
        actor_id=uuid4(),
        payload={},
        created_at=datetime.now(UTC),
    )


def _adaptation(workspace_id: UUID) -> AdaptationProposal:
    now = datetime.now(UTC)
    return AdaptationProposal(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        status="proposed",
        proposal_details={"adjustments": []},
        signals=[],
        review_reason=None,
        reviewed_by=None,
        reviewed_at=None,
        candidate_revision_id=None,
        evaluation_run_id=None,
        completed_at=None,
        completion_note=None,
        created_at=now,
        updated_at=now,
    )


def _canary(workspace_id: UUID) -> CanaryDeployment:
    now = datetime.now(UTC)
    return CanaryDeployment(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        production_revision_id=uuid4(),
        canary_revision_id=uuid4(),
        initiated_by=uuid4(),
        traffic_percentage=10,
        observation_window_hours=2.0,
        quality_tolerance_pct=5.0,
        latency_tolerance_pct=5.0,
        error_rate_tolerance_pct=5.0,
        cost_tolerance_pct=5.0,
        status="active",
        started_at=now,
        observation_ends_at=now + timedelta(hours=2),
        completed_at=None,
        promoted_at=None,
        rolled_back_at=None,
        rollback_reason=None,
        manual_override_by=None,
        manual_override_reason=None,
        latest_metrics_snapshot=None,
        created_at=now,
        updated_at=now,
    )


def _retirement(workspace_id: UUID) -> RetirementWorkflow:
    now = datetime.now(UTC)
    return RetirementWorkflow(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        trigger_reason="sustained_degradation",
        trigger_detail={},
        status="grace_period",
        dependent_workflows=[],
        high_impact_flag=False,
        operator_confirmed=False,
        notifications_sent_at=now,
        grace_period_days=14,
        grace_period_starts_at=now,
        grace_period_ends_at=now + timedelta(days=14),
        retired_at=None,
        halted_at=None,
        halted_by=None,
        halt_reason=None,
        created_at=now,
        updated_at=now,
    )


def _service(workspace_id: UUID) -> tuple[AgentOpsService, SimpleNamespace]:
    repository = SimpleNamespace(
        list_regression_alerts=AsyncMock(return_value=([], None)),
        get_regression_alert=AsyncMock(return_value=None),
        update_regression_alert=AsyncMock(),
        get_current_health_score=AsyncMock(return_value=None),
        list_health_history=AsyncMock(
            return_value=([_health_score("finance:agent", workspace_id)], None)
        ),
        get_health_config=AsyncMock(return_value=_health_config(workspace_id)),
        upsert_health_config=AsyncMock(return_value=_health_config(workspace_id)),
        list_gate_results=AsyncMock(return_value=([_gate_result(workspace_id)], None)),
        get_active_canary=AsyncMock(return_value=_canary(workspace_id)),
        get_canary=AsyncMock(return_value=_canary(workspace_id)),
        list_canaries=AsyncMock(return_value=([_canary(workspace_id)], None)),
        list_governance_events=AsyncMock(return_value=([_governance_event(workspace_id)], None)),
        has_active_retirement=AsyncMock(return_value=True),
        list_adaptations=AsyncMock(return_value=([_adaptation(workspace_id)], None)),
    )
    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=SimpleNamespace(),
        trust_service=SimpleNamespace(),
        eval_suite_service=SimpleNamespace(),
        policy_service=SimpleNamespace(),
        workflow_service=SimpleNamespace(),
        registry_service=SimpleNamespace(),
        redis_client=None,
        clickhouse_client=None,
    )
    return service, repository


@pytest.mark.asyncio
async def test_service_health_regression_gate_canary_retirement_and_governance(monkeypatch) -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    alert = SimpleNamespace(
        id=uuid4(),
        status="active",
        regressed_dimensions=["quality"],
        p_value=0.01,
        effect_size=0.8,
        detected_at=datetime.now(UTC),
        resolution_reason=None,
        resolved_at=None,
        resolved_by=None,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        new_revision_id=uuid4(),
        baseline_revision_id=uuid4(),
        statistical_test="welch_t_test",
        significance_threshold=0.05,
        sample_sizes={"quality": 50},
        triggered_rollback=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.list_regression_alerts.return_value = ([alert], None)
    repository.get_regression_alert.return_value = alert
    repository.update_regression_alert.return_value = alert
    repository.get_current_health_score.return_value = _health_score("finance:agent", workspace_id)

    gate_response = CiCdGateResultResponse.model_validate(_gate_result(workspace_id))
    monkeypatch.setattr(
        service,
        "_cicd_gate",
        lambda: SimpleNamespace(evaluate=AsyncMock(return_value=gate_response)),
    )
    monkeypatch.setattr(
        service,
        "_canary_manager",
        lambda: SimpleNamespace(
            start=AsyncMock(return_value=_canary(workspace_id)),
            promote=AsyncMock(return_value=_canary(workspace_id)),
            rollback=AsyncMock(return_value=_canary(workspace_id)),
        ),
    )
    monkeypatch.setattr(
        service,
        "_retirement_manager",
        lambda: SimpleNamespace(
            initiate=AsyncMock(return_value=_retirement(workspace_id)),
            get=AsyncMock(return_value=_retirement(workspace_id)),
            halt=AsyncMock(return_value=_retirement(workspace_id)),
            confirm=AsyncMock(return_value=_retirement(workspace_id)),
        ),
    )
    monkeypatch.setattr(
        GovernanceSummaryRepository,
        "get_summary",
        AsyncMock(
            return_value={
                "certification_status": "active",
                "trust_tier": 2,
                "pending_triggers": [],
                "upcoming_expirations": [],
                "active_alerts": [],
                "active_retirement": _retirement(workspace_id),
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_adaptation_pipeline",
        lambda: SimpleNamespace(
            propose=AsyncMock(return_value=_adaptation(workspace_id)),
            review=AsyncMock(return_value=_adaptation(workspace_id)),
        ),
    )
    monkeypatch.setattr(
        service,
        "_health_scorer",
        lambda: SimpleNamespace(
            compute=AsyncMock(return_value=_health_score("finance:agent", workspace_id))
        ),
    )
    monkeypatch.setattr(
        service,
        "_canary_monitor",
        lambda: SimpleNamespace(monitor_active_canaries_task=AsyncMock()),
    )
    monkeypatch.setattr(
        service,
        "_grace_period_scanner",
        lambda: SimpleNamespace(
            retirement_grace_period_scanner_task=AsyncMock(),
            recertification_grace_period_scanner_task=AsyncMock(),
        ),
    )

    active_alerts = await service.get_active_regression_alerts(
        "finance:agent", uuid4(), workspace_id
    )
    resolved_alert = await service.resolve_regression_alert(
        alert.id,
        resolution="resolved",
        reason="ok",
        resolved_by=uuid4(),
    )
    current_health = await service.get_current_health_score("finance:agent", workspace_id)
    health = await service.get_health_score("finance:agent", workspace_id)
    history = await service.list_health_history("finance:agent", workspace_id)
    health_config = await service.get_health_config(workspace_id)
    updated_config = await service.update_health_config(workspace_id, _health_config(workspace_id))
    gate_summary = await service.run_gate_check("finance:agent", uuid4(), workspace_id, uuid4())
    gate_result = await service.evaluate_gate_check("finance:agent", uuid4(), workspace_id, uuid4())
    gate_history = await service.list_gate_checks("finance:agent", workspace_id)
    canary_payload = CanaryDeploymentCreateRequest(
        workspace_id=workspace_id,
        production_revision_id=uuid4(),
        canary_revision_id=uuid4(),
        traffic_percentage=10,
        observation_window_hours=2.0,
    )
    started_canary = await service.start_canary(
        "finance:agent",
        canary_payload,
        initiated_by=uuid4(),
    )
    active_canary = await service.get_active_canary("finance:agent", workspace_id)
    canary = await service.get_canary(_canary(workspace_id).id)
    canaries = await service.list_canaries("finance:agent", workspace_id)
    retirement_request = RetirementInitiateRequest(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        reason="reason",
        operator_confirmed=False,
    )
    retirement = await service.initiate_retirement(
        "finance:agent",
        retirement_request,
        actor=uuid4(),
    )
    fetched_retirement = await service.get_retirement(_retirement(workspace_id).id)
    halted_retirement = await service.halt_retirement(
        _retirement(workspace_id).id,
        RetirementHaltRequest(reason="halt"),
        actor=uuid4(),
    )
    confirmed_retirement = await service.confirm_retirement(
        _retirement(workspace_id).id,
        RetirementConfirmRequest(confirmed=True, reason="ok"),
        actor=uuid4(),
    )
    governance_events = await service.list_governance_events("finance:agent", workspace_id)
    governance_summary = await service.get_governance_summary("finance:agent", workspace_id)
    assert await service.is_agent_retiring("finance:agent", workspace_id) is True
    adaptation = await service.propose_adaptation(
        "finance:agent",
        AdaptationTriggerRequest(workspace_id=workspace_id, revision_id=uuid4()),
        actor=uuid4(),
    )
    reviewed_adaptation = await service.review_adaptation(
        uuid4(),
        AdaptationReviewRequest(decision="approved", reason="ok"),
        actor=uuid4(),
    )
    adaptations = await service.list_adaptations("finance:agent", workspace_id)
    assert (
        len(
            await service.score_all_agents_task(
                agent_targets=[
                    {
                        "agent_fqn": "finance:agent",
                        "workspace_id": str(workspace_id),
                        "revision_id": str(uuid4()),
                    }
                ]
            )
        )
        == 1
    )
    await service.monitor_active_canaries_task()
    await service.retirement_grace_period_scanner_task()
    await service.recertification_grace_period_scanner_task()

    assert len(active_alerts) == 1
    assert resolved_alert.status == "resolved"
    assert current_health is not None
    assert current_health.composite_score == Decimal("88.00")
    assert health.agent_fqn == "finance:agent"
    assert history.items
    assert health_config.workspace_id == workspace_id
    assert updated_config.workspace_id == workspace_id
    assert gate_summary.overall_passed is True
    assert gate_result.overall_passed is True
    assert gate_history.items
    assert started_canary.agent_fqn == "finance:agent"
    assert active_canary is not None
    assert active_canary.agent_fqn == "finance:agent"
    assert canary.agent_fqn == "finance:agent"
    assert canaries.items
    assert retirement.agent_fqn == "finance:agent"
    assert fetched_retirement.agent_fqn == "finance:agent"
    assert halted_retirement.agent_fqn == "finance:agent"
    assert confirmed_retirement.agent_fqn == "finance:agent"
    assert governance_events.items
    assert isinstance(governance_summary, GovernanceSummaryResponse)
    assert adaptation.agent_fqn == "finance:agent"
    assert reviewed_adaptation.agent_fqn == "finance:agent"
    assert adaptations.items


@pytest.mark.asyncio
async def test_service_error_and_placeholder_paths() -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    repository.get_regression_alert.return_value = None
    repository.get_current_health_score.return_value = None
    repository.get_health_config.return_value = _health_config(workspace_id)
    repository.has_active_retirement.return_value = False

    with pytest.raises(NotFoundError):
        await service.get_regression_alert(uuid4())
    with pytest.raises(ValidationError):
        await service.evaluate_gate_check("finance:agent", uuid4(), workspace_id, UUID(int=0))

    placeholder = await service.get_health_score("finance:agent", workspace_id)
    assert placeholder.insufficient_data is True
    assert await service.is_agent_retiring("finance:agent", workspace_id) is False


def test_service_helper_functions_cover_target_and_gate_summary() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    target = _coerce_target(
        {
            "agent_fqn": "finance:agent",
            "workspace_id": str(workspace_id),
            "revision_id": str(revision_id),
        },
        default_workspace_id=None,
    )
    invalid = _coerce_target({"agent_fqn": "finance:agent"}, default_workspace_id=None)
    summary = _gate_summary(CiCdGateResultResponse.model_validate(_gate_result(workspace_id)))

    assert target is not None
    assert invalid is None
    assert summary.summary["evaluation_duration_ms"] == 10


@pytest.mark.asyncio
async def test_service_covers_successful_lookup_and_wrapper_branches(monkeypatch) -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    alert = SimpleNamespace(
        id=uuid4(),
        status="active",
        regressed_dimensions=["quality"],
        p_value=0.02,
        effect_size=0.7,
        detected_at=datetime.now(UTC),
        resolution_reason=None,
        resolved_at=None,
        resolved_by=None,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        new_revision_id=uuid4(),
        baseline_revision_id=uuid4(),
        statistical_test="welch_t_test",
        significance_threshold=0.05,
        sample_sizes={"quality": 10},
        triggered_rollback=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.list_regression_alerts.return_value = ([alert], "next-alert")
    repository.get_regression_alert.return_value = alert
    repository.get_active_canary.return_value = None
    repository.get_canary.return_value = None
    repository.list_canaries.return_value = ([], None)
    repository.list_governance_events.return_value = ([_governance_event(workspace_id)], "next-gov")
    repository.list_adaptations.return_value = ([_adaptation(workspace_id)], "next-adapt")
    repository.get_health_config.return_value = None
    repository.upsert_health_config.return_value = _health_config(workspace_id)
    repository.has_active_retirement.return_value = False
    repository.get_current_health_score.return_value = _health_score("finance:agent", workspace_id)
    manager = SimpleNamespace(
        promote=AsyncMock(return_value=_canary(workspace_id)),
        rollback=AsyncMock(return_value=_canary(workspace_id)),
    )
    retirement_manager = SimpleNamespace(
        initiate=AsyncMock(return_value=_retirement(workspace_id)),
    )
    canary_monitor = SimpleNamespace(monitor_active_canaries_task=AsyncMock())
    scanner = SimpleNamespace(
        retirement_grace_period_scanner_task=AsyncMock(),
        recertification_grace_period_scanner_task=AsyncMock(),
    )
    monkeypatch.setattr(service, "_canary_manager", lambda: manager)
    monkeypatch.setattr(service, "_retirement_manager", lambda: retirement_manager)
    monkeypatch.setattr(service, "_canary_monitor", lambda: canary_monitor)
    monkeypatch.setattr(service, "_grace_period_scanner", lambda: scanner)
    monkeypatch.setattr(
        GovernanceSummaryRepository,
        "get_summary",
        AsyncMock(
            return_value={
                "certification_status": None,
                "trust_tier": None,
                "pending_triggers": [],
                "upcoming_expirations": [],
                "active_alerts": [],
                "active_retirement": None,
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_adaptation_pipeline",
        lambda: SimpleNamespace(
            propose=AsyncMock(return_value=_adaptation(workspace_id)),
            review=AsyncMock(return_value=_adaptation(workspace_id)),
        ),
    )

    alerts = await service.list_regression_alerts("finance:agent", workspace_id, status="active")
    fetched_alert = await service.get_regression_alert(alert.id)
    assert await service.get_active_canary("finance:agent", workspace_id) is None
    with pytest.raises(NotFoundError):
        await service.get_canary(uuid4())
    listed_canaries = await service.list_canaries("finance:agent", workspace_id)
    promoted = await service.promote_canary(
        uuid4(),
        SimpleNamespace(reason="promote"),
        actor=uuid4(),
    )
    rolled_back = await service.rollback_canary(
        uuid4(),
        SimpleNamespace(reason="rollback"),
        actor=uuid4(),
    )
    initiated = await service.initiate_retirement_from_trigger(
        "finance:agent",
        uuid4(),
        workspace_id,
        trigger_reason="triggered",
    )
    governance_events = await service.list_governance_events("finance:agent", workspace_id)
    governance_summary = await service.get_governance_summary("finance:agent", workspace_id)
    adaptation_history = await service.list_adaptations("finance:agent", workspace_id)
    await service.monitor_active_canaries_task()
    await service.retirement_grace_period_scanner_task()
    await service.recertification_grace_period_scanner_task()

    assert alerts.next_cursor == "next-alert"
    assert fetched_alert.id == alert.id
    assert listed_canaries.items == []
    assert promoted.agent_fqn == "finance:agent"
    assert rolled_back.agent_fqn == "finance:agent"
    assert initiated.agent_fqn == "finance:agent"
    assert governance_events.next_cursor == "next-gov"
    assert isinstance(governance_summary, GovernanceSummaryResponse)
    assert adaptation_history.next_cursor == "next-adapt"


@pytest.mark.asyncio
async def test_service_task_and_constructor_helpers_cover_invalid_targets_and_defaults() -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    repository.get_health_config.return_value = None
    repository.upsert_health_config.return_value = _health_config(workspace_id)
    service.registry_service = None

    scorer = service._health_scorer()
    detector = service.regression_detector(alpha=0.1, minimum_sample_size=5)
    gate = service._cicd_gate()
    canary_manager = service._canary_manager()
    canary_monitor = service._canary_monitor()
    retirement_manager = service._retirement_manager()
    grace_scanner = service._grace_period_scanner()
    adaptation_pipeline = service._adaptation_pipeline()
    empty_result = await service.score_all_agents_task(workspace_id=workspace_id)
    skipped_result = await service.score_all_agents_task(
        workspace_id=workspace_id,
        agent_targets=[{"agent_fqn": "finance:agent"}],
    )
    created = await service.get_health_config(workspace_id)
    placeholder = await service.get_health_score("finance:agent", workspace_id)

    object_target = _coerce_target(
        SimpleNamespace(
            agent_fqn="finance:agent",
            workspace_id=str(workspace_id),
            revision_id=str(uuid4()),
        ),
        default_workspace_id=None,
    )
    invalid_object_target = _coerce_target(
        SimpleNamespace(agent_fqn="finance:agent", workspace_id="bad", revision_id="bad"),
        default_workspace_id=None,
    )

    assert scorer.repository is repository
    assert detector.alpha == 0.1
    assert gate.repository is repository
    assert canary_manager.redis_client is service.redis_client
    assert canary_monitor.repository is repository
    assert retirement_manager.registry_service is service.registry_service
    assert grace_scanner.repository is repository
    assert adaptation_pipeline.repository is repository
    assert empty_result == []
    assert skipped_result == []
    assert created.workspace_id == workspace_id
    assert placeholder.insufficient_data is True
    assert object_target is not None
    assert invalid_object_target is None


@pytest.mark.asyncio
async def test_service_adaptation_and_proficiency_methods_cover_new_delegations(
    monkeypatch,
) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repository = _service(workspace_id)
    proposal = _adaptation(workspace_id)
    proposal.status = "promoted"
    snapshot = SimpleNamespace(
        id=uuid4(),
        snapshot_type=SimpleNamespace(value="pre_apply"),
        configuration_hash="sha256:pre",
        configuration={"profile_fields": {"tags": ["finance"]}},
        revision_id=uuid4(),
        retention_expires_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    outcome = build_adaptation_outcome(proposal_id=proposal.id)
    repository.get_adaptation = AsyncMock(return_value=proposal)
    repository.list_snapshots_by_proposal = AsyncMock(return_value=[snapshot])
    repository.get_outcome_by_proposal = AsyncMock(return_value=outcome)

    apply_response = SimpleNamespace(kind="apply")
    rollback_response = SimpleNamespace(kind="rollback")
    outcome_response = SimpleNamespace(kind="outcome")
    proficiency_response = SimpleNamespace(kind="proficiency")
    history_response = SimpleNamespace(kind="history")
    fleet_response = SimpleNamespace(kind="fleet")
    monkeypatch.setattr(
        service,
        "_adaptation_pipeline",
        lambda: SimpleNamespace(revoke_approval=AsyncMock(return_value=proposal)),
    )
    monkeypatch.setattr(
        service,
        "_adaptation_apply_service",
        lambda: SimpleNamespace(apply=AsyncMock(return_value=apply_response)),
    )
    monkeypatch.setattr(
        service,
        "_adaptation_rollback_service",
        lambda: SimpleNamespace(rollback=AsyncMock(return_value=rollback_response)),
    )
    monkeypatch.setattr(
        service,
        "_adaptation_outcome_service",
        lambda: SimpleNamespace(get_outcome=AsyncMock(return_value=outcome_response)),
    )
    monkeypatch.setattr(
        service,
        "_proficiency_service",
        lambda: SimpleNamespace(
            get_current=AsyncMock(return_value=proficiency_response),
            list_history=AsyncMock(return_value=history_response),
            query_fleet=AsyncMock(return_value=fleet_response),
        ),
    )

    revoked = await service.revoke_adaptation_approval(proposal.id, reason="hold", actor=actor_id)
    applied = await service.apply_adaptation(proposal.id, actor=actor_id, reason="ship")
    rolled_back = await service.rollback_adaptation(proposal.id, actor=actor_id, reason="undo")
    measured_outcome = await service.get_adaptation_outcome(proposal.id)
    lineage = await service.get_adaptation_lineage(proposal.id)
    proficiency = await service.get_proficiency("finance:agent", workspace_id)
    history = await service.list_proficiency_history("finance:agent", workspace_id)
    fleet = await service.query_proficiency_fleet(
        workspace_id,
        level_at_or_below="competent",
        level="novice",
    )

    assert revoked.proposal.id == proposal.id
    assert applied is apply_response
    assert rolled_back is rollback_response
    assert measured_outcome is outcome_response
    assert lineage.proposal.status == "promoted"
    assert lineage.snapshot is not None
    assert lineage.snapshot["pre_apply"]["configuration_hash"] == "sha256:pre"
    assert lineage.outcome is not None
    assert proficiency is proficiency_response
    assert history is history_response
    assert fleet is fleet_response


@pytest.mark.asyncio
async def test_service_get_adaptation_lineage_raises_for_missing_proposal() -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    repository.get_adaptation = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await service.get_adaptation_lineage(uuid4())


def test_service_adaptation_helpers_use_settings_and_cache_analyzer() -> None:
    workspace_id = uuid4()
    service, repository = _service(workspace_id)
    service.settings = SimpleNamespace(
        agentops=SimpleNamespace(
            adaptation_proposal_ttl_hours=12,
            adaptation_rollback_retention_days=15,
            adaptation_observation_window_hours=48,
            adaptation_min_observations_per_dimension=7,
            adaptation_proficiency_dwell_time_hours=36,
        )
    )

    analyzer = service._behavioral_analyzer()
    apply_service = service._adaptation_apply_service()
    rollback_service = service._adaptation_rollback_service()
    outcome_service = service._adaptation_outcome_service()
    proficiency_service = service._proficiency_service()
    recomputer = service._proficiency_recomputer()
    target = AgentHealthTarget(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
    )

    assert analyzer is service._behavioral_analyzer()
    assert apply_service.repository is repository
    assert apply_service.rollback_retention_days == 15
    assert apply_service.observation_window_hours == 48
    assert rollback_service.repository is repository
    assert outcome_service.observation_window_hours == 48
    assert proficiency_service.min_observations_per_dimension == 7
    assert proficiency_service.dwell_time_hours == 36
    assert recomputer.proficiency_service.repository is repository
    assert service._proposal_ttl_hours() == 12
    assert service._rollback_retention_days() == 15
    assert service._observation_window_hours() == 48
    assert service._min_observations_per_dimension() == 7
    assert service._proficiency_dwell_time_hours() == 36
    assert _coerce_target(target, default_workspace_id=None) is target
