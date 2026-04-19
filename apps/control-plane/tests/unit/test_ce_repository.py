from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.models import (
    AbTestStatus,
    ContextAbTest,
    ContextDriftAlert,
    ContextEngineeringProfile,
    CorrelationClassification,
    CorrelationResult,
)
from platform.context_engineering.repository import ContextEngineeringRepository
from platform.context_engineering.schemas import BudgetEnvelope
from uuid import uuid4

import pytest

from tests.registry_support import ExecuteResultStub, SessionStub


@pytest.mark.asyncio
async def test_repository_create_mutate_and_delete_entities() -> None:
    session = SessionStub()
    repository = ContextEngineeringRepository(session)
    workspace_id = uuid4()
    profile = await repository.create_profile(
        workspace_id=workspace_id,
        created_by=uuid4(),
        name="executor",
        description=None,
        is_default=True,
        source_config=[],
        budget_config=BudgetEnvelope().model_dump(mode="json"),
        compaction_strategies=["relevance_truncation"],
        quality_weights={},
        privacy_overrides={},
    )
    assignment = await repository.create_assignment(
        workspace_id=workspace_id,
        profile_id=profile.id,
        assignment_level="workspace",
        agent_fqn=None,
        role_type=None,
    )
    record = await repository.create_assembly_record(
        workspace_id=workspace_id,
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        profile_id=profile.id,
        quality_score_pre=0.7,
        quality_score_post=0.8,
        token_count_pre=100,
        token_count_post=90,
        sources_queried=[],
        sources_available=[],
        compaction_applied=False,
        compaction_actions=[],
        privacy_exclusions=[],
        provenance_chain=[],
        bundle_storage_key="bundle.json",
        ab_test_id=None,
        ab_test_group=None,
        flags=[],
    )
    ab_test = await repository.create_ab_test(
        workspace_id=workspace_id,
        name="experiment",
        control_profile_id=profile.id,
        variant_profile_id=profile.id,
        target_agent_fqn=None,
        status=AbTestStatus.active,
        started_at=datetime.now(UTC),
        ended_at=None,
        control_assembly_count=0,
        variant_assembly_count=0,
        control_quality_mean=None,
        variant_quality_mean=None,
        control_token_mean=None,
        variant_token_mean=None,
        created_by=uuid4(),
        updated_by=uuid4(),
    )
    alert = await repository.create_drift_alert(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        historical_mean=0.8,
        historical_stddev=0.1,
        recent_mean=0.4,
        degradation_delta=0.4,
        analysis_window_days=7,
        suggested_actions=["review"],
    )

    await repository.clear_default_profiles(workspace_id)
    await repository.update_profile(profile, name="updated")
    await repository.update_ab_test_metrics(
        ab_test, group="control", quality_score=0.9, token_count=80
    )
    await repository.complete_ab_test(ab_test)
    await repository.resolve_drift_alert(alert)
    await repository.delete_profile(profile)

    assert assignment.profile_id == profile.id
    assert record.bundle_storage_key == "bundle.json"
    assert ab_test.control_assembly_count == 1
    assert ab_test.status is AbTestStatus.completed
    assert alert.resolved_at is not None
    assert session.flush_calls >= 6


