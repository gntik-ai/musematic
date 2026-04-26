from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import NotFoundError
from platform.workspaces.exceptions import (
    GoalNotFoundError,
    InvalidGoalTransitionError,
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
from platform.workspaces.models import GoalStatus, WorkspaceRole, WorkspaceStatus
from platform.workspaces.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    CreateGoalRequest,
    CreateWorkspaceRequest,
    SetVisibilityGrantRequest,
    UpdateGoalStatusRequest,
    UpdateSettingsRequest,
    UpdateWorkspaceRequest,
)
from platform.workspaces.service import WorkspacesService
from platform.ws_hub.subscription import ChannelType
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.workspaces_support import (
    AccountsServiceStub,
    WorkspacesRepoStub,
    build_goal,
    build_membership,
    build_recording_producer,
    build_settings,
    build_visibility,
    build_workspace,
)


def _settings() -> PlatformSettings:
    return PlatformSettings()


class CostGovernanceWorkspaceStub:
    def __init__(self) -> None:
        self.archived: list[object] = []

    async def handle_workspace_archived(self, workspace_id: object) -> None:
        self.archived.append(workspace_id)


def _service(
    repo: WorkspacesRepoStub,
    *,
    limit: int = 0,
    producer: RecordingProducer | None = None,
) -> tuple[WorkspacesService, AccountsServiceStub, RecordingProducer]:
    accounts_service = AccountsServiceStub(limit=limit)
    resolved_producer = producer or build_recording_producer()
    return (
        WorkspacesService(
            repo=repo,
            settings=_settings(),
            kafka_producer=resolved_producer,
            accounts_service=accounts_service,
        ),
        accounts_service,
        resolved_producer,
    )


