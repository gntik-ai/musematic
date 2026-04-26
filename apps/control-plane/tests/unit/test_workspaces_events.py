from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.workspaces.events import (
    GoalPayload,
    MembershipPayload,
    VisibilityGrantPayload,
    WorkspacePayload,
    WorkspacesEventType,
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
    register_workspaces_event_types,
)
from platform.workspaces.models import GoalStatus, WorkspaceRole, WorkspaceStatus
from uuid import uuid4

from tests.auth_support import RecordingProducer


async def _publish_all(producer: RecordingProducer, correlation: CorrelationContext) -> None:
    workspace_id = uuid4()
    goal_id = uuid4()
    goal_gid = uuid4()
    user_id = uuid4()
    payload = WorkspacePayload(
        workspace_id=workspace_id,
        owner_id=user_id,
        name="Finance",
        status=WorkspaceStatus.active,
        is_default=False,
    )
    await publish_workspace_created(producer, payload, correlation)
    await publish_workspace_updated(producer, payload, correlation)
    await publish_workspace_archived(producer, payload, correlation)
    await publish_workspace_restored(producer, payload, correlation)
    await publish_workspace_deleted(producer, payload, correlation)
    await publish_membership_added(
        producer,
        MembershipPayload(
            workspace_id=workspace_id,
            user_id=user_id,
            role=WorkspaceRole.member,
        ),
        correlation,
    )
    await publish_membership_role_changed(
        producer,
        MembershipPayload(
            workspace_id=workspace_id,
            user_id=user_id,
            role=WorkspaceRole.admin,
            previous_role=WorkspaceRole.member,
        ),
        correlation,
    )
    await publish_membership_removed(
        producer,
        MembershipPayload(
            workspace_id=workspace_id,
            user_id=user_id,
            role=WorkspaceRole.admin,
        ),
        correlation,
    )
    await publish_goal_created(
        producer,
        GoalPayload(
            workspace_id=workspace_id,
            goal_id=goal_id,
            gid=goal_gid,
            title="Goal",
            created_by=user_id,
            status=GoalStatus.open,
        ),
        correlation,
    )
    await publish_goal_status_changed(
        producer,
        GoalPayload(
            workspace_id=workspace_id,
            goal_id=goal_id,
            gid=goal_gid,
            previous_status=GoalStatus.open,
            status=GoalStatus.in_progress,
        ),
        correlation,
    )
    await publish_visibility_grant_updated(
        producer,
        VisibilityGrantPayload(
            workspace_id=workspace_id,
            visibility_agents=["finance:*"],
            visibility_tools=["tools:*"],
        ),
        correlation,
    )


async def test_workspaces_event_publishers_emit_expected_topics() -> None:
    register_workspaces_event_types()
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())

    await _publish_all(producer, correlation)

    assert {event["event_type"] for event in producer.events} == {
        item.value for item in WorkspacesEventType
    }
    assert {event["topic"] for event in producer.events} == {"workspaces.events"}

    await publish_workspace_created(
        None,
        WorkspacePayload(
            workspace_id=uuid4(),
            owner_id=uuid4(),
            name="No producer",
            status=WorkspaceStatus.active,
            is_default=False,
        ),
        correlation,
    )
