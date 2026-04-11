from __future__ import annotations

from platform.workspaces.models import GoalStatus, WorkspaceRole, WorkspaceStatus
from platform.workspaces.repository import WorkspacesRepository
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from tests.workspaces_support import (
    build_goal,
    build_membership,
    build_settings,
    build_visibility,
    build_workspace,
)


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ScalarsResult:
    def __init__(self, values) -> None:
        self.values = list(values)

    def scalars(self):
        return self

    def all(self):
        return self.values


def _session(*, execute_results=None, scalar_results=None):
    execute_results = list(execute_results or [])
    scalar_results = list(scalar_results or [])
    session = Mock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_results)
    session.scalar = AsyncMock(side_effect=scalar_results)
    return session


@pytest.mark.asyncio
async def test_workspace_crud_methods_update_state_and_flush() -> None:
    owner_id = uuid4()
    session = _session(scalar_results=[3])
    repo = WorkspacesRepository(session)

    workspace = await repo.create_workspace(
        name="Finance",
        description="Planning",
        owner_id=owner_id,
        is_default=True,
    )
    updated = await repo.update_workspace(workspace, name="Finance Ops", updated_by=owner_id)
    archived = await repo.archive_workspace(workspace)
    archived_status = archived.status
    restored = await repo.restore_workspace(workspace)
    restored_status = restored.status
    restored_deleted_at = restored.deleted_at
    deleted = await repo.delete_workspace(workspace)
    count = await repo.count_owned_workspaces(owner_id)

    assert workspace.owner_id == owner_id
    assert workspace.is_default is True
    assert workspace.status == WorkspaceStatus.deleted
    assert updated.name == "Finance Ops"
    assert updated.updated_by == owner_id
    assert archived_status == WorkspaceStatus.archived
    assert restored_status == WorkspaceStatus.active
    assert restored_deleted_at is None
    assert deleted.deleted_at is not None
    assert count == 3
    assert session.add.call_count == 1
    assert session.flush.await_count == 5


@pytest.mark.asyncio
async def test_workspace_lookup_methods_return_scalar_results() -> None:
    owner_id = uuid4()
    user_id = uuid4()
    workspace = build_workspace(owner_id=owner_id)
    other_workspace = build_workspace(owner_id=owner_id, name="Other")
    session = _session(
        execute_results=[
            _ScalarResult(workspace),
            _ScalarResult(workspace),
            _ScalarResult(other_workspace),
            _ScalarResult(None),
            _ScalarsResult([workspace]),
        ],
        scalar_results=[2],
    )
    repo = WorkspacesRepository(session)

    assert await repo.get_workspace_by_id(workspace.id, user_id) is workspace
    assert await repo.get_workspace_by_id_any(workspace.id) is workspace
    assert await repo.get_workspace_by_name_for_owner(owner_id, "Other") is other_workspace
    assert (
        await repo.get_workspace_by_name_for_owner(
            owner_id,
            "Other",
            exclude_workspace_id=other_workspace.id,
        )
        is None
    )
    items, total = await repo.list_workspaces_for_user(user_id, 1, 10, None)

    assert items == [workspace]
    assert total == 2


@pytest.mark.asyncio
async def test_default_workspace_membership_and_membership_counts() -> None:
    owner_id = uuid4()
    member_id = uuid4()
    workspace = build_workspace(owner_id=owner_id, is_default=True)
    membership = build_membership(
        workspace_id=workspace.id,
        user_id=member_id,
        role=WorkspaceRole.admin,
    )
    session = _session(
        execute_results=[
            _ScalarResult(workspace),
            _ScalarResult(membership),
            _ScalarsResult([membership]),
        ],
        scalar_results=[1, 1, 1, 0],
    )
    repo = WorkspacesRepository(session)

    fetched_default = await repo.get_default_workspace_for_owner(owner_id)
    added = await repo.add_member(workspace.id, member_id, WorkspaceRole.member)
    fetched_membership = await repo.get_membership(workspace.id, member_id)
    listed, total = await repo.list_members(workspace.id, 1, 10)
    changed = await repo.change_member_role(membership, WorkspaceRole.viewer)
    await repo.remove_member(membership)
    owners = await repo.count_owners(workspace.id)
    user_exists = await repo.user_exists(member_id)
    user_missing = await repo.user_exists(uuid4())

    assert fetched_default is workspace
    assert added.workspace_id == workspace.id
    assert fetched_membership is membership
    assert listed == [membership]
    assert total == 1
    assert changed.role == WorkspaceRole.viewer
    assert owners == 1
    assert user_exists is True
    assert user_missing is False
    session.delete.assert_awaited_once_with(membership)


