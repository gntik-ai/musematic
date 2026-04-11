from __future__ import annotations

from platform.interactions.exceptions import (
    InteractionNotAcceptingMessagesError,
    MessageNotInInteractionError,
)
from platform.interactions.models import MessageType
from platform.interactions.schemas import (
    ConversationCreate,
    InteractionCreate,
    InteractionTransition,
    MessageCreate,
    MessageInject,
)
from uuid import uuid4

import pytest

from tests.interactions_support import build_service


@pytest.mark.asyncio
async def test_interactions_causal_ordering_accepts_first_message_and_multiple_children() -> None:
    service, _repo, _workspaces, _producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Messages"),
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
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="start"),
        conversation.workspace_id,
    )

    first = await service.send_message(
        interaction.id,
        MessageCreate(content="root"),
        "user-1",
        conversation.workspace_id,
    )
    child_a = await service.send_message(
        interaction.id,
        MessageCreate(content="child-a", parent_message_id=first.id),
        "user-1",
        conversation.workspace_id,
    )
    child_b = await service.send_message(
        interaction.id,
        MessageCreate(content="child-b", parent_message_id=first.id),
        "user-1",
        conversation.workspace_id,
    )

    listed = await service.list_messages(interaction.id, conversation.workspace_id, 1, 20)

    assert first.parent_message_id is None
    assert child_a.parent_message_id == first.id
    assert child_b.parent_message_id == first.id
    assert [item.content for item in listed.items] == ["root", "child-a", "child-b"]
    assert listed.total == 3


@pytest.mark.asyncio
async def test_interactions_causal_ordering_rejects_foreign_parent_and_paused_messages() -> None:
    service, _repo, _workspaces, _producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Validation"),
        "user-1",
        uuid4(),
    )
    one = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )
    two = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )

    for interaction_id in (one.id, two.id):
        await service.transition_interaction(
            interaction_id,
            InteractionTransition(trigger="ready"),
            conversation.workspace_id,
        )
        await service.transition_interaction(
            interaction_id,
            InteractionTransition(trigger="start"),
            conversation.workspace_id,
        )

    foreign = await service.send_message(
        two.id,
        MessageCreate(content="other"),
        "user-1",
        conversation.workspace_id,
    )

    with pytest.raises(MessageNotInInteractionError):
        await service.send_message(
            one.id,
            MessageCreate(content="bad-parent", parent_message_id=foreign.id),
            "user-1",
            conversation.workspace_id,
        )

    await service.transition_interaction(
        one.id,
        InteractionTransition(trigger="pause"),
        conversation.workspace_id,
    )
    with pytest.raises(InteractionNotAcceptingMessagesError):
        await service.send_message(
            one.id,
            MessageCreate(content="blocked"),
            "user-1",
            conversation.workspace_id,
        )


@pytest.mark.asyncio
async def test_interactions_injection_auto_links_to_latest_agent_message_and_history_aliases() -> (
    None
):
    service, _repo, _workspaces, _producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Injection"),
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
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="start"),
        conversation.workspace_id,
    )
    root = await service.send_message(
        interaction.id,
        MessageCreate(content="user-msg"),
        "user-1",
        conversation.workspace_id,
    )
    agent = await service.send_message(
        interaction.id,
        MessageCreate(
            content="agent-msg",
            parent_message_id=root.id,
            message_type=MessageType.agent,
        ),
        "ops:agent",
        conversation.workspace_id,
    )
    injected = await service.inject_message(
        interaction.id,
        MessageInject(content="Please include EU"),
        "user-1",
        conversation.workspace_id,
    )

    history = await service.get_conversation_history(interaction.id, limit=10)
    alias_history = await service.list_conversation_history(uuid4(), interaction.id, limit=10)

    assert injected.message_type == MessageType.injection
    assert injected.parent_message_id == agent.id
    assert [item.id for item in history] == [root.id, agent.id, injected.id]
    assert [item.id for item in alias_history] == [root.id, agent.id, injected.id]
