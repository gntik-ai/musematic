from __future__ import annotations

from dataclasses import dataclass
from platform.fleets.models import FleetGovernanceChain
from platform.governance.exceptions import ChainConfigError
from platform.registry.models import AgentRoleType
from platform.registry.schemas import AgentProfileResponse
from platform.workspaces.models import WorkspaceGovernanceChain
from typing import Literal, Protocol
from uuid import UUID


class _FleetGovernanceRepo(Protocol):
    async def get_current(self, fleet_id: UUID) -> FleetGovernanceChain | None: ...


class _WorkspaceGovernanceRepo(Protocol):
    async def get_current(self, workspace_id: UUID) -> WorkspaceGovernanceChain | None: ...


class _RegistryService(Protocol):
    async def get_agent_by_fqn(
        self,
        fqn: str,
        workspace_id: UUID,
    ) -> AgentProfileResponse | None: ...


@dataclass(slots=True, frozen=True)
class ChainConfig:
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[str]
    verdict_to_action_mapping: dict[str, str]
    scope: Literal["workspace", "fleet"]


class PipelineConfigService:
    def __init__(
        self,
        *,
        fleet_governance_repo: _FleetGovernanceRepo,
        workspace_governance_repo: _WorkspaceGovernanceRepo,
        registry_service: _RegistryService | None,
    ) -> None:
        self.fleet_governance_repo = fleet_governance_repo
        self.workspace_governance_repo = workspace_governance_repo
        self.registry_service = registry_service

    async def resolve_chain(
        self,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
    ) -> ChainConfig | None:
        if workspace_id is not None:
            workspace_chain = await self.workspace_governance_repo.get_current(workspace_id)
            if workspace_chain is not None:
                return self._to_chain_config(workspace_chain, scope="workspace")
        if fleet_id is not None:
            fleet_chain = await self.fleet_governance_repo.get_current(fleet_id)
            if fleet_chain is not None:
                return self._to_chain_config(fleet_chain, scope="fleet")
        return None

    async def validate_chain_update(
        self,
        observer_fqns: list[str],
        judge_fqns: list[str],
        enforcer_fqns: list[str],
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        if workspace_id is None:
            raise ChainConfigError("workspace_id is required for governance chain validation")

        self._validate_self_referential(observer_fqns, judge_fqns, enforcer_fqns)
        await self._validate_roles(observer_fqns, AgentRoleType.observer, workspace_id)
        await self._validate_roles(judge_fqns, AgentRoleType.judge, workspace_id)
        await self._validate_roles(enforcer_fqns, AgentRoleType.enforcer, workspace_id)

    def _validate_self_referential(
        self,
        observer_fqns: list[str],
        judge_fqns: list[str],
        enforcer_fqns: list[str],
    ) -> None:
        overlaps = (
            set(observer_fqns) & set(judge_fqns)
            or set(observer_fqns) & set(enforcer_fqns)
            or set(judge_fqns) & set(enforcer_fqns)
        )
        if overlaps:
            duplicate = sorted(overlaps)[0]
            raise ChainConfigError(
                f"Agent {duplicate} cannot appear in multiple governance chain roles"
            )

    async def _validate_roles(
        self,
        fqns: list[str],
        expected_role: AgentRoleType,
        workspace_id: UUID,
    ) -> None:
        if self.registry_service is None:
            raise ChainConfigError("Registry service is required for governance chain validation")
        for fqn in fqns:
            profile = await self.registry_service.get_agent_by_fqn(fqn, workspace_id)
            if profile is None:
                raise ChainConfigError(f"Agent {fqn} not found")
            roles = {str(role) for role in profile.role_types}
            if expected_role.value not in roles:
                raise ChainConfigError(f"Agent {fqn} does not have the {expected_role.value} role")

    @staticmethod
    def _to_chain_config(
        chain: FleetGovernanceChain | WorkspaceGovernanceChain,
        *,
        scope: Literal["workspace", "fleet"],
    ) -> ChainConfig:
        return ChainConfig(
            observer_fqns=list(chain.observer_fqns),
            judge_fqns=list(chain.judge_fqns),
            enforcer_fqns=list(chain.enforcer_fqns),
            policy_binding_ids=list(chain.policy_binding_ids),
            verdict_to_action_mapping=dict(chain.verdict_to_action_mapping),
            scope=scope,
        )
