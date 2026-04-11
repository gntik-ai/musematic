from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.exceptions import ProfileInUseError
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.schemas import ProfileAssignmentCreate
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    EventProducerStub,
    MemoryContextRepository,
    PoliciesServiceStub,
    RegistryLookupStub,
    WorkspaceRepoStub,
    WorkspacesServiceStub,
    build_profile_create,
)
from tests.registry_support import ObjectStorageStub


def _service(workspace_id):
    repo = MemoryContextRepository()
    workspaces = WorkspacesServiceStub(
        workspace_ids=[workspace_id],
        repo=WorkspaceRepoStub(
            workspace=SimpleNamespace(
                id=workspace_id,
                name="Finance",
                description="Finance",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ),
    )
    return ContextEngineeringService(
        repository=repo,
        adapters=build_default_adapters(
            registry_service=RegistryLookupStub(
                agent=SimpleNamespace(
                    purpose="Do work",
                    approach="Be deterministic",
                    role_types=["executor"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
            workspaces_service=workspaces,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=PoliciesServiceStub()),
        object_storage=ObjectStorageStub(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=EventProducerStub(),
        workspaces_service=workspaces,
    ), repo


@pytest.mark.asyncio
async def test_profile_management_precedence_and_delete_guards() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo = _service(workspace_id)
    workspace_default = await service.create_profile(
        workspace_id,
        build_profile_create(name="workspace-default", is_default=True),
        actor_id,
    )
    role_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="role-profile"),
        actor_id,
    )
    agent_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="agent-profile"),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        role_profile.id,
        ProfileAssignmentCreate(
            assignment_level="role_type",
            role_type="executor",
        ),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        agent_profile.id,
        ProfileAssignmentCreate(
            assignment_level="agent",
            agent_fqn="finance:agent",
        ),
        actor_id,
    )

    resolved = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        role_type="executor",
    )
    fallback = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:other",
        role_type="executor",
    )
    default = await service.resolve_profile(
        workspace_id=workspace_id,
        agent_fqn="finance:none",
        role_type=None,
    )

    assert resolved.profile_id == agent_profile.id
    assert fallback.profile_id == role_profile.id
    assert default.profile_id == workspace_default.id
    assert (await service.list_profiles(workspace_id, actor_id)).total == 3

    with pytest.raises(ProfileInUseError):
        await service.delete_profile(workspace_id, agent_profile.id, actor_id)

    free_profile = await service.create_profile(
        workspace_id,
        build_profile_create(name="free-profile"),
        actor_id,
    )
    await service.delete_profile(workspace_id, free_profile.id, actor_id)

    assert free_profile.id not in repo.profiles
