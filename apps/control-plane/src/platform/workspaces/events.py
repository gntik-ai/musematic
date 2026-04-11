from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.workspaces.models import GoalStatus, WorkspaceRole, WorkspaceStatus
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class WorkspacesEventType(StrEnum):
    workspace_created = "workspaces.workspace.created"
    workspace_updated = "workspaces.workspace.updated"
    workspace_archived = "workspaces.workspace.archived"
    workspace_restored = "workspaces.workspace.restored"
    workspace_deleted = "workspaces.workspace.deleted"
    membership_added = "workspaces.membership.added"
    membership_role_changed = "workspaces.membership.role_changed"
    membership_removed = "workspaces.membership.removed"
    goal_created = "workspaces.goal.created"
    goal_status_changed = "workspaces.goal.status_changed"
    visibility_grant_updated = "workspaces.visibility_grant.updated"


class WorkspacePayload(BaseModel):
    workspace_id: UUID
    owner_id: UUID
    name: str
    status: WorkspaceStatus
    is_default: bool = False


class MembershipPayload(BaseModel):
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole | None = None
    previous_role: WorkspaceRole | None = None


class GoalPayload(BaseModel):
    workspace_id: UUID
    goal_id: UUID
    gid: UUID
    title: str | None = None
    created_by: UUID | None = None
    previous_status: GoalStatus | None = None
    status: GoalStatus | None = None


class VisibilityGrantPayload(BaseModel):
    workspace_id: UUID
    visibility_agents: list[str]
    visibility_tools: list[str]


WORKSPACES_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    WorkspacesEventType.workspace_created.value: WorkspacePayload,
    WorkspacesEventType.workspace_updated.value: WorkspacePayload,
    WorkspacesEventType.workspace_archived.value: WorkspacePayload,
    WorkspacesEventType.workspace_restored.value: WorkspacePayload,
    WorkspacesEventType.workspace_deleted.value: WorkspacePayload,
    WorkspacesEventType.membership_added.value: MembershipPayload,
    WorkspacesEventType.membership_role_changed.value: MembershipPayload,
    WorkspacesEventType.membership_removed.value: MembershipPayload,
    WorkspacesEventType.goal_created.value: GoalPayload,
    WorkspacesEventType.goal_status_changed.value: GoalPayload,
    WorkspacesEventType.visibility_grant_updated.value: VisibilityGrantPayload,
}


def register_workspaces_event_types() -> None:
    for event_type, schema in WORKSPACES_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_workspaces_event(
    producer: EventProducer | None,
    event_type: WorkspacesEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.workspaces",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, WorkspacesEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = (
        payload_dict.get("workspace_id")
        or payload_dict.get("goal_id")
        or str(correlation_ctx.correlation_id)
    )
    await producer.publish(
        topic="workspaces.events",
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )


async def publish_workspace_created(
    producer: EventProducer | None,
    payload: WorkspacePayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.workspace_created,
        payload,
        correlation_ctx,
    )


async def publish_workspace_updated(
    producer: EventProducer | None,
    payload: WorkspacePayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.workspace_updated,
        payload,
        correlation_ctx,
    )


async def publish_workspace_archived(
    producer: EventProducer | None,
    payload: WorkspacePayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.workspace_archived,
        payload,
        correlation_ctx,
    )


async def publish_workspace_restored(
    producer: EventProducer | None,
    payload: WorkspacePayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.workspace_restored,
        payload,
        correlation_ctx,
    )


async def publish_workspace_deleted(
    producer: EventProducer | None,
    payload: WorkspacePayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.workspace_deleted,
        payload,
        correlation_ctx,
    )


async def publish_membership_added(
    producer: EventProducer | None,
    payload: MembershipPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.membership_added,
        payload,
        correlation_ctx,
    )


async def publish_membership_role_changed(
    producer: EventProducer | None,
    payload: MembershipPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.membership_role_changed,
        payload,
        correlation_ctx,
    )


async def publish_membership_removed(
    producer: EventProducer | None,
    payload: MembershipPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.membership_removed,
        payload,
        correlation_ctx,
    )


async def publish_goal_created(
    producer: EventProducer | None,
    payload: GoalPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.goal_created,
        payload,
        correlation_ctx,
    )


async def publish_goal_status_changed(
    producer: EventProducer | None,
    payload: GoalPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.goal_status_changed,
        payload,
        correlation_ctx,
    )


async def publish_visibility_grant_updated(
    producer: EventProducer | None,
    payload: VisibilityGrantPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_workspaces_event(
        producer,
        WorkspacesEventType.visibility_grant_updated,
        payload,
        correlation_ctx,
    )
