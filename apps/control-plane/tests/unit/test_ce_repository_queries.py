from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.models import (
    AbTestStatus,
    ContextAbTest,
    ContextAssemblyRecord,
    ContextDriftAlert,
    ContextProfileAssignment,
    ProfileAssignmentLevel,
)
from platform.context_engineering.repository import ContextEngineeringRepository
from uuid import uuid4

import pytest

from tests.registry_support import ExecuteResultStub, SessionStub


def _assignment(*, workspace_id, profile_id, level, agent_fqn=None, role_type=None):
    assignment = ContextProfileAssignment(
        workspace_id=workspace_id,
        profile_id=profile_id,
        assignment_level=level,
        agent_fqn=agent_fqn,
        role_type=role_type,
    )
    assignment.id = uuid4()
    assignment.created_at = datetime.now(UTC)
    return assignment


@pytest.mark.asyncio
async def test_repository_create_assignment_reuses_existing_targets() -> None:
    workspace_id = uuid4()
    first_profile_id = uuid4()
    second_profile_id = uuid4()
    existing_agent = _assignment(
        workspace_id=workspace_id,
        profile_id=first_profile_id,
        level=ProfileAssignmentLevel.agent,
        agent_fqn="finance:agent",
    )
    existing_role = _assignment(
        workspace_id=workspace_id,
        profile_id=first_profile_id,
        level=ProfileAssignmentLevel.role_type,
        role_type="executor",
    )
    existing_workspace = _assignment(
        workspace_id=workspace_id,
        profile_id=first_profile_id,
        level=ProfileAssignmentLevel.workspace,
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=existing_agent),
            ExecuteResultStub(one=existing_role),
            ExecuteResultStub(one=existing_workspace),
        ]
    )
    repository = ContextEngineeringRepository(session)

    updated_agent = await repository.create_assignment(
        workspace_id=workspace_id,
        profile_id=second_profile_id,
        assignment_level=ProfileAssignmentLevel.agent,
        agent_fqn="finance:agent",
        role_type=None,
    )
    updated_role = await repository.create_assignment(
        workspace_id=workspace_id,
        profile_id=second_profile_id,
        assignment_level=ProfileAssignmentLevel.role_type,
        agent_fqn=None,
        role_type="executor",
    )
    updated_workspace = await repository.create_assignment(
        workspace_id=workspace_id,
        profile_id=second_profile_id,
        assignment_level=ProfileAssignmentLevel.workspace,
        agent_fqn=None,
        role_type=None,
    )

    assert updated_agent is existing_agent
    assert updated_role is existing_role
    assert updated_workspace is existing_workspace
    assert all(
        item.profile_id == second_profile_id
        for item in (updated_agent, updated_role, updated_workspace)
    )


