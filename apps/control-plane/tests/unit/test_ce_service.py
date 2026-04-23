from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.exceptions import (
    AbTestNotFoundError,
    InvalidProfileAssignmentError,
    ProfileConflictError,
    ProfileInUseError,
    ProfileNotFoundError,
    WorkspaceAuthorizationError,
)
from platform.context_engineering.models import (
    AbTestStatus,
    ContextSourceType,
    ProfileAssignmentLevel,
)
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.schemas import (
    AbTestCreate,
    BudgetEnvelope,
    ContextQualityScore,
    ProfileAssignmentCreate,
)
from platform.context_engineering.service import AbTestSelection, ContextEngineeringService
from types import MethodType, SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    EventProducerStub,
    MemoryContextRepository,
    PoliciesServiceStub,
    WorkspacesServiceStub,
    build_element,
    build_profile_create,
)
from tests.registry_support import ObjectStorageStub


class StaticAdapter:
    def __init__(self, elements):
        self.elements = list(elements)

    async def fetch(self, request):
        del request
        return [element.model_copy(deep=True) for element in self.elements]


class FailingAdapter:
    async def fetch(self, request):
        del request
        raise RuntimeError("boom")


def _service(
    workspace_id,
    *,
    repository: MemoryContextRepository | None = None,
    adapters=None,
    workspaces_service=None,
    clickhouse_client=None,
    object_storage=None,
    event_producer=None,
    policies_service=None,
) -> tuple[
    ContextEngineeringService,
    MemoryContextRepository,
    WorkspacesServiceStub | object | None,
    ClickHouseClientStub,
    ObjectStorageStub,
    EventProducerStub | None,
]:
    repo = repository or MemoryContextRepository()
    workspaces = workspaces_service or WorkspacesServiceStub(workspace_ids=[workspace_id])
    clickhouse = clickhouse_client or ClickHouseClientStub()
    storage = object_storage or ObjectStorageStub()
    producer = event_producer if event_producer is not None else EventProducerStub()
    service = ContextEngineeringService(
        repository=repo,
        adapters=adapters or {},
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=policies_service),
        object_storage=storage,
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=workspaces,
    )
    return service, repo, workspaces, clickhouse, storage, producer


@pytest.mark.asyncio
async def test_service_profile_crud_assignment_and_error_paths() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo, _, _, _, _ = _service(workspace_id)
    profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="default", is_default=True),
        actor_id,
    )
    updated = await service.update_profile(
        workspace_id,
        profile.id,
        build_profile_create(name="updated", is_default=False),
        actor_id,
    )
    assignment = await service.assign_profile(
        workspace_id,
        profile.id,
        ProfileAssignmentCreate(assignment_level="workspace"),
        actor_id,
    )
    assignments = await service.list_assignments(workspace_id, actor_id)
    listed = await service.list_profiles(workspace_id, actor_id)
    fetched = await service.get_profile(workspace_id, profile.id, actor_id)

    assert updated.name == "updated"
    assert assignment.assignment_level is ProfileAssignmentLevel.workspace
    assert assignments.total == 1
    assert listed.total == 1
    assert fetched.id == profile.id

    with pytest.raises(ProfileNotFoundError):
        await service.get_profile(workspace_id, uuid4(), actor_id)
    with pytest.raises(ProfileNotFoundError):
        await service.update_profile(workspace_id, uuid4(), build_profile_create(), actor_id)
    with pytest.raises(ProfileNotFoundError):
        await service.assign_profile(
            workspace_id,
            uuid4(),
            ProfileAssignmentCreate(assignment_level="workspace"),
            actor_id,
        )

    invalid_agent = ProfileAssignmentCreate.model_construct(
        assignment_level=ProfileAssignmentLevel.agent,
        agent_fqn=None,
        role_type=None,
    )
    invalid_role = ProfileAssignmentCreate.model_construct(
        assignment_level=ProfileAssignmentLevel.role_type,
        agent_fqn=None,
        role_type=None,
    )
    with pytest.raises(InvalidProfileAssignmentError):
        await service.assign_profile(workspace_id, profile.id, invalid_agent, actor_id)
    with pytest.raises(InvalidProfileAssignmentError):
        await service.assign_profile(workspace_id, profile.id, invalid_role, actor_id)

    active_ab_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="ab"),
        actor_id,
    )
    await repo.create_ab_test(
        workspace_id=workspace_id,
        name="exp",
        control_profile_id=active_ab_profile.id,
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
        created_by=actor_id,
        updated_by=actor_id,
    )
    with pytest.raises(ProfileInUseError):
        await service.delete_profile(workspace_id, profile.id, actor_id)
    with pytest.raises(ProfileInUseError):
        await service.delete_profile(workspace_id, active_ab_profile.id, actor_id)

    free_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="free"),
        actor_id,
    )
    await service.delete_profile(workspace_id, free_profile.id, actor_id)


