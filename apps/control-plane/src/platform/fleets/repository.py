from __future__ import annotations

from datetime import UTC, datetime
from platform.fleets.models import (
    Fleet,
    FleetGovernanceChain,
    FleetMember,
    FleetMemberRole,
    FleetOrchestrationRules,
    FleetPolicyBinding,
    FleetStatus,
    FleetTopologyVersion,
    ObserverAssignment,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class FleetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, fleet: Fleet) -> Fleet:
        self.session.add(fleet)
        await self.session.flush()
        return fleet

    async def get_by_id(self, fleet_id: UUID, workspace_id: UUID | None = None) -> Fleet | None:
        query = select(Fleet).where(Fleet.id == fleet_id, Fleet.deleted_at.is_(None))
        if workspace_id is not None:
            query = query.where(Fleet.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name_and_workspace(
        self,
        workspace_id: UUID,
        name: str,
        *,
        exclude_fleet_id: UUID | None = None,
    ) -> Fleet | None:
        query = select(Fleet).where(
            Fleet.workspace_id == workspace_id,
            Fleet.name == name,
            Fleet.deleted_at.is_(None),
        )
        if exclude_fleet_id is not None:
            query = query.where(Fleet.id != exclude_fleet_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: FleetStatus | None = None,
        page: int,
        page_size: int,
        allowed_ids: set[UUID] | None = None,
    ) -> tuple[list[Fleet], int]:
        filters = [Fleet.workspace_id == workspace_id, Fleet.deleted_at.is_(None)]
        if status is not None:
            filters.append(Fleet.status == status)
        if allowed_ids is not None:
            if not allowed_ids:
                return [], 0
            filters.append(Fleet.id.in_(sorted(allowed_ids, key=str)))
        total = await self.session.scalar(select(func.count()).select_from(Fleet).where(*filters))
        result = await self.session.execute(
            select(Fleet)
            .where(*filters)
            .order_by(Fleet.created_at.desc(), Fleet.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_active(self) -> list[Fleet]:
        result = await self.session.execute(
            select(Fleet).where(
                Fleet.deleted_at.is_(None),
                Fleet.status.in_([FleetStatus.active, FleetStatus.degraded]),
            )
        )
        return list(result.scalars().all())

    async def list_with_active_rules(self) -> list[Fleet]:
        return await self.list_active()

    async def soft_delete(self, fleet: Fleet) -> Fleet:
        fleet.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return fleet

    async def update(self, fleet: Fleet, **fields: Any) -> Fleet:
        for key, value in fields.items():
            setattr(fleet, key, value)
        await self.session.flush()
        return fleet


class FleetMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_fleet(self, fleet_id: UUID) -> list[FleetMember]:
        result = await self.session.execute(
            select(FleetMember)
            .where(FleetMember.fleet_id == fleet_id)
            .order_by(FleetMember.joined_at.asc(), FleetMember.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, member_id: UUID, fleet_id: UUID | None = None) -> FleetMember | None:
        query = select(FleetMember).where(FleetMember.id == member_id)
        if fleet_id is not None:
            query = query.where(FleetMember.fleet_id == fleet_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_fleet_and_fqn(self, fleet_id: UUID, agent_fqn: str) -> FleetMember | None:
        result = await self.session.execute(
            select(FleetMember).where(
                FleetMember.fleet_id == fleet_id,
                FleetMember.agent_fqn == agent_fqn,
            )
        )
        return result.scalar_one_or_none()

    async def get_lead(self, fleet_id: UUID) -> FleetMember | None:
        result = await self.session.execute(
            select(FleetMember).where(
                FleetMember.fleet_id == fleet_id,
                FleetMember.role == FleetMemberRole.lead,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, member: FleetMember) -> FleetMember:
        self.session.add(member)
        await self.session.flush()
        return member

    async def remove(self, member: FleetMember) -> None:
        await self.session.delete(member)
        await self.session.flush()

    async def update_role(self, member: FleetMember, role: Any) -> FleetMember:
        member.role = role
        await self.session.flush()
        return member

    async def get_by_agent_fqn_across_fleets(self, agent_fqn: str) -> list[FleetMember]:
        result = await self.session.execute(
            select(FleetMember)
            .join(Fleet, Fleet.id == FleetMember.fleet_id)
            .where(
                FleetMember.agent_fqn == agent_fqn,
                Fleet.deleted_at.is_(None),
                Fleet.status != FleetStatus.archived,
            )
        )
        return list(result.scalars().all())


class FleetTopologyVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(self, fleet_id: UUID) -> FleetTopologyVersion | None:
        result = await self.session.execute(
            select(FleetTopologyVersion).where(
                FleetTopologyVersion.fleet_id == fleet_id,
                FleetTopologyVersion.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, version: FleetTopologyVersion) -> FleetTopologyVersion:
        current = await self.get_current(version.fleet_id)
        if current is not None:
            current.is_current = False
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_history(self, fleet_id: UUID) -> list[FleetTopologyVersion]:
        result = await self.session.execute(
            select(FleetTopologyVersion)
            .where(FleetTopologyVersion.fleet_id == fleet_id)
            .order_by(FleetTopologyVersion.version.desc(), FleetTopologyVersion.created_at.desc())
        )
        return list(result.scalars().all())


class FleetPolicyBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, binding_id: UUID, fleet_id: UUID | None = None
    ) -> FleetPolicyBinding | None:
        query = select(FleetPolicyBinding).where(FleetPolicyBinding.id == binding_id)
        if fleet_id is not None:
            query = query.where(FleetPolicyBinding.fleet_id == fleet_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_policy(self, fleet_id: UUID, policy_id: UUID) -> FleetPolicyBinding | None:
        result = await self.session.execute(
            select(FleetPolicyBinding).where(
                FleetPolicyBinding.fleet_id == fleet_id,
                FleetPolicyBinding.policy_id == policy_id,
            )
        )
        return result.scalar_one_or_none()

    async def bind(self, binding: FleetPolicyBinding) -> FleetPolicyBinding:
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def unbind(self, binding: FleetPolicyBinding) -> None:
        await self.session.delete(binding)
        await self.session.flush()

    async def list_by_fleet(self, fleet_id: UUID) -> list[FleetPolicyBinding]:
        result = await self.session.execute(
            select(FleetPolicyBinding)
            .where(FleetPolicyBinding.fleet_id == fleet_id)
            .order_by(FleetPolicyBinding.created_at.asc())
        )
        return list(result.scalars().all())


class ObserverAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        assignment_id: UUID,
        fleet_id: UUID | None = None,
    ) -> ObserverAssignment | None:
        query = select(ObserverAssignment).where(ObserverAssignment.id == assignment_id)
        if fleet_id is not None:
            query = query.where(ObserverAssignment.fleet_id == fleet_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_by_fleet_and_fqn(
        self,
        fleet_id: UUID,
        observer_fqn: str,
    ) -> ObserverAssignment | None:
        result = await self.session.execute(
            select(ObserverAssignment).where(
                ObserverAssignment.fleet_id == fleet_id,
                ObserverAssignment.observer_fqn == observer_fqn,
                ObserverAssignment.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def assign(self, assignment: ObserverAssignment) -> ObserverAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def deactivate(self, assignment: ObserverAssignment) -> ObserverAssignment:
        assignment.is_active = False
        await self.session.flush()
        return assignment

    async def list_active_by_fleet(self, fleet_id: UUID) -> list[ObserverAssignment]:
        result = await self.session.execute(
            select(ObserverAssignment).where(
                ObserverAssignment.fleet_id == fleet_id,
                ObserverAssignment.is_active.is_(True),
            )
        )
        return list(result.scalars().all())


class FleetGovernanceChainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(self, fleet_id: UUID) -> FleetGovernanceChain | None:
        result = await self.session.execute(
            select(FleetGovernanceChain).where(
                FleetGovernanceChain.fleet_id == fleet_id,
                FleetGovernanceChain.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, chain: FleetGovernanceChain) -> FleetGovernanceChain:
        current = await self.get_current(chain.fleet_id)
        if current is not None:
            current.is_current = False
        self.session.add(chain)
        await self.session.flush()
        return chain

    async def list_history(self, fleet_id: UUID) -> list[FleetGovernanceChain]:
        result = await self.session.execute(
            select(FleetGovernanceChain)
            .where(FleetGovernanceChain.fleet_id == fleet_id)
            .order_by(FleetGovernanceChain.version.desc(), FleetGovernanceChain.created_at.desc())
        )
        return list(result.scalars().all())


class FleetOrchestrationRulesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(self, fleet_id: UUID) -> FleetOrchestrationRules | None:
        result = await self.session.execute(
            select(FleetOrchestrationRules).where(
                FleetOrchestrationRules.fleet_id == fleet_id,
                FleetOrchestrationRules.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, rules: FleetOrchestrationRules) -> FleetOrchestrationRules:
        current = await self.get_current(rules.fleet_id)
        if current is not None:
            current.is_current = False
        self.session.add(rules)
        await self.session.flush()
        return rules

    async def list_history(self, fleet_id: UUID) -> list[FleetOrchestrationRules]:
        result = await self.session.execute(
            select(FleetOrchestrationRules)
            .where(FleetOrchestrationRules.fleet_id == fleet_id)
            .order_by(
                FleetOrchestrationRules.version.desc(), FleetOrchestrationRules.created_at.desc()
            )
        )
        return list(result.scalars().all())

    async def get_by_version(self, fleet_id: UUID, version: int) -> FleetOrchestrationRules | None:
        result = await self.session.execute(
            select(FleetOrchestrationRules).where(
                FleetOrchestrationRules.fleet_id == fleet_id,
                FleetOrchestrationRules.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def set_current_version(
        self, fleet_id: UUID, version: int
    ) -> FleetOrchestrationRules | None:
        target = await self.get_by_version(fleet_id, version)
        if target is None:
            return None
        history = await self.list_history(fleet_id)
        for item in history:
            item.is_current = item.id == target.id
        await self.session.flush()
        return target
