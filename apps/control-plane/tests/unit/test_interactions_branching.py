from __future__ import annotations

from platform.interactions.models import BranchStatus
from platform.interactions.schemas import (
    BranchCreate,
    BranchMerge,
    ConversationCreate,
    InteractionCreate,
    InteractionTransition,
    MessageCreate,
)
from uuid import uuid4

import pytest

from tests.interactions_support import build_service


@pytest.mark.asyncio
async def test_interactions_branching_copies_history_and_preserves_isolation() -> None:
    service, _repo, _workspaces, _producer = build_service()
    conversation = await service.create_conversation(
        ConversationCreate(title="Branch"),
        "user-1",
        uuid4(),
    )
    parent = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        conversation.workspace_id,
    )
    await service.transition_interaction(
        parent.id,
        InteractionTransition(trigger="ready"),
        conversation.workspace_id,
    )
    await service.transition_interaction(
        parent.id,
        InteractionTransition(trigger="start"),
        conversation.workspace_id,
    )
    first = await service.send_message(
        parent.id,
        MessageCreate(content="m1"),
        "user-1",
        conversation.workspace_id,
    )
    second = await service.send_message(
        parent.id,
        MessageCreate(content="m2", parent_message_id=first.id),
        "user-1",
        conversation.workspace_id,
    )
    await service.send_message(
        parent.id,
        MessageCreate(content="m3", parent_message_id=second.id),
        "user-1",
        conversation.workspace_id,
    )

    branch = await service.create_branch(
        BranchCreate(parent_interaction_id=parent.id, branch_point_message_id=second.id),
        conversation.workspace_id,
    )
    branch_history = await service.list_messages(
        branch.branch_interaction_id,
        conversation.workspace_id,
        1,
        20,
    )
    parent_history = await service.list_messages(parent.id, conversation.workspace_id, 1, 20)
    await service.send_message(
        branch.branch_interaction_id,
        MessageCreate(content="branch-msg", parent_message_id=branch_history.items[-1].id),
        "user-1",
        conversation.workspace_id,
    )
    updated_branch_history = await service.list_messages(
        branch.branch_interaction_id,
        conversation.workspace_id,
        1,
        20,
    )
    updated_parent_history = await service.list_messages(
        parent.id, conversation.workspace_id, 1, 20
    )

    assert len(branch_history.items) == 2
    assert [item.content for item in branch_history.items] == ["m1", "m2"]
    assert {item.id for item in branch_history.items}.isdisjoint(
        {item.id for item in parent_history.items}
    )
    assert len(updated_branch_history.items) == 3
    assert len(updated_parent_history.items) == 3


@pytest.mark.asyncio
async def test_interactions_branching_merge_conflict_and_abandon_flow() -> None:
    service, _repo, workspaces, producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    conversation = await service.create_conversation(
        ConversationCreate(title="Merge"),
        str(user_id),
        workspace_id,
    )
    parent = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        str(user_id),
        workspace_id,
    )
    await service.transition_interaction(
        parent.id, InteractionTransition(trigger="ready"), workspace_id
    )
    await service.transition_interaction(
        parent.id, InteractionTransition(trigger="start"), workspace_id
    )
    root = await service.send_message(
        parent.id, MessageCreate(content="root"), str(user_id), workspace_id
    )
    pivot = await service.send_message(
        parent.id,
        MessageCreate(content="pivot", parent_message_id=root.id),
        str(user_id),
        workspace_id,
    )

    branch_one = await service.create_branch(
        BranchCreate(parent_interaction_id=parent.id, branch_point_message_id=pivot.id),
        workspace_id,
    )
    branch_one_history = await service.list_messages(
        branch_one.branch_interaction_id, workspace_id, 1, 20
    )
    await service.send_message(
        branch_one.branch_interaction_id,
        MessageCreate(content="branch-one", parent_message_id=branch_one_history.items[-1].id),
        str(user_id),
        workspace_id,
    )
    merge_one = await service.merge_branch(
        branch_one.id,
        BranchMerge(conflict_resolution="accept"),
        str(user_id),
        workspace_id,
    )

    branch_two = await service.create_branch(
        BranchCreate(parent_interaction_id=parent.id, branch_point_message_id=pivot.id),
        workspace_id,
    )
    branch_two_history = await service.list_messages(
        branch_two.branch_interaction_id, workspace_id, 1, 20
    )
    await service.send_message(
        branch_two.branch_interaction_id,
        MessageCreate(content="branch-two", parent_message_id=branch_two_history.items[-1].id),
        str(user_id),
        workspace_id,
    )
    merge_two = await service.merge_branch(
        branch_two.id,
        BranchMerge(conflict_resolution="manual"),
        str(user_id),
        workspace_id,
    )
    abandoned = await service.create_branch(
        BranchCreate(parent_interaction_id=parent.id, branch_point_message_id=pivot.id),
        workspace_id,
    )
    abandoned_response = await service.abandon_branch(abandoned.id, workspace_id)
    branches = await service.list_branches(conversation.id, workspace_id)
    parent_history = await service.list_messages(parent.id, workspace_id, 1, 20)

    assert merge_one.conflict_detected is False
    assert merge_two.conflict_detected is True
    assert abandoned_response.status == BranchStatus.abandoned
    assert len(branches) == 3
    assert [
        event["event_type"] for event in producer.events if event["event_type"] == "branch.merged"
    ] == [
        "branch.merged",
        "branch.merged",
    ]
    assert any(item.content == "branch-one" for item in parent_history.items)
    assert any(item.content == "branch-two" for item in parent_history.items)
