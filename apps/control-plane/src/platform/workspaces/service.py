from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.workspaces.events import (
    GoalPayload,
    MembershipPayload,
    VisibilityGrantPayload,
    WorkspacePayload,
    publish_goal_created,
    publish_goal_status_changed,
    publish_membership_added,
    publish_membership_removed,
    publish_membership_role_changed,
    publish_visibility_grant_updated,
    publish_workspace_archived,
    publish_workspace_created,
    publish_workspace_deleted,
    publish_workspace_restored,
    publish_workspace_updated,
)
from platform.workspaces.exceptions import (
    GoalNotFoundError,
    LastOwnerError,
    MemberAlreadyExistsError,
    MemberNotFoundError,
    VisibilityGrantNotFoundError,
    WorkspaceAuthorizationError,
    WorkspaceLimitError,
    WorkspaceNameConflictError,
    WorkspaceNotFoundError,
    WorkspaceStateConflictError,
)
from platform.workspaces.models import (
    GoalStatus,
    Membership,
    Workspace,
    WorkspaceGoal,
    WorkspaceGoalState,
    WorkspaceRole,
    WorkspaceStatus,
)
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    CreateGoalRequest,
    CreateWorkspaceRequest,
    GoalListResponse,
    GoalResponse,
    MemberListResponse,
    MembershipResponse,
    SettingsResponse,
    SetVisibilityGrantRequest,
    TransferOwnershipChallengeResponse,
    TransferOwnershipRequest,
    UpdateGoalStatusRequest,
    UpdateSettingsRequest,
    UpdateWorkspaceRequest,
    VisibilityGrantResponse,
    WorkspaceDeletedResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceSummaryResponse,
)
from platform.workspaces.state_machine import validate_goal_transition
from platform.ws_hub.subscription import ChannelType
from typing import Any
from uuid import UUID, uuid4


