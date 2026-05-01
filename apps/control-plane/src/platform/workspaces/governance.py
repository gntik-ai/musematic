from __future__ import annotations

from platform.workspaces.exceptions import (
    WorkspaceAuthorizationError,
    WorkspaceGovernanceNotFoundError,
    WorkspaceNotFoundError,
)
from platform.workspaces.models import WorkspaceGovernanceChain, WorkspaceRole
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.schemas import (
    WorkspaceGovernanceChainListResponse,
    WorkspaceGovernanceChainResponse,
    WorkspaceGovernanceChainUpdate,
)
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class _PipelineConfigValidator(Protocol):
    async def validate_chain_update(
        self,
        observer_fqns: list[str],
        judge_fqns: list[str],
        enforcer_fqns: list[str],
        *,
        workspace_id: UUID | None = None,
    ) -> None: ...


class WorkspaceGovernanceChainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces_repo = WorkspacesRepository(session)

    async def get_current(self, workspace_id: UUID) -> WorkspaceGovernanceChain | None:
        result = await self.session.execute(
            select(WorkspaceGovernanceChain).where(
                WorkspaceGovernanceChain.workspace_id == workspace_id,
                WorkspaceGovernanceChain.tenant_id == self.workspaces_repo._tenant_id(),
                WorkspaceGovernanceChain.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, chain: WorkspaceGovernanceChain) -> WorkspaceGovernanceChain:
        chain.tenant_id = self.workspaces_repo._tenant_id()
        current = await self.get_current(chain.workspace_id)
        if current is not None:
            current.is_current = False
        self.session.add(chain)
        await self.session.flush()
        return chain

    async def list_history(self, workspace_id: UUID) -> list[WorkspaceGovernanceChain]:
        result = await self.session.execute(
            select(WorkspaceGovernanceChain)
            .where(WorkspaceGovernanceChain.workspace_id == workspace_id)
            .where(WorkspaceGovernanceChain.tenant_id == self.workspaces_repo._tenant_id())
            .order_by(
                WorkspaceGovernanceChain.version.desc(),
                WorkspaceGovernanceChain.created_at.desc(),
            )
        )
        return list(result.scalars().all())


class WorkspaceGovernanceChainService:
    def __init__(
        self,
        *,
        workspaces_repo: WorkspacesRepository,
        governance_repo: WorkspaceGovernanceChainRepository,
        pipeline_config: _PipelineConfigValidator,
    ) -> None:
        self.workspaces_repo = workspaces_repo
        self.governance_repo = governance_repo
        self.pipeline_config = pipeline_config

    async def get_chain(
        self,
        workspace_id: UUID,
        requester_id: UUID,
    ) -> WorkspaceGovernanceChainResponse:
        await self._require_workspace_member(workspace_id, requester_id)
        chain = await self.governance_repo.get_current(workspace_id)
        if chain is None:
            raise WorkspaceGovernanceNotFoundError()
        return WorkspaceGovernanceChainResponse.model_validate(chain)

    async def update_chain(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: WorkspaceGovernanceChainUpdate,
    ) -> WorkspaceGovernanceChainResponse:
        await self._require_workspace_member(
            workspace_id,
            requester_id,
            minimum_role=WorkspaceRole.admin,
        )
        await self.pipeline_config.validate_chain_update(
            request.observer_fqns,
            request.judge_fqns,
            request.enforcer_fqns,
            workspace_id=workspace_id,
        )
        current = await self.governance_repo.get_current(workspace_id)
        version_number = 1 if current is None else current.version + 1
        chain = await self.governance_repo.create_version(
            WorkspaceGovernanceChain(
                workspace_id=workspace_id,
                version=version_number,
                observer_fqns=request.observer_fqns,
                judge_fqns=request.judge_fqns,
                enforcer_fqns=request.enforcer_fqns,
                policy_binding_ids=[str(item) for item in request.policy_binding_ids],
                verdict_to_action_mapping=request.verdict_to_action_mapping,
                is_current=True,
                is_default=False,
            )
        )
        return WorkspaceGovernanceChainResponse.model_validate(chain)

    async def get_chain_history(
        self,
        workspace_id: UUID,
        requester_id: UUID,
    ) -> WorkspaceGovernanceChainListResponse:
        await self._require_workspace_member(
            workspace_id,
            requester_id,
            minimum_role=WorkspaceRole.admin,
        )
        items = await self.governance_repo.list_history(workspace_id)
        return WorkspaceGovernanceChainListResponse(
            items=[WorkspaceGovernanceChainResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def create_default_chain(
        self,
        workspace_id: UUID,
    ) -> WorkspaceGovernanceChainResponse:
        chain = await self.governance_repo.create_version(
            WorkspaceGovernanceChain(
                workspace_id=workspace_id,
                version=1,
                observer_fqns=["platform:default-observer"],
                judge_fqns=["platform:default-judge"],
                enforcer_fqns=["platform:default-enforcer"],
                policy_binding_ids=[],
                verdict_to_action_mapping={},
                is_current=True,
                is_default=True,
            )
        )
        return WorkspaceGovernanceChainResponse.model_validate(chain)

    async def _require_workspace_member(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        minimum_role: WorkspaceRole | None = None,
    ) -> tuple[object, object]:
        workspace = await self.workspaces_repo.get_workspace_by_id_any(workspace_id)
        membership = await self.workspaces_repo.get_membership(workspace_id, requester_id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError()
        if minimum_role is None:
            return workspace, membership
        rank = {
            WorkspaceRole.viewer: 0,
            WorkspaceRole.member: 1,
            WorkspaceRole.admin: 2,
            WorkspaceRole.owner: 3,
        }
        if rank[membership.role] < rank[minimum_role]:
            raise WorkspaceAuthorizationError(
                "Insufficient workspace role for governance chain operation"
            )
        return workspace, membership
