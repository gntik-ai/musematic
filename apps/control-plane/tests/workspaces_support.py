from __future__ import annotations

from datetime import UTC, datetime
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
from uuid import UUID, uuid4

from tests.auth_support import RecordingProducer


def build_workspace(
    *,
    workspace_id: UUID | None = None,
    owner_id: UUID | None = None,
    name: str = "Workspace",
    description: str | None = "Workspace description",
    status: WorkspaceStatus = WorkspaceStatus.active,
    is_default: bool = False,
) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(
        id=workspace_id or uuid4(),
        name=name,
        description=description,
        status=status,
        owner_id=owner_id or uuid4(),
        is_default=is_default,
    )
    workspace.created_at = now
    workspace.updated_at = now
    return workspace


def build_membership(
    *,
    membership_id: UUID | None = None,
    workspace_id: UUID | None = None,
    user_id: UUID | None = None,
    role: WorkspaceRole = WorkspaceRole.member,
) -> Membership:
    now = datetime.now(UTC)
    membership = Membership(
        id=membership_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        user_id=user_id or uuid4(),
        role=role,
    )
    membership.created_at = now
    membership.updated_at = now
    return membership


def build_goal(
    *,
    goal_id: UUID | None = None,
    workspace_id: UUID | None = None,
    created_by: UUID | None = None,
    title: str = "Goal",
    description: str | None = "Goal description",
    status: GoalStatus = GoalStatus.open,
    state: WorkspaceGoalState = WorkspaceGoalState.ready,
    auto_complete_timeout_seconds: int | None = None,
    last_message_at: datetime | None = None,
    gid: UUID | None = None,
) -> WorkspaceGoal:
    now = datetime.now(UTC)
    goal = WorkspaceGoal(
        id=goal_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by=created_by or uuid4(),
        title=title,
        description=description,
        status=status,
        state=state,
        auto_complete_timeout_seconds=auto_complete_timeout_seconds,
        last_message_at=last_message_at,
        gid=gid or uuid4(),
    )
    goal.created_at = now
    goal.updated_at = now
    return goal


def build_settings(
    *,
    settings_id: UUID | None = None,
    workspace_id: UUID | None = None,
    subscribed_agents: list[str] | None = None,
    subscribed_fleets: list[UUID] | None = None,
    subscribed_policies: list[UUID] | None = None,
    subscribed_connectors: list[UUID] | None = None,
    cost_budget: dict[str, object] | None = None,
) -> WorkspaceSettings:
    now = datetime.now(UTC)
    settings = WorkspaceSettings(
        id=settings_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        subscribed_agents=subscribed_agents or [],
        subscribed_fleets=subscribed_fleets or [],
        subscribed_policies=subscribed_policies or [],
        subscribed_connectors=subscribed_connectors or [],
        cost_budget=cost_budget or {},
    )
    settings.created_at = now
    settings.updated_at = now
    return settings


def build_visibility(
    *,
    grant_id: UUID | None = None,
    workspace_id: UUID | None = None,
    visibility_agents: list[str] | None = None,
    visibility_tools: list[str] | None = None,
) -> WorkspaceVisibilityGrant:
    now = datetime.now(UTC)
    grant = WorkspaceVisibilityGrant(
        id=grant_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        visibility_agents=visibility_agents or [],
        visibility_tools=visibility_tools or [],
    )
    grant.created_at = now
    grant.updated_at = now
    return grant


class AccountsServiceStub:
    def __init__(self, *, limit: int = 0) -> None:
        self.limit = limit
        self.calls: list[UUID] = []

    async def get_user_workspace_limit(self, user_id: UUID) -> int:
        self.calls.append(user_id)
        return self.limit