@pytest.mark.asyncio
async def test_service_conflict_access_and_lookup_branches() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    unauthorized_service, _, _, _, _, _ = _service(
        workspace_id,
        workspaces_service=WorkspacesServiceStub(workspace_ids=[]),
    )
    with pytest.raises(WorkspaceAuthorizationError):
        await unauthorized_service.create_profile(workspace_id, build_profile_create(), actor_id)

    service, repo, _, _, _, _ = _service(workspace_id)
    profile = await service.create_profile(workspace_id, build_profile_create(), actor_id)

    async def _raise_integrity_create(self, **kwargs):
        del kwargs
        raise IntegrityError("stmt", None, Exception("duplicate"))

    repo.create_profile = MethodType(_raise_integrity_create, repo)
    with pytest.raises(ProfileConflictError):
        await service.create_profile(workspace_id, build_profile_create(name="conflict"), actor_id)
    assert repo.session.rollback_calls == 1

    service, repo, _, _, _, _ = _service(workspace_id)
    profile = await service.create_profile(workspace_id, build_profile_create(), actor_id)

    async def _raise_integrity_update(self, profile, **kwargs):
        del profile, kwargs
        raise IntegrityError("stmt", None, Exception("duplicate"))

    repo.update_profile = MethodType(_raise_integrity_update, repo)
    with pytest.raises(ProfileConflictError):
        await service.update_profile(
            workspace_id,
            profile.id,
            build_profile_create(name="dupe"),
            actor_id,
        )
    assert repo.session.rollback_calls == 1

    with pytest.raises(ProfileNotFoundError):
        await service.get_assembly_record(workspace_id, uuid4(), actor_id)
    with pytest.raises(AbTestNotFoundError):
        await service.get_ab_test(workspace_id, uuid4(), actor_id)
    with pytest.raises(AbTestNotFoundError):
        await service.end_ab_test(workspace_id, uuid4(), actor_id)