class WorkspacesService:
    def __init__(
        self,
        repo: WorkspacesRepository,
        settings: PlatformSettings,
        kafka_producer: EventProducer | None,
        *,
        accounts_service: Any | None = None,
        cost_governance_service: Any | None = None,
        incident_response_service: Any | None = None,
        saved_view_service: Any | None = None,
    ) -> None:
        self.repo = repo
        self.platform_settings = settings
        self.settings = settings.workspaces
        self.kafka_producer = kafka_producer
        self.accounts_service = accounts_service
        self.cost_governance_service = cost_governance_service
        self.incident_response_service = incident_response_service
        self.saved_view_service = saved_view_service
        self.two_person_approval_service: Any | None = None

    async def create_workspace(
        self,
        user_id: UUID,
        request: CreateWorkspaceRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> WorkspaceResponse:
        limit = await self._get_workspace_limit(user_id)
        owned_count = await self.repo.count_owned_workspaces(user_id)
        if limit > 0 and owned_count >= limit:
            raise WorkspaceLimitError(limit)

        if await self.repo.get_workspace_by_name_for_owner(user_id, request.name) is not None:
            raise WorkspaceNameConflictError(request.name)

        workspace = await self.repo.create_workspace(
            name=request.name,
            description=request.description,
            owner_id=user_id,
            is_default=False,
        )
        await self.repo.add_member(workspace.id, user_id, WorkspaceRole.owner)
        await self.repo.update_settings(workspace.id)
        await publish_workspace_created(
            self.kafka_producer,
            self._workspace_payload(workspace),
            self._correlation(correlation_id, workspace_id=workspace.id),
        )
        return self._workspace_response(workspace)

    async def create_default_workspace(
        self,
        user_id: UUID,
        display_name: str,
        *,
        correlation_ctx: CorrelationContext | None = None,
    ) -> WorkspaceResponse:
        existing = await self.repo.get_default_workspace_for_owner(user_id)
        if existing is not None:
            return self._workspace_response(existing)

        name = self.settings.default_name_template.format(display_name=display_name)
        workspace = await self.repo.create_workspace(
            name=name,
            description=None,
            owner_id=user_id,
            is_default=True,
        )
        await self.repo.add_member(workspace.id, user_id, WorkspaceRole.owner)
        await self.repo.update_settings(workspace.id)
        correlation = (
            correlation_ctx.model_copy(update={"workspace_id": workspace.id})
            if correlation_ctx is not None
            else self._correlation(uuid4(), workspace_id=workspace.id)
        )
        await publish_workspace_created(
            self.kafka_producer,
            self._workspace_payload(workspace),
            correlation,
        )
        return self._workspace_response(workspace)

    async def get_workspace(self, workspace_id: UUID, user_id: UUID) -> WorkspaceResponse:
        workspace = await self.repo.get_workspace_by_id(workspace_id, user_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        return self._workspace_response(workspace)

    async def list_workspaces(
        self,
        user_id: UUID,
        page: int,
        page_size: int,
        status_filter: WorkspaceStatus | None,
    ) -> WorkspaceListResponse:
        items, total = await self.repo.list_workspaces_for_user(
            user_id, page, page_size, status_filter
        )
        return WorkspaceListResponse(
            items=[self._workspace_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def update_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        request: UpdateWorkspaceRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> WorkspaceResponse:
        workspace, membership = await self._require_membership(
            workspace_id, user_id, WorkspaceRole.admin
        )
        update_fields: dict[str, Any] = {}
        if "name" in request.model_fields_set and request.name is not None:
            existing = await self.repo.get_workspace_by_name_for_owner(
                workspace.owner_id,
                request.name,
                exclude_workspace_id=workspace.id,
            )
            if existing is not None:
                raise WorkspaceNameConflictError(request.name)
            update_fields["name"] = request.name
        if "description" in request.model_fields_set:
            update_fields["description"] = request.description
        if not update_fields:
            return self._workspace_response(workspace)
        updated = await self.repo.update_workspace(
            workspace, **update_fields, updated_by=membership.user_id
        )
        await publish_workspace_updated(
            self.kafka_producer,
            self._workspace_payload(updated),
            self._correlation(correlation_id, workspace_id=updated.id),
        )
        return self._workspace_response(updated)

    async def archive_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> WorkspaceResponse:
        workspace, membership = await self._require_membership(
            workspace_id, user_id, WorkspaceRole.owner
        )
        if workspace.status.value == "archived":
            raise WorkspaceStateConflictError(
                "WORKSPACE_ALREADY_ARCHIVED", "Workspace is already archived"
            )
        archived = await self.repo.archive_workspace(workspace)
        archived.updated_by = membership.user_id
        await publish_workspace_archived(
            self.kafka_producer,
            self._workspace_payload(archived),
            self._correlation(correlation_id, workspace_id=archived.id),
        )
        if self.cost_governance_service is not None:
            await self.cost_governance_service.handle_workspace_archived(archived.id)
        if self.incident_response_service is not None:
            await self.incident_response_service.handle_workspace_archived(archived.id)
        return self._workspace_response(archived)

    async def restore_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> WorkspaceResponse:
        workspace, membership = await self._require_membership(
            workspace_id, user_id, WorkspaceRole.owner
        )
        if workspace.status.value != "archived":
            raise WorkspaceStateConflictError("WORKSPACE_NOT_ARCHIVED", "Workspace is not archived")
        restored = await self.repo.restore_workspace(workspace)
        restored.updated_by = membership.user_id
        await publish_workspace_restored(
            self.kafka_producer,
            self._workspace_payload(restored),
            self._correlation(correlation_id, workspace_id=restored.id),
        )
        return self._workspace_response(restored)

    async def delete_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        allow_platform_admin: bool = False,
        correlation_id: UUID | None = None,
    ) -> WorkspaceDeletedResponse:
        if allow_platform_admin:
            workspace = await self.repo.get_workspace_by_id_any(workspace_id)
            if workspace is None:
                raise WorkspaceNotFoundError()
        else:
            workspace, _ = await self._require_membership(
                workspace_id, user_id, WorkspaceRole.owner
            )
        if workspace.status.value != "archived":
            raise WorkspaceStateConflictError(
                "WORKSPACE_DELETE_REQUIRES_ARCHIVE",
                "Workspace must be archived before deletion",
            )
        deleted = await self.repo.delete_workspace(workspace)
        await publish_workspace_deleted(
            self.kafka_producer,
            self._workspace_payload(deleted),
            self._correlation(correlation_id, workspace_id=deleted.id),
        )
        return WorkspaceDeletedResponse(workspace_id=deleted.id)

    async def add_member(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: AddMemberRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> MembershipResponse:
        workspace, _ = await self._require_membership(
            workspace_id, requester_id, WorkspaceRole.admin
        )
        if not await self.repo.user_exists(request.user_id):
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        if await self.repo.get_membership(workspace.id, request.user_id) is not None:
            raise MemberAlreadyExistsError()
        membership = await self.repo.add_member(workspace.id, request.user_id, request.role)
        await publish_membership_added(
            self.kafka_producer,
            MembershipPayload(
                workspace_id=workspace.id,
                user_id=membership.user_id,
                role=membership.role,
            ),
            self._correlation(correlation_id, workspace_id=workspace.id),
        )
        return self._membership_response(membership)

    async def list_member_ids(self, workspace_id: UUID) -> list[UUID]:
        return await self.repo.list_member_ids(workspace_id)

    async def list_members(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        page: int,
        page_size: int,
    ) -> MemberListResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        items, total = await self.repo.list_members(workspace_id, page, page_size)
        return MemberListResponse(
            items=[self._membership_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def change_member_role(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        target_user_id: UUID,
        request: ChangeMemberRoleRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> MembershipResponse:
        _, _ = await self._require_membership(workspace_id, requester_id, WorkspaceRole.admin)
        membership = await self.repo.get_membership(workspace_id, target_user_id)
        if membership is None:
            raise MemberNotFoundError()
        if membership.role == WorkspaceRole.owner or request.role == WorkspaceRole.owner:
            raise WorkspaceAuthorizationError("Owner role cannot be changed through this endpoint")
        previous_role = membership.role
        updated = await self.repo.change_member_role(membership, request.role)
        await publish_membership_role_changed(
            self.kafka_producer,
            MembershipPayload(
                workspace_id=workspace_id,
                user_id=target_user_id,
                role=updated.role,
                previous_role=previous_role,
            ),
            self._correlation(correlation_id, workspace_id=workspace_id),
        )
        return self._membership_response(updated)

    async def remove_member(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        target_user_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> None:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.admin)
        membership = await self.repo.get_membership(workspace_id, target_user_id)
        if membership is None:
            raise MemberNotFoundError()
        if (
            membership.role == WorkspaceRole.owner
            and await self.repo.count_owners(workspace_id) <= 1
        ):
            raise LastOwnerError()
        await self.repo.remove_member(membership)
        if self.saved_view_service is not None:
            await self.saved_view_service.resolve_orphan_owner(
                workspace_id,
                former_owner_id=target_user_id,
            )
        await publish_membership_removed(
            self.kafka_producer,
            MembershipPayload(
                workspace_id=workspace_id,
                user_id=target_user_id,
                role=membership.role,
            ),
            self._correlation(correlation_id, workspace_id=workspace_id),
        )

    async def create_goal(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: CreateGoalRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> GoalResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.member)
        goal = await self.repo.create_goal(
            workspace_id=workspace_id,
            title=request.title,
            description=request.description,
            created_by=requester_id,
            auto_complete_timeout_seconds=request.auto_complete_timeout_seconds,
        )
        await publish_goal_created(
            self.kafka_producer,
            GoalPayload(
                workspace_id=workspace_id,
                goal_id=goal.id,
                gid=goal.gid,
                title=goal.title,
                created_by=goal.created_by,
                status=goal.status,
            ),
            self._correlation(correlation_id, workspace_id=workspace_id, goal_id=goal.gid),
        )
        return self._goal_response(goal)

    async def get_goal(self, workspace_id: UUID, requester_id: UUID, goal_id: UUID) -> GoalResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        goal = await self.repo.get_goal(workspace_id, goal_id)
        if goal is None:
            raise GoalNotFoundError()
        return self._goal_response(goal)

    async def list_goals(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        page: int,
        page_size: int,
        status_filter: GoalStatus | None,
    ) -> GoalListResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        items, total = await self.repo.list_goals(workspace_id, page, page_size, status_filter)
        return GoalListResponse(
            items=[self._goal_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def update_goal_status(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        goal_id: UUID,
        request: UpdateGoalStatusRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> GoalResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.member)
        goal = await self.repo.get_goal(workspace_id, goal_id)
        if goal is None:
            raise GoalNotFoundError()
        previous_status = goal.status
        await validate_goal_transition(previous_status, request.status)
        updated = await self.repo.update_goal_status(goal, request.status)
        await publish_goal_status_changed(
            self.kafka_producer,
            GoalPayload(
                workspace_id=workspace_id,
                goal_id=goal.id,
                gid=goal.gid,
                previous_status=previous_status,
                status=updated.status,
            ),
            self._correlation(correlation_id, workspace_id=workspace_id, goal_id=goal.gid),
        )
        return self._goal_response(updated)

    async def set_visibility_grant(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: SetVisibilityGrantRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> VisibilityGrantResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.admin)
        visibility = await self.repo.set_visibility_grant(
            workspace_id=workspace_id,
            visibility_agents=request.visibility_agents,
            visibility_tools=request.visibility_tools,
        )
        await publish_visibility_grant_updated(
            self.kafka_producer,
            VisibilityGrantPayload(
                workspace_id=workspace_id,
                visibility_agents=visibility.visibility_agents,
                visibility_tools=visibility.visibility_tools,
            ),
            self._correlation(correlation_id, workspace_id=workspace_id),
        )
        return self._visibility_response(visibility)

    async def get_visibility_grant(
        self,
        workspace_id: UUID,
        requester_id: UUID,
    ) -> VisibilityGrantResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        visibility = await self.repo.get_visibility_grant(workspace_id)
        if visibility is None:
            raise VisibilityGrantNotFoundError()
        return self._visibility_response(visibility)

    async def delete_visibility_grant(self, workspace_id: UUID, requester_id: UUID) -> None:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.admin)
        await self.repo.delete_visibility_grant(workspace_id)

    async def get_workspace_visibility_grant(
        self,
        workspace_id: UUID,
    ) -> VisibilityGrantResponse | None:
        visibility = await self.repo.get_visibility_grant(workspace_id)
        if visibility is None:
            return None
        return self._visibility_response(visibility)

    async def get_visibility_config(
        self,
        workspace_id: UUID,
    ) -> VisibilityGrantResponse | None:
        return await self.get_workspace_visibility_grant(workspace_id)

    async def get_settings(self, workspace_id: UUID, requester_id: UUID) -> SettingsResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        settings = await self.repo.get_settings(workspace_id)
        if settings is None:
            settings = await self.repo.update_settings(workspace_id)
        return self._settings_response(settings)

    async def update_settings(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: UpdateSettingsRequest,
    ) -> SettingsResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.admin)
        fields: dict[str, list[str] | list[UUID] | dict[str, Any]] = {}
        if (
            "subscribed_agents" in request.model_fields_set
            and request.subscribed_agents is not None
        ):
            fields["subscribed_agents"] = request.subscribed_agents
        if (
            "subscribed_fleets" in request.model_fields_set
            and request.subscribed_fleets is not None
        ):
            fields["subscribed_fleets"] = request.subscribed_fleets
        if (
            "subscribed_policies" in request.model_fields_set
            and request.subscribed_policies is not None
        ):
            fields["subscribed_policies"] = request.subscribed_policies
        if (
            "subscribed_connectors" in request.model_fields_set
            and request.subscribed_connectors is not None
        ):
            fields["subscribed_connectors"] = request.subscribed_connectors
        if "cost_budget" in request.model_fields_set and request.cost_budget is not None:
            fields["cost_budget"] = request.cost_budget
        if "quota_config" in request.model_fields_set and request.quota_config is not None:
            fields["quota_config"] = request.quota_config
        if "dlp_rules" in request.model_fields_set and request.dlp_rules is not None:
            fields["dlp_rules"] = request.dlp_rules
        if "residency_config" in request.model_fields_set and request.residency_config is not None:
            fields["residency_config"] = request.residency_config
        settings = await self.repo.update_settings(workspace_id, **fields)
        return self._settings_response(settings)

    async def get_summary(self, workspace_id: UUID, requester_id: UUID) -> WorkspaceSummaryResponse:
        await self._require_membership(workspace_id, requester_id, WorkspaceRole.viewer)
        settings = await self.repo.get_settings(workspace_id)
        if settings is None:
            settings = await self.repo.update_settings(workspace_id)
        active_goals = await self.repo.count_active_goals(workspace_id)
        executions_in_flight = await self.repo.count_executions_in_flight(workspace_id)
        subscribed_agents = list(settings.subscribed_agents)
        agent_count = len(subscribed_agents)
        budget = dict(getattr(settings, "cost_budget", {}) or {})
        quotas = dict(getattr(settings, "quota_config", {}) or {})
        dlp_rules = dict(getattr(settings, "dlp_rules", {}) or {})
        return WorkspaceSummaryResponse(
            workspace_id=workspace_id,
            active_goals=active_goals,
            executions_in_flight=executions_in_flight,
            agent_count=agent_count,
            budget=budget,
            quotas=quotas,
            tags={"count": 0, "items": []},
            dlp_violations=0,
            recent_activity=[],
            cards={
                "active_goals": {
                    "label": "Active goals",
                    "value": active_goals,
                    "metadata": {},
                },
                "executions_in_flight": {
                    "label": "Executions in flight",
                    "value": executions_in_flight,
                    "metadata": {},
                },
                "agent_count": {
                    "label": "Agents",
                    "value": agent_count,
                    "metadata": {"subscribed_agents": subscribed_agents},
                },
                "budget": {"label": "Budget", "value": budget.get("amount", 0), "metadata": budget},
                "quotas": {"label": "Quotas", "value": len(quotas), "metadata": quotas},
                "tags": {"label": "Tags", "value": 0, "metadata": {}},
                "dlp": {"label": "DLP violations", "value": 0, "metadata": dlp_rules},
            },
        )

    async def initiate_ownership_transfer(
        self,
        workspace_id: UUID,
        requester_id: UUID,
        request: TransferOwnershipRequest,
    ) -> TransferOwnershipChallengeResponse:
        workspace, _ = await self._require_membership(
            workspace_id, requester_id, WorkspaceRole.owner
        )
        if not await self.repo.user_exists(request.new_owner_id):
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        if request.new_owner_id == workspace.owner_id:
            raise WorkspaceAuthorizationError("New owner is already the workspace owner")
        if self.two_person_approval_service is None:
            raise WorkspaceStateConflictError(
                "TWO_PERSON_APPROVAL_UNAVAILABLE",
                "Two-person approval service is not configured",
            )
        challenge = await self.two_person_approval_service.create_challenge(
            initiator_id=requester_id,
            action_type="workspace_transfer_ownership",
            action_payload={
                "workspace_id": str(workspace_id),
                "new_owner_id": str(request.new_owner_id),
            },
        )
        return TransferOwnershipChallengeResponse(
            challenge_id=challenge.id,
            action_type=challenge.action_type,
            status=challenge.status,
            expires_at=challenge.expires_at,
        )

    async def commit_ownership_transfer_payload(
        self,
        payload: dict[str, Any],
        requester_id: UUID,
    ) -> WorkspaceResponse:
        workspace_id = UUID(str(payload["workspace_id"]))
        new_owner_id = UUID(str(payload["new_owner_id"]))
        workspace, previous_owner_membership = await self._require_membership(
            workspace_id, requester_id, WorkspaceRole.owner
        )
        if workspace.owner_id != requester_id:
            raise WorkspaceAuthorizationError("Only the current owner can commit transfer")
        if not await self.repo.user_exists(new_owner_id):
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        new_owner_membership = await self.repo.get_membership(workspace_id, new_owner_id)
        updated = await self.repo.transfer_ownership(
            workspace,
            previous_owner_membership,
            new_owner_membership,
            new_owner_id,
        )
        return self._workspace_response(updated)

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        return await self.repo.get_user_workspace_ids(user_id)

    async def get_workspace_id_for_resource(
        self,
        channel: ChannelType | str,
        resource_id: UUID,
    ) -> UUID | None:
        resolved_channel = ChannelType(str(channel))

        if resolved_channel is ChannelType.WORKSPACE:
            workspace = await self.repo.get_workspace_by_id_any(resource_id)
            return workspace.id if workspace is not None else None

        if resolved_channel in {
            ChannelType.EXECUTION,
            ChannelType.REASONING,
            ChannelType.CORRECTION,
        }:
            return await self.repo.get_workspace_id_for_execution(resource_id)

        if resolved_channel is ChannelType.INTERACTION:
            return await self.repo.get_workspace_id_for_interaction(resource_id)

        if resolved_channel is ChannelType.CONVERSATION:
            return await self.repo.get_workspace_id_for_conversation(resource_id)

        if resolved_channel in {
            ChannelType.SIMULATION,
            ChannelType.TESTING,
        }:
            goal = await self.repo.get_goal_by_gid(resource_id)
            return goal.workspace_id if goal is not None else None

        if resolved_channel is ChannelType.FLEET:
            return await self.repo.get_workspace_id_for_fleet(resource_id)

        return None

    async def _get_workspace_limit(self, user_id: UUID) -> int:
        if self.accounts_service is None:
            return self.settings.default_limit
        getter = getattr(self.accounts_service, "get_user_workspace_limit", None)
        if getter is None:
            return self.settings.default_limit
        return int(await getter(user_id))

    async def _require_membership(
        self,
        workspace_id: UUID,
        user_id: UUID,
        minimum_role: WorkspaceRole,
    ) -> tuple[Workspace, Membership]:
        workspace = await self.repo.get_workspace_by_id(workspace_id, user_id)
        membership = await self.repo.get_membership(workspace_id, user_id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError()
        if not self._role_allows(membership.role, minimum_role):
            raise WorkspaceAuthorizationError()
        return workspace, membership

    @staticmethod
    def _role_allows(current: WorkspaceRole, minimum: WorkspaceRole) -> bool:
        rank = {
            WorkspaceRole.viewer: 0,
            WorkspaceRole.member: 1,
            WorkspaceRole.admin: 2,
            WorkspaceRole.owner: 3,
        }
        return rank[current] >= rank[minimum]

    @staticmethod
    def _workspace_response(workspace: Workspace) -> WorkspaceResponse:
        return WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            description=workspace.description,
            status=workspace.status,
            owner_id=workspace.owner_id,
            is_default=workspace.is_default,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

    @staticmethod
    def _membership_response(membership: Membership) -> MembershipResponse:
        return MembershipResponse(
            id=membership.id,
            workspace_id=membership.workspace_id,
            user_id=membership.user_id,
            role=membership.role,
            created_at=membership.created_at,
        )

    @staticmethod
    def _goal_response(goal: WorkspaceGoal) -> GoalResponse:
        return GoalResponse(
            id=goal.id,
            workspace_id=goal.workspace_id,
            gid=goal.gid,
            title=goal.title,
            description=goal.description,
            status=goal.status,
            state=getattr(goal, "state", WorkspaceGoalState.ready),
            auto_complete_timeout_seconds=getattr(goal, "auto_complete_timeout_seconds", None),
            created_by=goal.created_by,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )

    @staticmethod
    def _settings_response(settings: Any) -> SettingsResponse:
        return SettingsResponse(
            workspace_id=settings.workspace_id,
            subscribed_agents=list(settings.subscribed_agents),
            subscribed_fleets=list(settings.subscribed_fleets),
            subscribed_policies=list(settings.subscribed_policies),
            subscribed_connectors=list(settings.subscribed_connectors),
            cost_budget=dict(getattr(settings, "cost_budget", {}) or {}),
            quota_config=dict(getattr(settings, "quota_config", {}) or {}),
            dlp_rules=dict(getattr(settings, "dlp_rules", {}) or {}),
            residency_config=dict(getattr(settings, "residency_config", {}) or {}),
            updated_at=settings.updated_at,
        )

    @staticmethod
    def _visibility_response(visibility: Any) -> VisibilityGrantResponse:
        return VisibilityGrantResponse(
            workspace_id=visibility.workspace_id,
            visibility_agents=list(visibility.visibility_agents),
            visibility_tools=list(visibility.visibility_tools),
            updated_at=visibility.updated_at,
        )

    @staticmethod
    def _workspace_payload(workspace: Workspace) -> WorkspacePayload:
        return WorkspacePayload(
            workspace_id=workspace.id,
            owner_id=workspace.owner_id,
            name=workspace.name,
            status=workspace.status,
            is_default=workspace.is_default,
        )

    @staticmethod
    def _correlation(
        correlation_id: UUID | None,
        *,
        workspace_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=correlation_id or uuid4(),
            workspace_id=workspace_id,
            goal_id=goal_id,
        )
