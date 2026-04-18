from __future__ import annotations

from platform.registry.exceptions import DecommissionImmutableError, InvalidTransitionError
from platform.registry.models import LifecycleStatus
from platform.registry.schemas import LifecycleTransitionRequest
from platform.registry.service import RegistryService
from platform.registry.state_machine import VALID_REGISTRY_TRANSITIONS
from uuid import uuid4

import pytest
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    WorkspacesServiceStub,
    build_namespace,
    build_profile,
    build_registry_settings,
)


def _service(workspace_id, actor_id):
    return RegistryService(
        repository=RegistryRepoStub(),
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
        event_producer=None,
        settings=build_registry_settings(),
    )


@pytest.mark.asyncio
async def test_decommissioned_state_is_terminal_in_state_machine_and_service() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        status=LifecycleStatus.decommissioned,
    )
    service = _service(workspace_id, actor_id)
    service.repository.profiles_by_id[profile.id] = profile
    service.repository.profiles_by_fqn[(workspace_id, profile.fqn)] = profile

    assert VALID_REGISTRY_TRANSITIONS[LifecycleStatus.decommissioned] == set()
    with pytest.raises(InvalidTransitionError):
        await service.transition_lifecycle(
            workspace_id,
            profile.id,
            LifecycleTransitionRequest(target_status=LifecycleStatus.published),
            actor_id,
        )


@pytest.mark.asyncio
async def test_fqn_reuse_after_decommission_creates_new_profile_id() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    repo = RegistryRepoStub()
    namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
    old = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="tax-reconciler",
        status=LifecycleStatus.published,
    )
    repo.profiles_by_id[old.id] = old
    repo.profiles_by_fqn[(workspace_id, old.fqn)] = old

    await repo.persist_decommission(old, reason="Regulatory retirement Q2 2026", actor_id=actor_id)
    new, created = await repo.upsert_agent_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="tax-reconciler",
        display_name="Tax Reconciler",
        purpose="A purpose long enough to satisfy the registry validation rules.",
        approach="Deterministic reasoning",
        role_types=["executor"],
        custom_role_description=None,
        tags=["finance"],
        maturity_level=2,
        actor_id=actor_id,
    )

    assert created is True
    assert new.id != old.id
    assert repo.profiles_by_id[old.id].status is LifecycleStatus.decommissioned


@pytest.mark.asyncio
async def test_decommission_metadata_cannot_be_cleared_once_set() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
    profile = build_profile(workspace_id=workspace_id, namespace=namespace)
    repo = RegistryRepoStub()
    await repo.persist_decommission(
        profile, reason="Regulatory retirement Q2 2026", actor_id=actor_id
    )

    with pytest.raises(DecommissionImmutableError):
        await repo.update_agent_profile(
            profile,
            decommissioned_at=None,
            decommission_reason=None,
            decommissioned_by=None,
        )
