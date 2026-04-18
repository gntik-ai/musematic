from __future__ import annotations

from datetime import UTC, datetime
from platform.common.models.user import User as PlatformUser
from platform.workspaces.models import (
    GoalStatus,
    Membership,
    Workspace,
    WorkspaceGoal,
    WorkspaceGoalState,
    WorkspaceRole,
    WorkspaceSettings,
    WorkspaceStatus,
    WorkspaceVisibilityGrant,
)
from typing import Any, cast
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class WorkspacesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_workspace(
        self,
        *,
        name: str,
        description: str | None,
        owner_id: UUID,
        is_default: bool = False,
    ) -> Workspace:
        workspace = Workspace(
            name=name,
            description=description,
            owner_id=owner_id,
            is_default=is_default,
            status=WorkspaceStatus.active,
        )
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def get_workspace_by_id(self, workspace_id: UUID, user_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                Membership.user_id == user_id,
                Workspace.status != WorkspaceStatus.deleted,
            )
        )
        return result.scalar_one_or_none()

    async def get_workspace_by_id_any(self, workspace_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.status != WorkspaceStatus.deleted,
            )
        )
        return result.scalar_one_or_none()

    async def get_workspace_by_name_for_owner(
        self,
        owner_id: UUID,
        name: str,
        *,
        exclude_workspace_id: UUID | None = None,
    ) -> Workspace | None:
        query = select(Workspace).where(
            Workspace.owner_id == owner_id,
            Workspace.name == name,
            Workspace.status != WorkspaceStatus.deleted,
        )
        if exclude_workspace_id is not None:
            query = query.where(Workspace.id != exclude_workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_workspaces_for_user(
        self,
        user_id: UUID,
        page: int,
        page_size: int,
        status_filter: WorkspaceStatus | None,
    ) -> tuple[list[Workspace], int]:
        target_status = status_filter or WorkspaceStatus.active
        total = await self.session.scalar(
            select(func.count())
            .select_from(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(
                Membership.user_id == user_id,
                Workspace.status == target_status,
            )
        )
        result = await self.session.execute(
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(
                Membership.user_id == user_id,
                Workspace.status == target_status,
            )
            .order_by(Workspace.created_at.asc(), Workspace.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_workspace(self, workspace: Workspace, **fields: Any) -> Workspace:
        for key, value in fields.items():
            setattr(workspace, key, value)
        await self.session.flush()
        return workspace

    async def archive_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.archived
        await self.session.flush()
        return workspace

    async def restore_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.active
        workspace.deleted_at = None
        await self.session.flush()
        return workspace

    async def delete_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.deleted
        workspace.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return workspace

    async def count_owned_workspaces(self, owner_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Workspace)
            .where(
                Workspace.owner_id == owner_id,
                Workspace.status == WorkspaceStatus.active,
            )
        )
        return int(total or 0)

    async def get_default_workspace_for_owner(self, owner_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(
                Workspace.owner_id == owner_id,
                Workspace.is_default.is_(True),
                Workspace.status != WorkspaceStatus.deleted,
            )
        )
        return result.scalar_one_or_none()

    async def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        role: WorkspaceRole,
    ) -> Membership:
        membership = Membership(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_membership(self, workspace_id: UUID, user_id: UUID) -> Membership | None:
        result = await self.session.execute(
            select(Membership)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == user_id,
                Workspace.status != WorkspaceStatus.deleted,
            )
        )
        return result.scalar_one_or_none()

    async def list_members(
        self,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Membership], int]:
        role_rank = case(
            (Membership.role == WorkspaceRole.owner, 0),
            (Membership.role == WorkspaceRole.admin, 1),
            (Membership.role == WorkspaceRole.member, 2),
            else_=3,
        )
        total = await self.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id)
        )
        result = await self.session.execute(
            select(Membership)
            .join(PlatformUser, PlatformUser.id == Membership.user_id, isouter=True)
            .where(Membership.workspace_id == workspace_id)
            .order_by(role_rank.asc(), PlatformUser.display_name.asc(), Membership.user_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def change_member_role(
        self,
        membership: Membership,
        new_role: WorkspaceRole,
    ) -> Membership:
        membership.role = new_role
        await self.session.flush()
        return membership

    async def remove_member(self, membership: Membership) -> None:
        await self.session.delete(membership)
        await self.session.flush()

    async def count_owners(self, workspace_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.workspace_id == workspace_id,
                Membership.role == WorkspaceRole.owner,
            )
        )
        return int(total or 0)

    async def user_exists(self, user_id: UUID) -> bool:
        existing = await self.session.scalar(
            select(func.count()).select_from(PlatformUser).where(PlatformUser.id == user_id)
        )
        return bool(existing)

    async def create_goal(
        self,
        *,
        workspace_id: UUID,
        title: str,
        description: str | None,
        created_by: UUID,
        auto_complete_timeout_seconds: int | None = None,
    ) -> WorkspaceGoal:
        goal = WorkspaceGoal(
            workspace_id=workspace_id,
            title=title,
            description=description,
            status=GoalStatus.open,
            state=WorkspaceGoalState.ready,
            auto_complete_timeout_seconds=auto_complete_timeout_seconds,
            created_by=created_by,
        )
        self.session.add(goal)
        await self.session.flush()
        return goal

    async def get_goal(self, workspace_id: UUID, goal_id: UUID) -> WorkspaceGoal | None:
        result = await self.session.execute(
            select(WorkspaceGoal).where(
                WorkspaceGoal.workspace_id == workspace_id,
                WorkspaceGoal.id == goal_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_goals(
        self,
        workspace_id: UUID,
        page: int,
        page_size: int,
        status_filter: GoalStatus | None,
    ) -> tuple[list[WorkspaceGoal], int]:
        filters = [WorkspaceGoal.workspace_id == workspace_id]
        if status_filter is not None:
            filters.append(WorkspaceGoal.status == status_filter)
        total = await self.session.scalar(
            select(func.count()).select_from(WorkspaceGoal).where(*filters)
        )
        result = await self.session.execute(
            select(WorkspaceGoal)
            .where(*filters)
            .order_by(WorkspaceGoal.created_at.asc(), WorkspaceGoal.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_goal_status(
        self,
        goal: WorkspaceGoal,
        new_status: GoalStatus,
    ) -> WorkspaceGoal:
        goal.status = new_status
        await self.session.flush()
        return goal

    async def get_visibility_grant(self, workspace_id: UUID) -> WorkspaceVisibilityGrant | None:
        result = await self.session.execute(
            select(WorkspaceVisibilityGrant).where(
                WorkspaceVisibilityGrant.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def set_visibility_grant(
        self,
        *,
        workspace_id: UUID,
        visibility_agents: list[str],
        visibility_tools: list[str],
    ) -> WorkspaceVisibilityGrant:
        existing = await self.get_visibility_grant(workspace_id)
        if existing is None:
            existing = WorkspaceVisibilityGrant(
                workspace_id=workspace_id,
                visibility_agents=visibility_agents,
                visibility_tools=visibility_tools,
            )
            self.session.add(existing)
        else:
            existing.visibility_agents = visibility_agents
            existing.visibility_tools = visibility_tools
        await self.session.flush()
        return existing

    async def delete_visibility_grant(self, workspace_id: UUID) -> bool:
        existing = await self.get_visibility_grant(workspace_id)
        if existing is None:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True

    async def get_settings(self, workspace_id: UUID) -> WorkspaceSettings | None:
        result = await self.session.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def update_settings(
        self,
        workspace_id: UUID,
        **fields: list[str] | list[UUID],
    ) -> WorkspaceSettings:
        settings = await self.get_settings(workspace_id)
        if settings is None:
            settings = WorkspaceSettings(
                workspace_id=workspace_id,
                subscribed_agents=[],
                subscribed_fleets=[],
                subscribed_policies=[],
                subscribed_connectors=[],
            )
            self.session.add(settings)
            await self.session.flush()
        for key, value in fields.items():
            setattr(settings, key, value)
        await self.session.flush()
        return settings

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(Membership.workspace_id)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .where(
                Membership.user_id == user_id,
                Workspace.status == WorkspaceStatus.active,
            )
            .order_by(Membership.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_goal_by_gid(self, goal_gid: UUID) -> WorkspaceGoal | None:
        result = await self.session.execute(
            select(WorkspaceGoal).where(WorkspaceGoal.gid == goal_gid)
        )
        return result.scalar_one_or_none()

    async def get_workspace_id_for_fleet(self, fleet_id: UUID) -> UUID | None:
        result = await self.session.execute(
            select(WorkspaceSettings.workspace_id).where(
                WorkspaceSettings.subscribed_fleets.any(cast(Any, fleet_id))
            )
        )
        return result.scalar_one_or_none()
