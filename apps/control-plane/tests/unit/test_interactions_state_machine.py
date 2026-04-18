from __future__ import annotations

import asyncio
from platform.interactions.exceptions import InvalidStateTransitionError
from platform.interactions.models import InteractionState
from platform.interactions.schemas import (
    ConversationCreate,
    InteractionCreate,
    InteractionTransition,
)
from platform.interactions.state_machine import INTERACTION_TRANSITIONS, validate_transition
from uuid import uuid4

import pytest

from tests.interactions_support import build_service


def test_interactions_state_machine_valid_transitions_are_exhaustive() -> None:
    for key, value in INTERACTION_TRANSITIONS.items():
        current, trigger = key
        assert validate_transition(current, trigger) == value


def test_interactions_state_machine_rejects_invalid_and_terminal_transitions() -> None:
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(InteractionState.initializing, "start")

    for terminal in (
        InteractionState.completed,
        InteractionState.failed,
        InteractionState.canceled,
    ):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(terminal, "resume")


@pytest.mark.asyncio
async def test_interactions_transition_service_emits_lifecycle_events() -> None:
    service, _repo, _workspaces, producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Lifecycle"),
        "user-1",
        uuid4(),
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )

    ready = await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="ready"),
        conversation.workspace_id,
    )
    running = await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="start"),
        conversation.workspace_id,
    )
    completed = await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="complete"),
        conversation.workspace_id,
    )

    second = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )
    await service.transition_interaction(
        second.id,
        InteractionTransition(trigger="ready"),
        conversation.workspace_id,
    )
    await service.transition_interaction(
        second.id,
        InteractionTransition(trigger="start"),
        conversation.workspace_id,
    )
    failed = await service.transition_interaction(
        second.id,
        InteractionTransition(trigger="fail", error_metadata={"reason": "boom"}),
        conversation.workspace_id,
    )

    third = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )
    await service.transition_interaction(
        third.id,
        InteractionTransition(trigger="ready"),
        conversation.workspace_id,
    )
    canceled = await service.transition_interaction(
        third.id,
        InteractionTransition(trigger="cancel"),
        conversation.workspace_id,
    )

    assert ready.state == InteractionState.ready
    assert running.state == InteractionState.running
    assert completed.state == InteractionState.completed
    assert failed.state == InteractionState.failed
    assert canceled.state == InteractionState.canceled
    event_types = [event["event_type"] for event in producer.events]
    assert [
        event_type for event_type in event_types if event_type != "interaction.state_changed"
    ] == [
        "interaction.started",
        "interaction.completed",
        "interaction.started",
        "interaction.failed",
        "interaction.canceled",
    ]
    assert event_types.count("interaction.state_changed") == 8


@pytest.mark.asyncio
async def test_interactions_concurrent_transition_only_one_wins() -> None:
    service, _repo, _workspaces, producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Concurrent"),
        "user-1",
        uuid4(),
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="ready"),
        conversation.workspace_id,
    )

    async def _start() -> InteractionState:
        response = await service.transition_interaction(
            interaction.id,
            InteractionTransition(trigger="start"),
            conversation.workspace_id,
        )
        return response.state

    results = await asyncio.gather(_start(), _start(), return_exceptions=True)

    assert results.count(InteractionState.running) == 1
    errors = [item for item in results if isinstance(item, Exception)]
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidStateTransitionError)
    event_types = [event["event_type"] for event in producer.events]
    assert [
        event_type for event_type in event_types if event_type != "interaction.state_changed"
    ] == ["interaction.started"]
    assert event_types.count("interaction.state_changed") == 2
