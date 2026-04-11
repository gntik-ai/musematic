from __future__ import annotations

import asyncio
from platform.interactions.exceptions import InvalidStateTransitionError
from platform.interactions.models import InteractionState
from platform.interactions.schemas import (
    ConversationCreate,
    InteractionCreate,
    InteractionTransition,
    MessageCreate,
)
from uuid import uuid4

import pytest

from tests.interactions_support import build_service


@pytest.mark.asyncio
async def test_interactions_concurrency_message_isolation_and_counts() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    conversation = await service.create_conversation(
        ConversationCreate(title="Concurrency"),
        str(user_id),
        workspace_id,
    )
    interactions = [
        await service.create_interaction(
            InteractionCreate(conversation_id=conversation.id),
            str(user_id),
            workspace_id,
        )
        for _ in range(10)
    ]
    for item in interactions:
        await service.transition_interaction(
            item.id, InteractionTransition(trigger="ready"), workspace_id
        )
        await service.transition_interaction(
            item.id, InteractionTransition(trigger="start"), workspace_id
        )

    async def _send(index: int, interaction_id) -> None:
        await service.send_message(
            interaction_id,
            MessageCreate(content=f"msg-{index}"),
            str(user_id),
            workspace_id,
        )

    await asyncio.gather(*[_send(index, item.id) for index, item in enumerate(interactions)])
    histories = await asyncio.gather(
        *[service.list_messages(item.id, workspace_id, 1, 10) for item in interactions]
    )
    refreshed = await service.get_conversation(conversation.id, workspace_id)

    assert all(history.total == 1 for history in histories)
    assert refreshed.message_count == 10
    assert len({history.items[0].content for history in histories}) == 10


@pytest.mark.asyncio
async def test_interactions_concurrency_transition_guard_and_subscription_access() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    outsider_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    conversation = await service.create_conversation(
        ConversationCreate(title="Guard"),
        str(user_id),
        workspace_id,
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        str(user_id),
        workspace_id,
    )
    await service.transition_interaction(
        interaction.id, InteractionTransition(trigger="ready"), workspace_id
    )

    async def _start() -> InteractionState:
        result = await service.transition_interaction(
            interaction.id,
            InteractionTransition(trigger="start"),
            workspace_id,
        )
        return result.state

    results = await asyncio.gather(_start(), _start(), return_exceptions=True)

    assert results.count(InteractionState.running) == 1
    assert any(isinstance(item, InvalidStateTransitionError) for item in results)
    assert await service.check_subscription_access(
        str(user_id),
        "conversation",
        conversation.id,
        workspace_id,
    )
    assert await service.check_subscription_access(
        str(user_id),
        "interaction",
        interaction.id,
        workspace_id,
    )
    assert await service.check_subscription_access(
        str(user_id),
        "attention",
        user_id,
        workspace_id,
    )
    assert not await service.check_subscription_access(
        str(outsider_id),
        "conversation",
        conversation.id,
        workspace_id,
    )
