from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.interactions.models import AttentionUrgency, MessageType
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class InteractionsEventType(StrEnum):
    interaction_started = "interaction.started"
    interaction_completed = "interaction.completed"
    interaction_failed = "interaction.failed"
    interaction_canceled = "interaction.canceled"
    message_received = "message.received"
    branch_merged = "branch.merged"
    goal_message_posted = "goal.message.posted"
    goal_status_changed = "goal.status.changed"
    goal_state_changed = "workspace.goal.state_changed"
    attention_requested = "attention.requested"


class InteractionStartedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    goal_id: UUID | None
    created_by: str


class InteractionCompletedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    duration_seconds: float


class InteractionFailedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    error_metadata: dict[str, object]


class InteractionCanceledPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID


class MessageReceivedPayload(BaseModel):
    message_id: UUID
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    sender_identity: str
    message_type: MessageType


class BranchMergedPayload(BaseModel):
    branch_id: UUID
    parent_interaction_id: UUID
    branch_interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    conflict_detected: bool


class GoalMessagePostedPayload(BaseModel):
    message_id: UUID
    goal_id: UUID
    workspace_id: UUID
    participant_identity: str
    interaction_id: UUID | None


class GoalStatusChangedPayload(BaseModel):
    goal_id: UUID
    workspace_id: UUID
    previous_status: str | None
    status: str


class GoalStateChangedPayload(BaseModel):
    goal_id: UUID
    workspace_id: UUID
    previous_state: str
    new_state: str
    automatic: bool
    reason: str | None
    transitioned_at: datetime


class AttentionRequestedPayload(BaseModel):
    request_id: UUID
    workspace_id: UUID
    source_agent_fqn: str
    target_identity: str
    urgency: AttentionUrgency
    related_interaction_id: UUID | None
    related_goal_id: UUID | None


INTERACTIONS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    InteractionsEventType.interaction_started.value: InteractionStartedPayload,
    InteractionsEventType.interaction_completed.value: InteractionCompletedPayload,
    InteractionsEventType.interaction_failed.value: InteractionFailedPayload,
    InteractionsEventType.interaction_canceled.value: InteractionCanceledPayload,
    InteractionsEventType.message_received.value: MessageReceivedPayload,
    InteractionsEventType.branch_merged.value: BranchMergedPayload,
    InteractionsEventType.goal_message_posted.value: GoalMessagePostedPayload,
    InteractionsEventType.goal_status_changed.value: GoalStatusChangedPayload,
    InteractionsEventType.goal_state_changed.value: GoalStateChangedPayload,
    InteractionsEventType.attention_requested.value: AttentionRequestedPayload,
}


def register_interactions_event_types() -> None:
    for event_type, schema in INTERACTIONS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    *,
    producer: EventProducer | None,
    topic: str,
    event_type: InteractionsEventType | str,
    key: str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, InteractionsEventType) else event_type
    await producer.publish(
        topic=topic,
        key=key,
        event_type=event_name,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.interactions",
    )


async def publish_interaction_started(
    producer: EventProducer | None,
    payload: InteractionStartedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.interaction_started,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_interaction_completed(
    producer: EventProducer | None,
    payload: InteractionCompletedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.interaction_completed,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_interaction_failed(
    producer: EventProducer | None,
    payload: InteractionFailedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.interaction_failed,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_interaction_canceled(
    producer: EventProducer | None,
    payload: InteractionCanceledPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.interaction_canceled,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_message_received(
    producer: EventProducer | None,
    payload: MessageReceivedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.message_received,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_branch_merged(
    producer: EventProducer | None,
    payload: BranchMergedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.branch_merged,
        key=str(payload.parent_interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_goal_message_posted(
    producer: EventProducer | None,
    payload: GoalMessagePostedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="workspace.goal",
        event_type=InteractionsEventType.goal_message_posted,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_goal_status_changed(
    producer: EventProducer | None,
    payload: GoalStatusChangedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="workspace.goal",
        event_type=InteractionsEventType.goal_status_changed,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_goal_state_changed(
    producer: EventProducer | None,
    payload: GoalStateChangedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="workspace.goal",
        event_type=InteractionsEventType.goal_state_changed,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_attention_requested(
    producer: EventProducer | None,
    payload: AttentionRequestedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.attention",
        event_type=InteractionsEventType.attention_requested,
        key=payload.target_identity,
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