@pytest.mark.asyncio
async def test_create_workspace_enforces_limit_and_name_conflict() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    existing = build_workspace(owner_id=owner_id, name="Existing")
    repo.workspaces[existing.id] = existing
    repo.memberships[(existing.id, owner_id)] = build_membership(
        workspace_id=existing.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    service, accounts_service, _producer = _service(repo, limit=1)

    with pytest.raises(WorkspaceLimitError):
        await service.create_workspace(owner_id, CreateWorkspaceRequest(name="Another"))

    accounts_service.limit = 0
    with pytest.raises(WorkspaceNameConflictError):
        await service.create_workspace(owner_id, CreateWorkspaceRequest(name="Existing"))


@pytest.mark.asyncio
async def test_create_get_list_update_archive_restore_and_delete_workspace() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    service, _accounts_service, producer = _service(repo)
    cost_governance = CostGovernanceWorkspaceStub()
    service.cost_governance_service = cost_governance

    created = await service.create_workspace(
        owner_id,
        CreateWorkspaceRequest(name="Finance", description="Planning"),
    )
    listed = await service.list_workspaces(owner_id, 1, 20, None)
    fetched = await service.get_workspace(created.id, owner_id)
    updated = await service.update_workspace(
        created.id,
        owner_id,
        UpdateWorkspaceRequest(name="Finance Ops"),
    )
    archived = await service.archive_workspace(created.id, owner_id)
    restored = await service.restore_workspace(created.id, owner_id)
    rearchived = await service.archive_workspace(created.id, owner_id)
    deleted = await service.delete_workspace(
        created.id,
        owner_id,
        allow_platform_admin=False,
    )

    assert created.name == "Finance"
    assert listed.total == 1
    assert fetched.id == created.id
    assert updated.name == "Finance Ops"
    assert archived.status == WorkspaceStatus.archived
    assert restored.status == WorkspaceStatus.active
    assert rearchived.status == WorkspaceStatus.archived
    assert deleted.workspace_id == created.id
    assert cost_governance.archived == [created.id, created.id]
    assert [event["event_type"] for event in producer.events][:6] == [
        "workspaces.workspace.created",
        "workspaces.workspace.updated",
        "workspaces.workspace.archived",
        "workspaces.workspace.restored",
        "workspaces.workspace.archived",
        "workspaces.workspace.deleted",
    ]


@pytest.mark.asyncio
async def test_create_default_workspace_is_idempotent_and_uses_correlation_context() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    service, _accounts_service, producer = _service(repo)

    first = await service.create_default_workspace(
        owner_id,
        "Ada",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    second = await service.create_default_workspace(owner_id, "Ada")

    assert first.is_default is True
    assert second.id == first.id
    assert len(producer.events) == 1


@pytest.mark.asyncio
async def test_workspace_get_update_and_delete_raise_expected_errors() -> None:
    owner_id = uuid4()
    other_user = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    service, _accounts_service, _producer = _service(repo)

    with pytest.raises(WorkspaceNotFoundError):
        await service.get_workspace(workspace.id, other_user)

    repo.memberships[(workspace.id, other_user)] = build_membership(
        workspace_id=workspace.id,
        user_id=other_user,
        role=WorkspaceRole.viewer,
    )
    with pytest.raises(WorkspaceAuthorizationError):
        await service.update_workspace(
            workspace.id,
            other_user,
            UpdateWorkspaceRequest(name="Forbidden"),
        )

    with pytest.raises(WorkspaceStateConflictError):
        await service.delete_workspace(workspace.id, owner_id)


@pytest.mark.asyncio
async def test_workspace_update_and_lifecycle_conflicts_are_reported() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id, name="Finance")
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    conflicting = build_workspace(owner_id=owner_id, name="Ops")
    repo.workspaces[conflicting.id] = conflicting
    service, _accounts_service, _producer = _service(repo)

    empty_update = UpdateWorkspaceRequest.model_construct()
    empty_update.__pydantic_fields_set__ = set()

    unchanged = await service.update_workspace(
        workspace.id,
        owner_id,
        empty_update,
    )
    described = await service.update_workspace(
        workspace.id,
        owner_id,
        UpdateWorkspaceRequest(description="Only description"),
    )

    with pytest.raises(WorkspaceNameConflictError):
        await service.update_workspace(
            workspace.id,
            owner_id,
            UpdateWorkspaceRequest(name="Ops"),
        )

    archived = await service.archive_workspace(workspace.id, owner_id)
    with pytest.raises(WorkspaceStateConflictError):
        await service.archive_workspace(workspace.id, owner_id)

    restored = await service.restore_workspace(workspace.id, owner_id)
    with pytest.raises(WorkspaceStateConflictError):
        await service.restore_workspace(workspace.id, owner_id)

    archived_again = await service.archive_workspace(workspace.id, owner_id)
    deleted = await service.delete_workspace(
        workspace.id,
        uuid4(),
        allow_platform_admin=True,
    )

    with pytest.raises(WorkspaceNotFoundError):
        await service.delete_workspace(uuid4(), owner_id, allow_platform_admin=True)

    assert unchanged.id == workspace.id
    assert described.description == "Only description"
    assert archived.status == WorkspaceStatus.archived
    assert restored.status == WorkspaceStatus.active
    assert archived_again.status == WorkspaceStatus.archived
    assert deleted.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_membership_flows_and_last_owner_guard() -> None:
    owner_id = uuid4()
    member_id = uuid4()
    repo = WorkspacesRepoStub()
    repo.existing_users.update({owner_id, member_id})
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    service, _accounts_service, producer = _service(repo)

    added = await service.add_member(
        workspace.id,
        owner_id,
        AddMemberRequest(user_id=member_id, role=WorkspaceRole.member),
    )
    members = await service.list_members(workspace.id, owner_id, 1, 50)
    member_ids = await service.list_member_ids(workspace.id)
    changed = await service.change_member_role(
        workspace.id,
        owner_id,
        member_id,
        ChangeMemberRoleRequest(role=WorkspaceRole.admin),
    )
    await service.remove_member(workspace.id, owner_id, member_id)

    assert added.user_id == member_id
    assert members.total == 2
    assert set(member_ids) == {owner_id, member_id}
    assert changed.role == WorkspaceRole.admin
    assert [event["event_type"] for event in producer.events][-3:] == [
        "workspaces.membership.added",
        "workspaces.membership.role_changed",
        "workspaces.membership.removed",
    ]

    with pytest.raises(MemberAlreadyExistsError):
        await service.add_member(
            workspace.id,
            owner_id,
            AddMemberRequest(user_id=owner_id, role=WorkspaceRole.admin),
        )

    with pytest.raises(LastOwnerError):
        await service.remove_member(workspace.id, owner_id, owner_id)


@pytest.mark.asyncio
async def test_membership_error_paths_are_reported() -> None:
    owner_id = uuid4()
    member_id = uuid4()
    repo = WorkspacesRepoStub()
    repo.existing_users.add(owner_id)
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.memberships[(workspace.id, member_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=member_id,
        role=WorkspaceRole.member,
    )
    service, _accounts_service, _producer = _service(repo)

    with pytest.raises(NotFoundError, match="User not found"):
        await service.add_member(
            workspace.id,
            owner_id,
            AddMemberRequest(user_id=uuid4(), role=WorkspaceRole.member),
        )

    with pytest.raises(MemberNotFoundError):
        await service.change_member_role(
            workspace.id,
            owner_id,
            uuid4(),
            ChangeMemberRoleRequest(role=WorkspaceRole.admin),
        )

    repo.memberships[(workspace.id, member_id)].role = WorkspaceRole.owner
    with pytest.raises(WorkspaceAuthorizationError):
        await service.change_member_role(
            workspace.id,
            owner_id,
            member_id,
            ChangeMemberRoleRequest(role=WorkspaceRole.admin),
        )

    repo.memberships.pop((workspace.id, member_id))
    with pytest.raises(MemberNotFoundError):
        await service.remove_member(workspace.id, owner_id, member_id)


@pytest.mark.asyncio
async def test_goal_visibility_and_settings_flows() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.settings_by_workspace[workspace.id] = build_settings(workspace_id=workspace.id)
    service, _accounts_service, producer = _service(repo)

    goal = await service.create_goal(
        workspace.id,
        owner_id,
        CreateGoalRequest(title="Goal A", description="Ship it"),
    )
    listed = await service.list_goals(workspace.id, owner_id, 1, 20, None)
    updated_goal = await service.update_goal_status(
        workspace.id,
        owner_id,
        goal.id,
        UpdateGoalStatusRequest(status=GoalStatus.in_progress),
    )
    visibility = await service.set_visibility_grant(
        workspace.id,
        owner_id,
        SetVisibilityGrantRequest(
            visibility_agents=["finance:*"],
            visibility_tools=["tools:csv-reader"],
        ),
    )
    fetched_visibility = await service.get_visibility_grant(workspace.id, owner_id)
    internal_visibility = await service.get_visibility_config(workspace.id)
    existing_settings = await service.get_settings(workspace.id, owner_id)
    settings = await service.update_settings(
        workspace.id,
        owner_id,
        UpdateSettingsRequest(subscribed_agents=["planner:*"]),
    )
    workspace_ids = await service.get_user_workspace_ids(owner_id)

    assert goal.title == "Goal A"
    assert listed.total == 1
    assert updated_goal.status == GoalStatus.in_progress
    assert visibility.visibility_agents == ["finance:*"]
    assert fetched_visibility.visibility_tools == ["tools:csv-reader"]
    assert internal_visibility is not None
    assert existing_settings.workspace_id == workspace.id
    assert settings.subscribed_agents == ["planner:*"]
    assert workspace_ids == [workspace.id]
    assert {event["event_type"] for event in producer.events} >= {
        "workspaces.goal.created",
        "workspaces.goal.status_changed",
        "workspaces.visibility_grant.updated",
    }


@pytest.mark.asyncio
async def test_goal_visibility_settings_and_limit_fallback_paths() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    goal = build_goal(workspace_id=workspace.id, created_by=owner_id)
    repo.goals[(workspace.id, goal.id)] = goal
    service, _accounts_service, _producer = _service(repo)

    fetched_goal = await service.get_goal(workspace.id, owner_id, goal.id)
    await service.delete_visibility_grant(workspace.id, owner_id)
    fetched_settings = await service.get_settings(workspace.id, owner_id)
    updated_settings = await service.update_settings(
        workspace.id,
        owner_id,
        UpdateSettingsRequest(
            subscribed_fleets=[uuid4()],
            subscribed_policies=[uuid4()],
            subscribed_connectors=[uuid4()],
            cost_budget={"monthly_cents": 1000},
        ),
    )
    default_only_service = WorkspacesService(
        repo=repo,
        settings=_settings(),
        kafka_producer=None,
        accounts_service=None,
    )
    no_getter_service = WorkspacesService(
        repo=repo,
        settings=_settings(),
        kafka_producer=None,
        accounts_service=object(),
    )

    assert fetched_goal.id == goal.id
    assert fetched_settings.workspace_id == workspace.id
    assert updated_settings.cost_budget == {"monthly_cents": 1000}
    assert len(updated_settings.subscribed_fleets) == 1
    assert len(updated_settings.subscribed_policies) == 1
    assert len(updated_settings.subscribed_connectors) == 1
    assert (
        await default_only_service._get_workspace_limit(owner_id)
        == _settings().workspaces.default_limit
    )
    assert (
        await no_getter_service._get_workspace_limit(owner_id)
        == _settings().workspaces.default_limit
    )

    with pytest.raises(WorkspaceNotFoundError):
        await service._require_membership(uuid4(), owner_id, WorkspaceRole.viewer)


@pytest.mark.asyncio
async def test_goal_and_visibility_errors() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    service, _accounts_service, _producer = _service(repo)

    with pytest.raises(GoalNotFoundError):
        await service.get_goal(workspace.id, owner_id, uuid4())

    completed_goal = build_goal(
        workspace_id=workspace.id,
        created_by=owner_id,
        status=GoalStatus.completed,
    )
    repo.goals[(workspace.id, completed_goal.id)] = completed_goal
    with pytest.raises(InvalidGoalTransitionError):
        await service.update_goal_status(
            workspace.id,
            owner_id,
            completed_goal.id,
            UpdateGoalStatusRequest(status=GoalStatus.in_progress),
        )

    with pytest.raises(VisibilityGrantNotFoundError):
        await service.get_visibility_grant(workspace.id, owner_id)

    with pytest.raises(GoalNotFoundError):
        await service.update_goal_status(
            workspace.id,
            owner_id,
            uuid4(),
            UpdateGoalStatusRequest(status=GoalStatus.in_progress),
        )


@pytest.mark.asyncio
async def test_internal_visibility_interface_returns_none() -> None:
    owner_id = uuid4()
    repo = WorkspacesRepoStub()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.visibility_by_workspace[workspace.id] = build_visibility(
        workspace_id=workspace.id,
        visibility_agents=["finance:*"],
    )
    service, _accounts_service, _producer = _service(repo)

    assert await service.get_workspace_visibility_grant(workspace.id) is not None
    assert await service.get_visibility_config(workspace.id) is not None
    assert await service.get_workspace_visibility_grant(uuid4()) is None


@pytest.mark.asyncio
async def test_get_workspace_id_for_resource_resolves_execution_backed_channels() -> None:
    repo = WorkspacesRepoStub()
    service, _accounts_service, _producer = _service(repo)
    workspace_id = uuid4()
    workspace = build_workspace(workspace_id=workspace_id)
    execution_id = uuid4()
    interaction_id = uuid4()
    conversation_id = uuid4()
    simulation_goal_gid = uuid4()
    fleet_id = uuid4()
    repo.workspaces[workspace_id] = workspace
    repo.execution_workspaces[execution_id] = workspace_id
    repo.interaction_workspaces[interaction_id] = workspace_id
    repo.conversation_workspaces[conversation_id] = workspace_id
    repo.fleet_workspaces[fleet_id] = workspace_id
    repo.goals[(workspace_id, uuid4())] = build_goal(
        workspace_id=workspace_id,
        gid=simulation_goal_gid,
    )

    for channel in (ChannelType.EXECUTION, ChannelType.REASONING, ChannelType.CORRECTION):
        assert await service.get_workspace_id_for_resource(channel, execution_id) == workspace_id
    assert (
        await service.get_workspace_id_for_resource(ChannelType.WORKSPACE, workspace_id)
        == workspace_id
    )
    assert (
        await service.get_workspace_id_for_resource(ChannelType.INTERACTION, interaction_id)
        == workspace_id
    )
    assert (
        await service.get_workspace_id_for_resource(ChannelType.CONVERSATION, conversation_id)
        == workspace_id
    )
    for channel in (ChannelType.SIMULATION, ChannelType.TESTING):
        assert (
            await service.get_workspace_id_for_resource(channel, simulation_goal_gid)
            == workspace_id
        )
    assert await service.get_workspace_id_for_resource(ChannelType.FLEET, fleet_id) == workspace_id
    assert await service.get_workspace_id_for_resource(ChannelType.WORKSPACE, uuid4()) is None
    assert await service.get_workspace_id_for_resource(ChannelType.ALERTS, uuid4()) is None
