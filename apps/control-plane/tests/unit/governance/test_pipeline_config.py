from __future__ import annotations

from platform.governance.exceptions import ChainConfigError
from platform.governance.services.pipeline_config import PipelineConfigService
from platform.workspaces.models import WorkspaceGovernanceChain
from uuid import uuid4

import pytest
from tests.fleet_support import build_governance_chain
from tests.registry_support import build_namespace, build_profile, build_profile_response
from tests.workspaces_support import build_workspace


class FleetRepoStub:
    def __init__(self, chain=None) -> None:
        self.chain = chain
        self.calls: list[object] = []

    async def get_current(self, fleet_id):
        self.calls.append(fleet_id)
        return self.chain


class WorkspaceRepoStub:
    def __init__(self, chain=None) -> None:
        self.chain = chain
        self.calls: list[object] = []

    async def get_current(self, workspace_id):
        self.calls.append(workspace_id)
        return self.chain


class RegistryStub:
    def __init__(self, profiles: dict[str, object]) -> None:
        self.profiles = profiles
        self.calls: list[tuple[str, object]] = []

    async def get_agent_by_fqn(self, fqn: str, workspace_id):
        self.calls.append((fqn, workspace_id))
        return self.profiles.get(fqn)


def _workspace_chain(workspace_id, **overrides) -> WorkspaceGovernanceChain:
    return WorkspaceGovernanceChain(
        workspace_id=workspace_id,
        version=1,
        observer_fqns=["observer:workspace"],
        judge_fqns=["judge:workspace"],
        enforcer_fqns=["enforcer:workspace"],
        policy_binding_ids=[str(uuid4())],
        verdict_to_action_mapping={"VIOLATION": "block"},
        is_current=True,
        is_default=False,
        **overrides,
    )


@pytest.mark.asyncio
async def test_resolve_chain_prefers_workspace_chain() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    service = PipelineConfigService(
        fleet_governance_repo=FleetRepoStub(
            build_governance_chain(fleet_id=fleet_id, workspace_id=workspace_id)
        ),
        workspace_governance_repo=WorkspaceRepoStub(_workspace_chain(workspace_id)),
        registry_service=None,
    )

    chain = await service.resolve_chain(fleet_id, workspace_id)

    assert chain is not None
    assert chain.scope == "workspace"
    assert chain.judge_fqns == ["judge:workspace"]
    assert chain.verdict_to_action_mapping == {"VIOLATION": "block"}


@pytest.mark.asyncio
async def test_validate_chain_update_accepts_valid_roles() -> None:
    workspace = build_workspace()
    namespace = build_namespace(workspace_id=workspace.id, name="platform")
    observer = build_profile(
        workspace_id=workspace.id,
        namespace=namespace,
        local_name="observer",
        role_types=["observer"],
    )
    judge = build_profile(
        workspace_id=workspace.id,
        namespace=namespace,
        local_name="judge",
        role_types=["judge"],
    )
    enforcer = build_profile(
        workspace_id=workspace.id,
        namespace=namespace,
        local_name="enforcer",
        role_types=["enforcer"],
    )
    registry = RegistryStub(
        {
            observer.fqn: build_profile_response(observer),
            judge.fqn: build_profile_response(judge),
            enforcer.fqn: build_profile_response(enforcer),
        }
    )
    service = PipelineConfigService(
        fleet_governance_repo=FleetRepoStub(),
        workspace_governance_repo=WorkspaceRepoStub(),
        registry_service=registry,
    )

    await service.validate_chain_update(
        [observer.fqn],
        [judge.fqn],
        [enforcer.fqn],
        workspace_id=workspace.id,
    )

    assert registry.calls == [
        (observer.fqn, workspace.id),
        (judge.fqn, workspace.id),
        (enforcer.fqn, workspace.id),
    ]


@pytest.mark.asyncio
async def test_validate_chain_update_rejects_role_mismatch_and_missing_agent() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="platform")
    wrong = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="executor",
        role_types=["executor"],
    )
    registry = RegistryStub({wrong.fqn: build_profile_response(wrong)})
    service = PipelineConfigService(
        fleet_governance_repo=FleetRepoStub(),
        workspace_governance_repo=WorkspaceRepoStub(),
        registry_service=registry,
    )

    with pytest.raises(ChainConfigError, match="does not have the judge role"):
        await service.validate_chain_update([], [wrong.fqn], [], workspace_id=workspace_id)

    with pytest.raises(ChainConfigError, match="not found"):
        await service.validate_chain_update([], ["platform:ghost"], [], workspace_id=workspace_id)


@pytest.mark.asyncio
async def test_validate_chain_update_rejects_self_referential_agent() -> None:
    workspace_id = uuid4()
    service = PipelineConfigService(
        fleet_governance_repo=FleetRepoStub(),
        workspace_governance_repo=WorkspaceRepoStub(),
        registry_service=RegistryStub({}),
    )

    with pytest.raises(ChainConfigError, match="cannot appear in multiple"):
        await service.validate_chain_update(
            ["platform:shared"],
            ["platform:shared"],
            ["platform:enforcer"],
            workspace_id=workspace_id,
        )