@pytest.mark.asyncio
async def test_service_resolve_profile_listing_and_private_helpers() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo, _, _, _, _ = _service(workspace_id, workspaces_service=None)

    resolved_default = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:none",
        role_type=None,
    )
    assert resolved_default.profile_id is None
    assert len(resolved_default.source_config) == 9

    with pytest.raises(ProfileNotFoundError):
        await service.resolve_profile(
            workspace_id=workspace_id,
            agent_fqn="finance:none",
            role_type=None,
            explicit_profile_id=uuid4(),
        )

    empty_profile = await repo.create_profile(
        workspace_id=workspace_id,
        created_by=actor_id,
        name="empty",
        description=None,
        is_default=False,
        source_config=[],
        budget_config={},
        compaction_strategies=[],
        quality_weights={},
        privacy_overrides={},
    )
    role_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="role"),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        role_profile.id,
        ProfileAssignmentCreate(assignment_level="role_type", role_type="executor"),
        actor_id,
    )
    await repo.create_assembly_record(
        workspace_id=workspace_id,
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        profile_id=role_profile.id,
        quality_score_pre=0.5,
        quality_score_post=0.6,
        token_count_pre=12,
        token_count_post=10,
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
    alert = await repo.create_drift_alert(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        historical_mean=0.8,
        historical_stddev=0.1,
        recent_mean=0.4,
        degradation_delta=0.4,
        analysis_window_days=7,
        suggested_actions=["review"],
    )

    explicit = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:none",
        role_type=None,
        explicit_profile_id=empty_profile.id,
    )
    role_resolved = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        role_type="executor",
    )
    records = await service.list_assembly_records(
        workspace_id,
        actor_id,
        agent_fqn="finance:agent",
        limit=10,
        offset=0,
    )
    record = await service.get_assembly_record(workspace_id, next(iter(repo.records)), actor_id)
    alerts = await service.list_drift_alerts(
        workspace_id,
        actor_id,
        resolved=None,
        limit=10,
        offset=0,
    )
    loaded_missing = await service._load_bundle("missing.json")
    merged = service._merge_budget(
        BudgetEnvelope(max_tokens_step=10),
        BudgetEnvelope(max_tokens_step=5),
    )

    assert explicit.source_config[0].source_type is ContextSourceType.system_instructions
    assert role_resolved.profile_id == role_profile.id
    assert records.total == 1
    assert record.agent_fqn == "finance:agent"
    assert alerts.items[0].id == alert.id
    assert loaded_missing is None
    assert merged.max_tokens_step == 5
    assert service._bundle_storage_key(workspace_id, uuid4(), uuid4()).endswith("/bundle.json")
    assert service._correlation(None, workspace_id=workspace_id).workspace_id == workspace_id
    assert (
        service._subscores(
            ContextQualityScore(
                relevance=1.0,
                freshness=1.0,
                authority=1.0,
                contradiction_density=1.0,
                token_efficiency=1.0,
                task_brief_coverage=1.0,
                aggregate=1.0,
            )
        )["relevance"]
        == 1.0
    )
    assert await service._assert_workspace_access(workspace_id, actor_id) is None

    service_without_access, _, _, _, _, _ = _service(
        workspace_id,
        workspaces_service=SimpleNamespace(),
    )
    assert await service_without_access._assert_workspace_access(workspace_id, actor_id) is None


