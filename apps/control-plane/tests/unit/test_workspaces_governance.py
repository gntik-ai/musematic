from __future__ import annotations

from datetime import UTC, datetime
from platform.workspaces.exceptions import (
    WorkspaceAuthorizationError,
    WorkspaceGovernanceNotFoundError,
    WorkspaceNotFoundError,
)
from platform.workspaces.governance import (
    WorkspaceGovernanceChainRepository,
    WorkspaceGovernanceChainService,
)
from platform.workspaces.models import WorkspaceGovernanceChain, WorkspaceRole
from platform.workspaces.schemas import WorkspaceGovernanceChainUpdate
from uuid import UUID, uuid4

import pytest

from tests.workspaces_support import WorkspacesRepoStub, build_membership, build_workspace


class ScalarResultStub:
    def __init__(self, items: list[object] | None = None, one: object | None = None) -> None:
        self._items = list(items or [])
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalars(self):
        items = list(self._items)
        return type("Scalars", (), {"all": lambda self: list(items)})()


class SessionStub:
    def __init__(self, *, execute_results: list[ScalarResultStub] | None = None) -> None:
        self.execute_results = list(execute_results or [])
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flush_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: object) -> ScalarResultStub:
        self.executed.append(statement)
        assert self.execute_results, f"unexpected execute call: {statement}"
        return self.execute_results.pop(0)


class GovernanceRepoStub:
    def __init__(
        self,
        *,
        current: WorkspaceGovernanceChain | None = None,
        history: list[WorkspaceGovernanceChain] | None = None,
    ) -> None:
        self.current = current
        self.history = list(history or ([] if current is None else [current]))
        self.created: list[WorkspaceGovernanceChain] = []

    async def get_current(self, workspace_id: UUID) -> WorkspaceGovernanceChain | None:
        del workspace_id
        return self.current

    async def create_version(
        self, chain: WorkspaceGovernanceChain
    ) -> WorkspaceGovernanceChain:
        chain.id = uuid4()
        chain.created_at = datetime.now(UTC)
        chain.updated_at = chain.created_at
        if self.current is not None:
            self.current.is_current = False
        self.current = chain
        self.history.insert(0, chain)
        self.created.append(chain)
        return chain

    async def list_history(self, workspace_id: UUID) -> list[WorkspaceGovernanceChain]:
        del workspace_id
        return list(self.history)


class PipelineConfigStub:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str], list[str], UUID | None]] = []

    async def validate_chain_update(
        self,
        observer_fqns: list[str],
        judge_fqns: list[str],
        enforcer_fqns: list[str],
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        self.calls.append((observer_fqns, judge_fqns, enforcer_fqns, workspace_id))


def _chain(
    workspace_id: UUID,
    *,
    version: int = 1,
    is_current: bool = True,
    is_default: bool = False,
) -> WorkspaceGovernanceChain:
    chain = WorkspaceGovernanceChain(
        id=uuid4(),
        workspace_id=workspace_id,
        version=version,
        observer_fqns=["observer:one"],
        judge_fqns=["judge:one"],
        enforcer_fqns=["enforcer:one"],
        policy_binding_ids=[],
        verdict_to_action_mapping={},
        is_current=is_current,
        is_default=is_default,
    )
    chain.created_at = datetime.now(UTC)
    chain.updated_at = chain.created_at
    return chain


@pytest.mark.asyncio
async def test_workspace_governance_repository_get_create_and_list_history() -> None:
    workspace_id = uuid4()
    current = _chain(workspace_id, version=1)
    updated = _chain(workspace_id, version=2)
    session = SessionStub(
        execute_results=[
            ScalarResultStub(one=current),
            ScalarResultStub(one=current),
            ScalarResultStub(items=[updated, current]),
        ]
    )
    repo = WorkspaceGovernanceChainRepository(session)  # type: ignore[arg-type]

    resolved = await repo.get_current(workspace_id)
    created = await repo.create_version(updated)
    history = await repo.list_history(workspace_id)

    assert resolved is current
    assert created is updated
    assert current.is_current is False
    assert session.added == [updated]
    assert session.flush_count == 1
    assert [item.version for item in history] == [2, 1]


@pytest.mark.asyncio
async def test_workspace_governance_service_get_update_history_and_defaults() -> None:
    workspace = build_workspace()
    requester_id = uuid4()
    repo = WorkspacesRepoStub()
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, requester_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=requester_id,
        role=WorkspaceRole.admin,
    )
    current = _chain(workspace.id, version=1)
    governance_repo = GovernanceRepoStub(current=current, history=[current])
    pipeline = PipelineConfigStub()
    service = WorkspaceGovernanceChainService(
        workspaces_repo=repo,  # type: ignore[arg-type]
        governance_repo=governance_repo,  # type: ignore[arg-type]
        pipeline_config=pipeline,
    )

    resolved = await service.get_chain(workspace.id, requester_id)
    updated = await service.update_chain(
        workspace.id,
        requester_id,
        WorkspaceGovernanceChainUpdate(
            observer_fqns=[" observer:two "],
            judge_fqns=["judge:two"],
            enforcer_fqns=["enforcer:two"],
            policy_binding_ids=[uuid4()],
            verdict_to_action_mapping={"VIOLATION": "block"},
        ),
    )
    history = await service.get_chain_history(workspace.id, requester_id)
    default_chain = await service.create_default_chain(uuid4())

    assert resolved.version == 1
    assert pipeline.calls == [
        (["observer:two"], ["judge:two"], ["enforcer:two"], workspace.id)
    ]
    assert updated.version == 2
    assert updated.policy_binding_ids
    assert updated.verdict_to_action_mapping == {"VIOLATION": "block"}
    assert history.total == 2
    assert [item.version for item in history.items] == [2, 1]
    assert default_chain.version == 1
    assert default_chain.is_default is True


@pytest.mark.asyncio
async def test_workspace_governance_service_raises_for_missing_chain_and_permissions() -> None:
    workspace = build_workspace()
    requester_id = uuid4()
    repo = WorkspacesRepoStub()
    governance_repo = GovernanceRepoStub(current=None)
    pipeline = PipelineConfigStub()
    service = WorkspaceGovernanceChainService(
        workspaces_repo=repo,  # type: ignore[arg-type]
        governance_repo=governance_repo,  # type: ignore[arg-type]
        pipeline_config=pipeline,
    )

    with pytest.raises(WorkspaceNotFoundError):
        await service.get_chain(workspace.id, requester_id)

    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, requester_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=requester_id,
        role=WorkspaceRole.viewer,
    )

    with pytest.raises(WorkspaceGovernanceNotFoundError):
        await service.get_chain(workspace.id, requester_id)

    with pytest.raises(WorkspaceAuthorizationError):
        await service.update_chain(
            workspace.id,
            requester_id,
            WorkspaceGovernanceChainUpdate(
                observer_fqns=["observer:one"],
                judge_fqns=["judge:one"],
                enforcer_fqns=["enforcer:one"],
            ),
        )
