from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.registry import event_registry
from platform.interactions.dependencies import build_interactions_service, get_interactions_service
from platform.interactions.events import (
    AttentionRequestedPayload,
    BranchMergedPayload,
    GoalMessagePostedPayload,
    GoalStatusChangedPayload,
    InteractionCanceledPayload,
    InteractionCompletedPayload,
    InteractionFailedPayload,
    InteractionsEventType,
    InteractionStartedPayload,
    InteractionStateChangedPayload,
    MessageReceivedPayload,
    publish_attention_requested,
    publish_branch_merged,
    publish_goal_message_posted,
    publish_goal_status_changed,
    publish_interaction_canceled,
    publish_interaction_completed,
    publish_interaction_failed,
    publish_interaction_started,
    publish_interaction_state_changed,
    publish_message_received,
    register_interactions_event_types,
)
from platform.interactions.models import AttentionUrgency, MessageType
from platform.interactions.service import InteractionsService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.interactions_support import SessionStub, WorkspacesServiceStub


def test_interactions_register_event_types_and_build_service() -> None:
    register_interactions_event_types()
    assert event_registry.is_registered(InteractionsEventType.interaction_started.value) is True
    assert event_registry.is_registered(InteractionsEventType.goal_message_posted.value) is True
    assert event_registry.is_registered(InteractionsEventType.state_changed.value) is True
    assert event_registry.is_registered(InteractionsEventType.attention_requested.value) is True

    service = build_interactions_service(
        session=SessionStub(),  # type: ignore[arg-type]
        settings=SimpleNamespace(interactions=SimpleNamespace(max_messages_per_conversation=10000)),
        producer=None,
        workspaces_service=WorkspacesServiceStub(),  # type: ignore[arg-type]
        registry_service=None,
    )
    assert isinstance(service, InteractionsService)


@pytest.mark.asyncio
async def test_interactions_publish_helpers_and_get_dependency() -> None:
    producer = RecordingProducer()
    correlation = SimpleNamespace(
        correlation_id=uuid4(),
        workspace_id=uuid4(),
        conversation_id=uuid4(),
        interaction_id=uuid4(),
        goal_id=None,
        execution_id=None,
    )
    workspace_id = uuid4()
    interaction_id = uuid4()
    conversation_id = uuid4()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    interactions=SimpleNamespace(max_messages_per_conversation=10000)
                ),
                clients={"kafka": producer},
            )
        )
    )

    resolved = await get_interactions_service(
        request,
        session=SessionStub(),  # type: ignore[arg-type]
        workspaces_service=WorkspacesServiceStub(),  # type: ignore[arg-type]
        registry_service=None,  # type: ignore[arg-type]
    )

    await publish_interaction_started(
        producer,
        InteractionStartedPayload(
            interaction_id=interaction_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            goal_id=None,
            created_by="user-1",
        ),
        correlation,
    )
    await publish_interaction_completed(
        producer,
        InteractionCompletedPayload(
            interaction_id=interaction_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            duration_seconds=1.0,
        ),
        correlation,
    )
    await publish_interaction_failed(
        producer,
        InteractionFailedPayload(
            interaction_id=interaction_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            error_metadata={"reason": "boom"},
        ),
        correlation,
    )
    await publish_interaction_canceled(
        producer,
        InteractionCanceledPayload(
            interaction_id=interaction_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
        ),
        correlation,
    )
    await publish_interaction_state_changed(
        producer,
        InteractionStateChangedPayload(
            interaction_id=interaction_id,
            workspace_id=workspace_id,
            from_state="running",
            to_state="failed",
            occurred_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_message_received(
        producer,
        MessageReceivedPayload(
            message_id=uuid4(),
            interaction_id=interaction_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            sender_identity="user-1",
            message_type=MessageType.user,
        ),
        correlation,
    )
    await publish_branch_merged(
        producer,
        BranchMergedPayload(
            branch_id=uuid4(),
            parent_interaction_id=interaction_id,
            branch_interaction_id=uuid4(),
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            conflict_detected=False,
        ),
        correlation,
    )
    await publish_goal_message_posted(
        producer,
        GoalMessagePostedPayload(
            message_id=uuid4(),
            goal_id=uuid4(),
            workspace_id=workspace_id,
            participant_identity="user-1",
            interaction_id=interaction_id,
        ),
        correlation,
    )
    await publish_goal_status_changed(
        producer,
        GoalStatusChangedPayload(
            goal_id=uuid4(),
            workspace_id=workspace_id,
            previous_status="open",
            status="completed",
        ),
        correlation,
    )
    await publish_attention_requested(
        producer,
        AttentionRequestedPayload(
            request_id=uuid4(),
            workspace_id=workspace_id,
            source_agent_fqn="ops:agent",
            target_identity="user-1",
            urgency=AttentionUrgency.high,
            related_interaction_id=interaction_id,
            related_goal_id=None,
        ),
        correlation,
    )

    assert isinstance(resolved, InteractionsService)
    assert [event["event_type"] for event in producer.events] == [
        "interaction.started",
        "interaction.completed",
        "interaction.failed",
        "interaction.canceled",
        "interaction.state_changed",
        "message.received",
        "branch.merged",
        "goal.message.posted",
        "goal.status.changed",
        "attention.requested",
    ]