@pytest.mark.asyncio
async def test_service_assemble_context_and_drift_monitor_cover_remaining_branches() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    system_element = build_element(
        source_type=ContextSourceType.system_instructions,
        content="keep context",
        origin="registry:finance:agent",
    )
    service, repo, _, clickhouse, _, producer = _service(
        workspace_id,
        adapters={
            ContextSourceType.system_instructions: StaticAdapter([system_element]),
            ContextSourceType.workflow_state: FailingAdapter(),
        },
        policies_service=PoliciesServiceStub(),
    )
    profile = await service.create_profile(
        workspace_id,
        build_profile_create(
            source_config=[
                {
                    "source_type": ContextSourceType.system_instructions.value,
                    "priority": 100,
                    "enabled": True,
                    "max_elements": 1,
                },
                {
                    "source_type": ContextSourceType.workflow_state.value,
                    "priority": 90,
                    "enabled": True,
                    "max_elements": 1,
                },
                {
                    "source_type": ContextSourceType.workspace_goal_history.value,
                    "priority": 80,
                    "enabled": True,
                    "max_elements": 1,
                },
            ],
            privacy_overrides={"excluded_source_types": ["system_instructions"]},
        ),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        profile.id,
        ProfileAssignmentCreate(assignment_level="agent", agent_fqn="finance:agent"),
        actor_id,
    )
    execution_id = uuid4()
    step_id = uuid4()
    await repo.create_assembly_record(
        workspace_id=workspace_id,
        execution_id=execution_id,
        step_id=step_id,
        agent_fqn="finance:agent",
        profile_id=profile.id,
        quality_score_pre=0.1,
        quality_score_post=0.1,
        token_count_pre=1,
        token_count_post=1,
        sources_queried=[],
        sources_available=[],
        compaction_applied=False,
        compaction_actions=[],
        privacy_exclusions=[],
        provenance_chain=[],
        bundle_storage_key="missing.json",
        ab_test_id=None,
        ab_test_group=None,
        flags=[],
    )
    selection_test_id = uuid4()

    async def _selection(*, workspace_id, agent_fqn, execution_id):
        del workspace_id, agent_fqn, execution_id
        return AbTestSelection(test_id=selection_test_id, profile_id=uuid4(), group="control")

    service._resolve_ab_test_profile = _selection  # type: ignore[method-assign]
    bundle = await service.assemble_context(
        execution_id=execution_id,
        step_id=step_id,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="retry payment",
    )

    assert "partial_sources" in bundle.flags
    assert "zero_quality" in bundle.flags
    assert bundle.token_count == 0
    assert clickhouse.insert_calls
    assert any(
        item["event_type"] == "context_engineering.assembly.completed"
        for item in producer.published
    )

    control_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="control"),
        actor_id,
    )
    variant_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="variant"),
        actor_id,
    )
    created_ab_test = await service.create_ab_test(
        workspace_id,
        AbTestCreate(
            name="experiment",
            control_profile_id=control_profile.id,
            variant_profile_id=variant_profile.id,
            target_agent_fqn="finance:agent",
        ),
        actor_id,
    )
    listed_ab_tests = await service.list_ab_tests(
        workspace_id,
        actor_id,
        status=AbTestStatus.active,
        limit=10,
        offset=0,
    )
    fetched_ab_test = await service.get_ab_test(workspace_id, created_ab_test.id, actor_id)
    ended_ab_test = await service.end_ab_test(workspace_id, created_ab_test.id, actor_id)

    unresolved_agent = "finance:existing"
    await repo.create_drift_alert(
        workspace_id=workspace_id,
        agent_fqn=unresolved_agent,
        historical_mean=0.8,
        historical_stddev=0.1,
        recent_mean=0.4,
        degradation_delta=0.4,
        analysis_window_days=7,
        suggested_actions=["review"],
    )
    clickhouse.query_responses.append(
        [
            {
                "workspace_id": workspace_id,
                "agent_fqn": "finance:zero",
                "historical_mean": 0.0,
                "historical_stddev": 0.1,
                "recent_mean": 0.1,
            },
            {
                "workspace_id": workspace_id,
                "agent_fqn": "finance:stable",
                "historical_mean": 0.8,
                "historical_stddev": 0.1,
                "recent_mean": 0.7,
            },
            {
                "workspace_id": workspace_id,
                "agent_fqn": unresolved_agent,
                "historical_mean": 0.8,
                "historical_stddev": 0.1,
                "recent_mean": 0.2,
            },
            {
                "workspace_id": workspace_id,
                "agent_fqn": "finance:drift",
                "historical_mean": 0.8,
                "historical_stddev": 0.1,
                "recent_mean": 0.2,
            },
        ]
    )
    created_alerts = await service.run_drift_analysis()

    assert listed_ab_tests.total >= 1
    assert fetched_ab_test.id == created_ab_test.id
    assert ended_ab_test.status is AbTestStatus.completed
    assert created_alerts == 1
    assert any(
        item["event_type"] == "context_engineering.drift.detected" for item in producer.published
    )

    with pytest.raises(ProfileNotFoundError):
        await service.create_ab_test(
            workspace_id,
            AbTestCreate(
                name="missing-control",
                control_profile_id=uuid4(),
                variant_profile_id=variant_profile.id,
            ),
            actor_id,
        )
    with pytest.raises(ProfileNotFoundError):
        await service.create_ab_test(
            workspace_id,
            AbTestCreate(
                name="missing-variant",
                control_profile_id=control_profile.id,
                variant_profile_id=uuid4(),
            ),
            actor_id,
        )



