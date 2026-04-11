from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.models import AbTestStatus
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.schemas import ProfileAssignmentCreate
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    ConnectorsServiceStub,
    EventProducerStub,
    ExecutionServiceStub,
    InteractionsServiceStub,
    MemoryContextRepository,
    MemoryServiceStub,
    PoliciesServiceStub,
    RegistryLookupStub,
    WorkspaceRepoStub,
    WorkspacesServiceStub,
    build_profile_create,
)
from tests.registry_support import ObjectStorageStub


def _build_service(workspace_id):
    repository = MemoryContextRepository()
    clickhouse = ClickHouseClientStub()
    storage = ObjectStorageStub()
    producer = EventProducerStub()
    workspaces = WorkspacesServiceStub(
        workspace_ids=[workspace_id],
        repo=WorkspaceRepoStub(
            workspace=SimpleNamespace(
                id=workspace_id,
                name="Finance",
                description="Handles payment operations",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            goal=SimpleNamespace(
                gid=uuid4(),
                title="Reduce payment failures",
                description="Focus on retries and exception routing",
                status="open",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ),
    )
    service = ContextEngineeringService(
        repository=repository,
        adapters=build_default_adapters(
            registry_service=RegistryLookupStub(
                agent=SimpleNamespace(
                    purpose="Verify payment exception flows",
                    approach="Use deterministic reasoning",
                    role_types=["executor"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
            execution_service=ExecutionServiceStub(),
            interactions_service=InteractionsServiceStub(
                history=[
                    {
                        "id": "history-1",
                        "content": "Retry the failed payment",
                        "timestamp": datetime.now(UTC),
                    }
                ]
            ),
            memory_service=MemoryServiceStub(),
            connectors_service=ConnectorsServiceStub(),
            workspaces_service=workspaces,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=PoliciesServiceStub()),
        object_storage=storage,
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=workspaces,
    )
    return service, repository, storage, clickhouse, producer


@pytest.mark.asyncio
async def test_assemble_context_is_deterministic_via_cached_bundle() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repository, storage, _, _ = _build_service(workspace_id)
    profile = await service.create_profile(workspace_id, build_profile_create(), actor_id)
    await service.assign_profile(
        workspace_id,
        profile.id,
        ProfileAssignmentCreate(
            assignment_level="agent",
            agent_fqn="finance:agent",
        ),
        actor_id,
    )
    execution_id = uuid4()
    step_id = uuid4()

    first = await service.assemble_context(
        execution_id=execution_id,
        step_id=step_id,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="payment retry",
    )
    second = await service.assemble_context(
        execution_id=execution_id,
        step_id=step_id,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="payment retry",
    )

    assert first.model_dump() == second.model_dump()
    assert len(repository.records) == 1
    assert storage.objects


@pytest.mark.asyncio
async def test_ab_test_group_assignment_is_deterministic_and_balanced() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repository, _, _, _ = _build_service(workspace_id)
    control = await service.create_profile(
        workspace_id, build_profile_create(name="control"), actor_id
    )
    variant = await service.create_profile(
        workspace_id, build_profile_create(name="variant"), actor_id
    )
    await repository.create_ab_test(
        workspace_id=workspace_id,
        name="exp",
        control_profile_id=control.id,
        variant_profile_id=variant.id,
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
        created_by=actor_id,
        updated_by=actor_id,
    )

    groups = {"control": 0, "variant": 0}
    selection = await service._resolve_ab_test_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        execution_id=uuid4(),
    )
    assert selection is not None
    fixed = await service._resolve_ab_test_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        execution_id=uuid4(),
    )
    assert fixed is not None

    shared_execution = uuid4()
    shared_a = await service._resolve_ab_test_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        execution_id=shared_execution,
    )
    shared_b = await service._resolve_ab_test_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        execution_id=shared_execution,
    )

    for _ in range(1000):
        result = await service._resolve_ab_test_profile(
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            execution_id=uuid4(),
        )
        assert result is not None
        groups[result.group] += 1

    assert shared_a == shared_b
    assert abs(groups["control"] - groups["variant"]) < 150