@pytest.mark.asyncio
async def test_repository_getters_and_list_queries_use_session_results() -> None:
    workspace_id = uuid4()
    profile = ContextEngineeringProfile(workspace_id=workspace_id, name="executor", is_default=True)
    profile.id = uuid4()
    profile.created_at = datetime.now(UTC)
    profile.updated_at = profile.created_at
    test = ContextAbTest(
        workspace_id=workspace_id,
        name="experiment",
        control_profile_id=uuid4(),
        variant_profile_id=uuid4(),
        target_agent_fqn=None,
        status=AbTestStatus.active,
        started_at=datetime.now(UTC),
        ended_at=None,
        control_assembly_count=0,
        variant_assembly_count=0,
        control_quality_mean=None,
        variant_quality_mean=None,
        control_token_mean=None,
        variant_token_mean=None,
    )
    alert = ContextDriftAlert(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        historical_mean=0.8,
        historical_stddev=0.1,
        recent_mean=0.4,
        degradation_delta=0.4,
        analysis_window_days=7,
        suggested_actions=["review"],
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=profile),
            ExecuteResultStub(one=profile),
            ExecuteResultStub(many=[profile]),
            ExecuteResultStub(one=test),
            ExecuteResultStub(many=[test]),
            ExecuteResultStub(one=alert),
            ExecuteResultStub(many=[alert]),
        ],
        scalar_results=[1, 1, 1],
    )
    repository = ContextEngineeringRepository(session)

    fetched = await repository.get_profile(workspace_id, profile.id)
    default = await repository.get_default_profile(workspace_id)
    profiles = await repository.list_profiles(workspace_id)
    ab_test = await repository.get_ab_test(workspace_id, uuid4())
    tests, total_tests = await repository.list_ab_tests(
        workspace_id, status=None, limit=10, offset=0
    )
    unresolved = await repository.find_unresolved_drift_alert(workspace_id, "finance:agent")
    alerts, total_alerts = await repository.list_drift_alerts(
        workspace_id, resolved=None, limit=10, offset=0
    )

    assert fetched is profile
    assert default is profile
    assert profiles == [profile]
    assert ab_test is test
    assert total_tests == 1
    assert tests == [test]
    assert unresolved is alert
    assert total_alerts == 1
    assert alerts == [alert]


@pytest.mark.asyncio
async def test_repository_correlation_helpers_insert_update_and_dedupe_latest_rows() -> None:
    workspace_id = uuid4()
    now = datetime.now(UTC)
    existing = CorrelationResult(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        dimension="retrieval_accuracy",
        performance_metric="quality_score",
        window_start=now,
        window_end=now,
        coefficient=0.2,
        classification=CorrelationClassification.weak,
        data_point_count=2,
        computed_at=now,
    )
    existing.id = uuid4()
    existing.created_at = now
    existing.updated_at = now
    newer = CorrelationResult(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        dimension="retrieval_accuracy",
        performance_metric="quality_score",
        window_start=now,
        window_end=now,
        coefficient=0.9,
        classification=CorrelationClassification.strong_positive,
        data_point_count=12,
        computed_at=now,
    )
    newer.id = uuid4()
    newer.created_at = now
    newer.updated_at = now
    other = CorrelationResult(
        workspace_id=workspace_id,
        agent_fqn="ops:agent",
        dimension="instruction_adherence",
        performance_metric="quality_score",
        window_start=now,
        window_end=now,
        coefficient=-0.8,
        classification=CorrelationClassification.strong_negative,
        data_point_count=9,
        computed_at=now,
    )
    other.id = uuid4()
    other.created_at = now
    other.updated_at = now
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=None),
            ExecuteResultStub(one=existing),
            ExecuteResultStub(many=[newer, existing]),
            ExecuteResultStub(many=[other, newer]),
        ]
    )
    repository = ContextEngineeringRepository(session)
    inserted = CorrelationResult(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        dimension="retrieval_accuracy",
        performance_metric="quality_score",
        window_start=now,
        window_end=now,
        coefficient=0.7,
        classification=CorrelationClassification.strong_positive,
        data_point_count=10,
        computed_at=now,
    )
    inserted.id = uuid4()
    inserted.created_at = now
    inserted.updated_at = now
    updated = CorrelationResult(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        dimension="retrieval_accuracy",
        performance_metric="quality_score",
        window_start=now,
        window_end=now,
        coefficient=0.5,
        classification=CorrelationClassification.moderate_positive,
        data_point_count=6,
        computed_at=now,
    )
    updated.id = uuid4()
    updated.created_at = now
    updated.updated_at = now

    inserted_row = await repository.upsert_correlation_result(inserted)
    updated_row = await repository.upsert_correlation_result(updated)
    latest = await repository.get_latest_by_agent(workspace_id, "finance:agent", window_days=30)
    fleet = await repository.list_fleet_by_classification(
        workspace_id,
        classification=CorrelationClassification.strong_negative,
    )

    assert inserted_row is inserted
    assert updated_row is existing
    assert existing.coefficient == 0.5
    assert existing.classification == CorrelationClassification.moderate_positive
    assert latest == [newer]
    assert fleet == [other, newer]
    assert session.flush_calls == 2