class WorkspacesRepoStub:
    def __init__(self) -> None:
        self.workspaces: dict[UUID, Workspace] = {}
        self.memberships: dict[tuple[UUID, UUID], Membership] = {}
        self.goals: dict[tuple[UUID, UUID], WorkspaceGoal] = {}
        self.settings_by_workspace: dict[UUID, WorkspaceSettings] = {}
        self.visibility_by_workspace: dict[UUID, WorkspaceVisibilityGrant] = {}
        self.conversation_workspaces: dict[UUID, UUID] = {}
        self.interaction_workspaces: dict[UUID, UUID] = {}
        self.execution_workspaces: dict[UUID, UUID] = {}
        self.fleet_workspaces: dict[UUID, UUID] = {}
        self.existing_users: set[UUID] = set()

    async def create_workspace(
        self, *, name: str, description: str | None, owner_id: UUID, is_default: bool = False
    ) -> Workspace:
        workspace = build_workspace(
            name=name, description=description, owner_id=owner_id, is_default=is_default
        )
        self.workspaces[workspace.id] = workspace
        return workspace

    async def get_workspace_by_id(self, workspace_id: UUID, user_id: UUID) -> Workspace | None:
        if (workspace_id, user_id) not in self.memberships:
            return None
        workspace = self.workspaces.get(workspace_id)
        if workspace is None or workspace.status == WorkspaceStatus.deleted:
            return None
        return workspace

    async def get_workspace_by_id_any(self, workspace_id: UUID) -> Workspace | None:
        workspace = self.workspaces.get(workspace_id)
        if workspace is None or workspace.status == WorkspaceStatus.deleted:
            return None
        return workspace

    async def get_workspace_by_name_for_owner(
        self, owner_id: UUID, name: str, *, exclude_workspace_id: UUID | None = None
    ) -> Workspace | None:
        for workspace in self.workspaces.values():
            if (
                workspace.owner_id != owner_id
                or workspace.name != name
                or workspace.status == WorkspaceStatus.deleted
            ):
                continue
            if exclude_workspace_id is not None and workspace.id == exclude_workspace_id:
                continue
            return workspace
        return None

    async def list_workspaces_for_user(
        self, user_id: UUID, page: int, page_size: int, status_filter: WorkspaceStatus | None
    ):
        target_status = status_filter or WorkspaceStatus.active
        items = [
            workspace
            for (workspace_id, member_id), _membership in self.memberships.items()
            if member_id == user_id
            for workspace in [self.workspaces[workspace_id]]
            if workspace.status == target_status
        ]
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def update_workspace(self, workspace: Workspace, **fields) -> Workspace:
        for key, value in fields.items():
            setattr(workspace, key, value)
        workspace.updated_at = datetime.now(UTC)
        return workspace

    async def archive_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.archived
        workspace.updated_at = datetime.now(UTC)
        return workspace

    async def restore_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.active
        workspace.updated_at = datetime.now(UTC)
        workspace.deleted_at = None
        return workspace

    async def delete_workspace(self, workspace: Workspace) -> Workspace:
        workspace.status = WorkspaceStatus.deleted
        workspace.deleted_at = datetime.now(UTC)
        workspace.updated_at = workspace.deleted_at
        return workspace

    async def count_owned_workspaces(self, owner_id: UUID) -> int:
        return sum(
            1
            for workspace in self.workspaces.values()
            if workspace.owner_id == owner_id and workspace.status == WorkspaceStatus.active
        )

    async def get_default_workspace_for_owner(self, owner_id: UUID) -> Workspace | None:
        for workspace in self.workspaces.values():
            if (
                workspace.owner_id == owner_id
                and workspace.is_default
                and workspace.status != WorkspaceStatus.deleted
            ):
                return workspace
        return None

    async def add_member(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> Membership:
        membership = build_membership(workspace_id=workspace_id, user_id=user_id, role=role)
        self.memberships[(workspace_id, user_id)] = membership
        return membership

    async def get_membership(self, workspace_id: UUID, user_id: UUID) -> Membership | None:
        return self.memberships.get((workspace_id, user_id))

    async def list_members(self, workspace_id: UUID, page: int, page_size: int):
        role_order = {
            WorkspaceRole.owner: 0,
            WorkspaceRole.admin: 1,
            WorkspaceRole.member: 2,
            WorkspaceRole.viewer: 3,
        }
        items = [
            membership
            for (candidate_workspace_id, _user_id), membership in self.memberships.items()
            if candidate_workspace_id == workspace_id
        ]
        items.sort(key=lambda item: (role_order[item.role], str(item.user_id)))
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def list_member_ids(self, workspace_id: UUID) -> list[UUID]:
        return [
            user_id
            for candidate_workspace_id, user_id in self.memberships
            if candidate_workspace_id == workspace_id
        ]

    async def change_member_role(
        self, membership: Membership, new_role: WorkspaceRole
    ) -> Membership:
        membership.role = new_role
        membership.updated_at = datetime.now(UTC)
        return membership

    async def remove_member(self, membership: Membership) -> None:
        self.memberships.pop((membership.workspace_id, membership.user_id), None)

    async def count_owners(self, workspace_id: UUID) -> int:
        return sum(
            1
            for (candidate_workspace_id, _user_id), membership in self.memberships.items()
            if candidate_workspace_id == workspace_id and membership.role == WorkspaceRole.owner
        )

    async def user_exists(self, user_id: UUID) -> bool:
        return user_id in self.existing_users

    async def create_goal(
        self,
        *,
        workspace_id: UUID,
        title: str,
        description: str | None,
        created_by: UUID,
        auto_complete_timeout_seconds: int | None = None,
    ) -> WorkspaceGoal:
        goal = build_goal(
            workspace_id=workspace_id,
            title=title,
            description=description,
            created_by=created_by,
            auto_complete_timeout_seconds=auto_complete_timeout_seconds,
        )
        self.goals[(workspace_id, goal.id)] = goal
        return goal

    async def get_goal(self, workspace_id: UUID, goal_id: UUID) -> WorkspaceGoal | None:
        return self.goals.get((workspace_id, goal_id))

    async def list_goals(
        self, workspace_id: UUID, page: int, page_size: int, status_filter: GoalStatus | None
    ):
        items = [
            goal
            for (candidate_workspace_id, _goal_id), goal in self.goals.items()
            if candidate_workspace_id == workspace_id
            and (status_filter is None or goal.status == status_filter)
        ]
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def update_goal_status(
        self, goal: WorkspaceGoal, new_status: GoalStatus
    ) -> WorkspaceGoal:
        goal.status = new_status
        goal.updated_at = datetime.now(UTC)
        return goal

    async def get_visibility_grant(self, workspace_id: UUID) -> WorkspaceVisibilityGrant | None:
        return self.visibility_by_workspace.get(workspace_id)

    async def set_visibility_grant(
        self, *, workspace_id: UUID, visibility_agents: list[str], visibility_tools: list[str]
    ) -> WorkspaceVisibilityGrant:
        grant = self.visibility_by_workspace.get(workspace_id)
        if grant is None:
            grant = build_visibility(
                workspace_id=workspace_id,
                visibility_agents=visibility_agents,
                visibility_tools=visibility_tools,
            )
            self.visibility_by_workspace[workspace_id] = grant
        else:
            grant.visibility_agents = visibility_agents
            grant.visibility_tools = visibility_tools
            grant.updated_at = datetime.now(UTC)
        return grant

    async def delete_visibility_grant(self, workspace_id: UUID) -> bool:
        return self.visibility_by_workspace.pop(workspace_id, None) is not None

    async def get_settings(self, workspace_id: UUID) -> WorkspaceSettings | None:
        return self.settings_by_workspace.get(workspace_id)

    async def update_settings(self, workspace_id: UUID, **fields) -> WorkspaceSettings:
        settings = self.settings_by_workspace.get(workspace_id)
        if settings is None:
            settings = build_settings(workspace_id=workspace_id)
            self.settings_by_workspace[workspace_id] = settings
        for key, value in fields.items():
            setattr(settings, key, value)
        settings.updated_at = datetime.now(UTC)
        return settings

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        return [
            workspace_id
            for (workspace_id, member_id), _membership in self.memberships.items()
            if member_id == user_id
            and self.workspaces[workspace_id].status == WorkspaceStatus.active
        ]

    async def get_goal_by_gid(self, goal_gid: UUID) -> WorkspaceGoal | None:
        for goal in self.goals.values():
            if goal.gid == goal_gid:
                return goal
        return None

    async def get_workspace_id_for_conversation(self, conversation_id: UUID) -> UUID | None:
        return self.conversation_workspaces.get(conversation_id)

    async def get_workspace_id_for_interaction(self, interaction_id: UUID) -> UUID | None:
        return self.interaction_workspaces.get(interaction_id)

    async def get_workspace_id_for_execution(self, execution_id: UUID) -> UUID | None:
        return self.execution_workspaces.get(execution_id)

    async def get_workspace_id_for_fleet(self, fleet_id: UUID) -> UUID | None:
        return self.fleet_workspaces.get(fleet_id)


class RouterServiceStub:
    def __init__(self) -> None:
        self.workspace_id = uuid4()
        self.member_user_id = uuid4()
        self.goal_id = uuid4()
        self.visibility_updated_at = datetime.now(UTC)
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def create_workspace(self, user_id, payload):
        self.calls.append(("create_workspace", (user_id, payload)))
        return {
            "id": self.workspace_id,
            "name": payload.name,
            "description": payload.description,
            "status": "active",
            "owner_id": user_id,
            "is_default": False,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def list_workspaces(self, user_id, page, page_size, status):
        self.calls.append(("list_workspaces", (user_id, page, page_size, status)))
        return {
            "items": [
                await self.create_workspace(
                    user_id, type("Payload", (), {"name": "Workspace", "description": None})()
                )
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "has_prev": page > 1,
        }

    async def get_workspace(self, workspace_id, user_id):
        self.calls.append(("get_workspace", (workspace_id, user_id)))
        return {
            "id": workspace_id,
            "name": "Workspace",
            "description": "Workspace description",
            "status": "active",
            "owner_id": user_id,
            "is_default": False,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def update_workspace(self, workspace_id, user_id, payload):
        self.calls.append(("update_workspace", (workspace_id, user_id, payload)))
        return await self.get_workspace(workspace_id, user_id)

    async def archive_workspace(self, workspace_id, user_id):
        self.calls.append(("archive_workspace", (workspace_id, user_id)))
        response = await self.get_workspace(workspace_id, user_id)
        response["status"] = "archived"
        return response

    async def restore_workspace(self, workspace_id, user_id):
        self.calls.append(("restore_workspace", (workspace_id, user_id)))
        return await self.get_workspace(workspace_id, user_id)

    async def delete_workspace(self, workspace_id, user_id, *, allow_platform_admin=False):
        self.calls.append(("delete_workspace", (workspace_id, user_id, allow_platform_admin)))
        return {"workspace_id": workspace_id, "deletion_scheduled": True}

    async def add_member(self, workspace_id, user_id, payload):
        self.calls.append(("add_member", (workspace_id, user_id, payload)))
        return {
            "id": uuid4(),
            "workspace_id": workspace_id,
            "user_id": payload.user_id,
            "role": payload.role,
            "created_at": datetime.now(UTC),
        }

    async def list_members(self, workspace_id, user_id, page, page_size):
        self.calls.append(("list_members", (workspace_id, user_id, page, page_size)))
        return {
            "items": [
                {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "user_id": self.member_user_id,
                    "role": "member",
                    "created_at": datetime.now(UTC),
                }
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "has_prev": page > 1,
        }

    async def change_member_role(self, workspace_id, requester_id, target_user_id, payload):
        self.calls.append(
            ("change_member_role", (workspace_id, requester_id, target_user_id, payload))
        )
        return {
            "id": uuid4(),
            "workspace_id": workspace_id,
            "user_id": target_user_id,
            "role": payload.role,
            "created_at": datetime.now(UTC),
        }

    async def remove_member(self, workspace_id, requester_id, target_user_id):
        self.calls.append(("remove_member", (workspace_id, requester_id, target_user_id)))
        return None

    async def create_goal(self, workspace_id, requester_id, payload):
        self.calls.append(("create_goal", (workspace_id, requester_id, payload)))
        return {
            "id": self.goal_id,
            "workspace_id": workspace_id,
            "gid": uuid4(),
            "title": payload.title,
            "description": payload.description,
            "status": "open",
            "created_by": requester_id,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def list_goals(self, workspace_id, requester_id, page, page_size, status):
        self.calls.append(("list_goals", (workspace_id, requester_id, page, page_size, status)))
        return {
            "items": [
                {
                    "id": self.goal_id,
                    "workspace_id": workspace_id,
                    "gid": uuid4(),
                    "title": "Goal",
                    "description": "Goal description",
                    "status": status or "open",
                    "created_by": requester_id,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "has_prev": page > 1,
        }

    async def get_goal(self, workspace_id, requester_id, goal_id):
        self.calls.append(("get_goal", (workspace_id, requester_id, goal_id)))
        return {
            "id": goal_id,
            "workspace_id": workspace_id,
            "gid": uuid4(),
            "title": "Goal",
            "description": "Goal description",
            "status": "open",
            "created_by": requester_id,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def update_goal_status(self, workspace_id, requester_id, goal_id, payload):
        self.calls.append(("update_goal_status", (workspace_id, requester_id, goal_id, payload)))
        response = await self.get_goal(workspace_id, requester_id, goal_id)
        response["status"] = payload.status
        return response

    async def set_visibility_grant(self, workspace_id, requester_id, payload):
        self.calls.append(("set_visibility_grant", (workspace_id, requester_id, payload)))
        return {
            "workspace_id": workspace_id,
            "visibility_agents": payload.visibility_agents,
            "visibility_tools": payload.visibility_tools,
            "updated_at": self.visibility_updated_at,
        }

    async def get_visibility_grant(self, workspace_id, requester_id):
        self.calls.append(("get_visibility_grant", (workspace_id, requester_id)))
        return {
            "workspace_id": workspace_id,
            "visibility_agents": ["finance:*"],
            "visibility_tools": ["tools:csv-reader"],
            "updated_at": self.visibility_updated_at,
        }

    async def delete_visibility_grant(self, workspace_id, requester_id):
        self.calls.append(("delete_visibility_grant", (workspace_id, requester_id)))
        return None

    async def get_settings(self, workspace_id, requester_id):
        self.calls.append(("get_settings", (workspace_id, requester_id)))
        return {
            "workspace_id": workspace_id,
            "subscribed_agents": ["finance:*"],
            "subscribed_fleets": [],
            "subscribed_policies": [],
            "subscribed_connectors": [],
            "cost_budget": {},
            "updated_at": self.visibility_updated_at,
        }

    async def update_settings(self, workspace_id, requester_id, payload):
        self.calls.append(("update_settings", (workspace_id, requester_id, payload)))
        return {
            "workspace_id": workspace_id,
            "subscribed_agents": payload.subscribed_agents or [],
            "subscribed_fleets": payload.subscribed_fleets or [],
            "subscribed_policies": payload.subscribed_policies or [],
            "subscribed_connectors": payload.subscribed_connectors or [],
            "cost_budget": payload.cost_budget or {},
            "updated_at": self.visibility_updated_at,
        }


def build_recording_producer() -> RecordingProducer:
    return RecordingProducer()