@pytest.mark.asyncio
async def test_repository_query_helpers_cover_filtered_paths() -> None:
    workspace_id = uuid4()
    agent_assignment = _assignment(
        workspace_id=workspace_id,
        profile_id=uuid4(),
        level=ProfileAssignmentLevel.agent,
        agent_fqn="finance:agent",
    )
    role_assignment = _assignment(
        workspace_id=workspace_id,
        profile_id=uuid4(),
        level=ProfileAssignmentLevel.role_type,
        role_type="executor",
    )
    workspace_assignment = _assignment(
        workspace_id=workspace_id,
        profile_id=uuid4(),
        level=ProfileAssignmentLevel.workspace,
    )
    record = ContextAssemblyRecord(
        workspace_id=workspace_id,
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        profile_id=None,
        quality_score_pre=0.6,
        quality_score_post=0.8,
        token_count_pre=100,
        token_count_post=80,
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
    record.id = uuid4()
    record.created_at = datetime.now(UTC)
    ab_test = ContextAbTest(
        workspace_id=workspace_id,
        name="experiment",
        control_profile_id=uuid4(),
        variant_profile_id=uuid4(),
        target_agent_fqn="finance:agent",
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
    ab_test.id = uuid4()
    ab_test.created_at = datetime.now(UTC)
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
    alert.id = uuid4()
    alert.created_at = datetime.now(UTC)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(many=[agent_assignment]),
            ExecuteResultStub(one=agent_assignment),
            ExecuteResultStub(one=role_assignment),
            ExecuteResultStub(one=workspace_assignment),
            ExecuteResultStub(one=record),
            ExecuteResultStub(one=record),
            ExecuteResultStub(many=[record]),
            ExecuteResultStub(one=ab_test),
            ExecuteResultStub(many=[ab_test]),
            ExecuteResultStub(one=alert),
            ExecuteResultStub(many=[alert]),
            ExecuteResultStub(many=[alert]),
        ],
        scalar_results=[2, 1, 1, 1, 1, 1],
    )
    repository = ContextEngineeringRepository(session)

    assignments = await repository.list_assignments(workspace_id, profile_id=None)
    fetched_agent = await repository.get_assignment_by_agent_fqn(workspace_id, "finance:agent")
    fetched_role = await repository.get_assignment_by_role_type(workspace_id, "executor")
    fetched_workspace = await repository.get_workspace_default_assignment(workspace_id)
    by_execution = await repository.find_assembly_record_by_execution_step(
        workspace_id,
        record.execution_id,
        record.step_id,
    )
    by_id = await repository.get_assembly_record(workspace_id, record.id)
    records, record_total = await repository.list_assembly_records(
        workspace_id,
        agent_fqn="finance:agent",
        limit=10,
        offset=0,
    )
    active = await repository.get_active_ab_test(workspace_id, "finance:agent")
    ab_tests, ab_total = await repository.list_ab_tests(
        workspace_id,
        status=AbTestStatus.active,
        limit=10,
        offset=0,
    )
    unresolved = await repository.find_unresolved_drift_alert(workspace_id, "finance:agent")
    resolved_alerts, resolved_total = await repository.list_drift_alerts(
        workspace_id,
        resolved=True,
        limit=10,
        offset=0,
    )
    unresolved_alerts, unresolved_total = await repository.list_drift_alerts(
        workspace_id,
        resolved=False,
        limit=10,
        offset=0,
    )

    assert assignments == [agent_assignment]
    assert fetched_agent is agent_assignment
    assert fetched_role is role_assignment
    assert fetched_workspace is workspace_assignment
    assert by_execution is record
    assert by_id is record
    assert records == [record]
    assert record_total == 2
    assert active is ab_test
    assert ab_tests == [ab_test]
    assert ab_total == 1
    assert unresolved is alert
    assert resolved_alerts == [alert]
    assert resolved_total == 1
    assert unresolved_alerts == [alert]
    assert unresolved_total == 1


@pytest.mark.asyncio
async def test_repository_boolean_helpers_and_variant_metrics() -> None:
    session = SessionStub(scalar_results=[0, 1])
    repository = ContextEngineeringRepository(session)
    ab_test = ContextAbTest(
        workspace_id=uuid4(),
        name="experiment",
        control_profile_id=uuid4(),
        variant_profile_id=uuid4(),
        target_agent_fqn=None,
        status=AbTestStatus.active,
        started_at=datetime.now(UTC),
        ended_at=None,
        control_assembly_count=0,
        variant_assembly_count=1,
        control_quality_mean=None,
        variant_quality_mean=0.5,
        control_token_mean=None,
        variant_token_mean=20.0,
    )

    has_assignments = await repository.profile_has_assignments(uuid4())
    has_active_tests = await repository.profile_has_active_ab_tests(uuid4())
    updated = await repository.update_ab_test_metrics(
        ab_test,
        group="variant",
        quality_score=1.0,
        token_count=40,
    )

    assert has_assignments is False
    assert has_active_tests is True
    assert updated.variant_assembly_count == 2
    assert updated.variant_quality_mean == 0.75
    assert updated.variant_token_mean == 30.0
    assert repository._rolling_mean(0.5, 2, 1.0) == pytest.approx(2 / 3)