@pytest.mark.asyncio
async def test_goal_methods_return_expected_values() -> None:
    creator_id = uuid4()
    workspace_id = uuid4()
    goal = build_goal(workspace_id=workspace_id, created_by=creator_id)
    completed = build_goal(
        workspace_id=workspace_id,
        created_by=creator_id,
        status=GoalStatus.completed,
    )
    session = _session(
        execute_results=[
            _ScalarResult(goal),
            _ScalarsResult([goal]),
            _ScalarsResult([completed]),
        ],
        scalar_results=[1, 1],
    )
    repo = WorkspacesRepository(session)

    created = await repo.create_goal(
        workspace_id=workspace_id,
        title="Ship V1",
        description="Milestone",
        created_by=creator_id,
    )
    fetched = await repo.get_goal(workspace_id, goal.id)
    listed_all, total_all = await repo.list_goals(workspace_id, 1, 10, None)
    listed_completed, total_completed = await repo.list_goals(
        workspace_id,
        1,
        10,
        GoalStatus.completed,
    )
    updated = await repo.update_goal_status(goal, GoalStatus.in_progress)

    assert created.status == GoalStatus.open
    assert fetched is goal
    assert listed_all == [goal]
    assert total_all == 1
    assert listed_completed == [completed]
    assert total_completed == 1
    assert updated.status == GoalStatus.in_progress


@pytest.mark.asyncio
async def test_visibility_and_settings_methods_support_create_update_and_delete() -> None:
    workspace_id = uuid4()
    existing_visibility = build_visibility(
        workspace_id=workspace_id,
        visibility_agents=["old:*"],
        visibility_tools=["tools:old"],
    )
    existing_settings = build_settings(
        workspace_id=workspace_id,
        subscribed_agents=["old:*"],
    )
    session = _session(
        execute_results=[
            _ScalarResult(existing_visibility),
            _ScalarResult(None),
            _ScalarResult(existing_visibility),
            _ScalarResult(existing_visibility),
            _ScalarResult(None),
            _ScalarResult(existing_settings),
            _ScalarResult(None),
            _ScalarResult(existing_settings),
        ]
    )
    repo = WorkspacesRepository(session)

    fetched_visibility = await repo.get_visibility_grant(workspace_id)
    created_visibility = await repo.set_visibility_grant(
        workspace_id=workspace_id,
        visibility_agents=["finance:*"],
        visibility_tools=["tools:csv-reader"],
    )
    updated_visibility = await repo.set_visibility_grant(
        workspace_id=workspace_id,
        visibility_agents=["sales:*"],
        visibility_tools=["tools:xlsx-reader"],
    )
    deleted_existing = await repo.delete_visibility_grant(workspace_id)
    deleted_missing = await repo.delete_visibility_grant(uuid4())

    fetched_settings = await repo.get_settings(workspace_id)
    created_settings = await repo.update_settings(
        workspace_id,
        subscribed_agents=["planner:*"],
        subscribed_connectors=[uuid4()],
    )
    updated_settings = await repo.update_settings(
        existing_settings.workspace_id,
        subscribed_agents=["ops:*"],
    )

    assert fetched_visibility is existing_visibility
    assert created_visibility.visibility_agents == ["finance:*"]
    assert updated_visibility.visibility_tools == ["tools:xlsx-reader"]
    assert deleted_existing is True
    assert deleted_missing is False
    assert fetched_settings is existing_settings
    assert created_settings.subscribed_agents == ["planner:*"]
    assert len(created_settings.subscribed_connectors) == 1
    assert updated_settings.subscribed_agents == ["ops:*"]


@pytest.mark.asyncio
async def test_get_user_workspace_ids_returns_scalar_values() -> None:
    workspace_ids = [uuid4(), uuid4()]
    session = _session(execute_results=[_ScalarsResult(workspace_ids)])
    repo = WorkspacesRepository(session)

    assert await repo.get_user_workspace_ids(uuid4()) == workspace_ids