@pytest.mark.asyncio
async def test_service_profile_fallbacks_and_private_helpers_cover_remaining_branches() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo, _, _, _, _ = _service(workspace_id)

    original_default = await service.create_profile(
        workspace_id,
        build_profile_create(name="original-default", is_default=True),
        actor_id,
    )
    candidate = await service.create_profile(
        workspace_id,
        build_profile_create(name="candidate", is_default=False),
        actor_id,
    )
    updated = await service.update_profile(
        workspace_id,
        candidate.id,
        build_profile_create(name="candidate-default", is_default=True),
        actor_id,
    )
    assert repo.profiles[original_default.id].is_default is False
    assert updated.is_default is True

    with pytest.raises(ProfileNotFoundError):
        await service.delete_profile(workspace_id, uuid4(), actor_id)

    workspace_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="workspace-profile"),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        workspace_profile.id,
        ProfileAssignmentCreate(assignment_level="workspace"),
        actor_id,
    )

    workspace_resolved = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:unassigned",
        role_type="missing-role",
    )
    assert workspace_resolved.profile_id == workspace_profile.id

    repo.assignments.clear()
    default_resolved = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:unassigned",
        role_type="missing-role",
    )
    assert default_resolved.profile_id == updated.id

    correlation_service = service._correlation_service()
    recomputer = service._correlation_recomputer()
    assert correlation_service.repository is repo
    assert (
        recomputer.default_window_days
        == service.settings.context_engineering.correlation_window_days
    )

    no_session_service = ContextEngineeringService(
        repository=SimpleNamespace(session=SimpleNamespace()),
        adapters={},
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=None),
        object_storage=SimpleNamespace(),
        clickhouse_client=SimpleNamespace(),
        settings=PlatformSettings(),
        event_producer=None,
        workspaces_service=None,
        registry_service=None,
    )
    await no_session_service._commit()
    await no_session_service._rollback()


@pytest.mark.asyncio
async def test_service_assemble_context_budget_minimum_and_ab_metrics_paths() -> None:
    from platform.context_engineering.exceptions import BudgetExceededMinimumError

    workspace_id = uuid4()
    actor_id = uuid4()

    class _BudgetFailingCompactor:
        async def compact(self, elements, budget, strategies):
            del elements, strategies
            raise BudgetExceededMinimumError(budget.max_tokens_step, minimum_tokens=99)

        def minimum_viable_elements(self, elements):
            return list(elements[:1])

    repo = MemoryContextRepository()
    workspaces = WorkspacesServiceStub(workspace_ids=[workspace_id])
    clickhouse = ClickHouseClientStub()
    storage = ObjectStorageStub()
    producer = EventProducerStub()
    service = ContextEngineeringService(
        repository=repo,
        adapters={
            ContextSourceType.system_instructions: StaticAdapter(
                [
                    build_element(
                        source_type=ContextSourceType.system_instructions,
                        content="budget critical context",
                        token_count=50,
                        origin="registry:finance:agent",
                    )
                ]
            )
        },
        quality_scorer=QualityScorer(),
        compactor=_BudgetFailingCompactor(),
        privacy_filter=PrivacyFilter(policies_service=None),
        object_storage=storage,
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=workspaces,
        registry_service=None,
    )

    control_profile = await service.create_profile(
        workspace_id,
        build_profile_create(
            name="control",
            source_config=[
                {
                    "source_type": ContextSourceType.system_instructions.value,
                    "priority": 100,
                    "enabled": True,
                    "max_elements": 1,
                }
            ],
            budget_config={"max_tokens_step": 1, "max_sources": 1},
        ),
        actor_id,
    )
    variant_profile = await service.create_profile(
        workspace_id,
        build_profile_create(
            name="variant",
            source_config=[
                {
                    "source_type": ContextSourceType.system_instructions.value,
                    "priority": 100,
                    "enabled": True,
                    "max_elements": 1,
                }
            ],
            budget_config={"max_tokens_step": 1, "max_sources": 1},
        ),
        actor_id,
    )
    ab_test = await repo.create_ab_test(
        workspace_id=workspace_id,
        created_by=actor_id,
        updated_by=actor_id,
        name="budget-exp",
        control_profile_id=control_profile.id,
        variant_profile_id=variant_profile.id,
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

    bundle = await service.assemble_context(
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="recover payment",
    )

    assert "budget_exceeded_minimum" in bundle.flags
    assert any(
        item["event_type"] == "context_engineering.budget.exceeded_minimum"
        for item in producer.published
    )
    assert any(
        item["event_type"] == "context_engineering.assembly.completed"
        for item in producer.published
    )
    refreshed_ab_test = repo.ab_tests[ab_test.id]
    assert refreshed_ab_test.control_assembly_count + refreshed_ab_test.variant_assembly_count == 1
