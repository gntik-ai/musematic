from __future__ import annotations

from platform.interactions.models import (
    AttentionStatus,
    BranchStatus,
    InteractionState,
    ParticipantRole,
)
from uuid import uuid4

import pytest

from tests.interactions_support import (
    SessionStub,
    _ScalarResult,
    _ScalarsResult,
    build_attention_request,
    build_branch,
    build_conversation,
    build_goal_message,
    build_interaction,
    build_message,
    build_participant,
    build_repository,
)


@pytest.mark.asyncio
async def test_interactions_repository_mutations_flush_and_update_objects() -> None:
    workspace_id = uuid4()
    session = SessionStub()
    repo = build_repository(session)
    conversation = await repo.create_conversation(
        workspace_id=workspace_id,
        title="Repo",
        created_by="user-1",
        metadata={"priority": "high"},
    )
    updated = await repo.update_conversation(conversation, title="Repo 2", metadata={"done": True})
    deleted = await repo.soft_delete_conversation(conversation)
    interaction = await repo.create_interaction(
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        goal_id=None,
        state=InteractionState.ready,
    )
    transitioned_interaction = build_interaction(
        interaction_id=interaction.id,
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        state=InteractionState.running,
    )
    session.execute_results.extend(
        [
            _ScalarResult(interaction.id),
            _ScalarResult(transitioned_interaction),
            _ScalarResult(None),
            _ScalarResult(None),
        ]
    )
    transitioned = await repo.transition_interaction_state(
        interaction_id=interaction.id,
        workspace_id=workspace_id,
        expected_state=InteractionState.ready,
        new_state=InteractionState.running,
        error_metadata=None,
        started_at=interaction.created_at,
        completed_at=None,
    )
    message = await repo.create_message(
        interaction_id=interaction.id,
        parent_message_id=None,
        sender_identity="user-1",
        message_type="user",
        content="hello",
        metadata={},
    )
    participant = await repo.add_participant(
        interaction_id=interaction.id,
        identity="user-1",
        role=ParticipantRole.initiator,
    )
    removed = await repo.remove_participant(participant)
    goal_message = await repo.create_goal_message(
        workspace_id=workspace_id,
        goal_id=uuid4(),
        participant_identity="user-1",
        content="goal",
        interaction_id=interaction.id,
        metadata={},
    )
    branch = await repo.create_branch(
        conversation_id=conversation.id,
        parent_interaction_id=interaction.id,
        branch_interaction_id=uuid4(),
        branch_point_message_id=message.id,
    )
    merge_record = await repo.create_merge_record(
        branch_id=branch.id,
        merged_by="user-1",
        conflict_detected=False,
        conflict_resolution=None,
        messages_merged_count=1,
    )
    attention = await repo.create_attention_request(
        workspace_id=workspace_id,
        source_agent_fqn="ops:agent",
        target_identity="user-1",
        urgency="high",
        context_summary="Need review",
        related_execution_id=None,
        related_interaction_id=interaction.id,
        related_goal_id=None,
    )
    attention = await repo.update_attention_status(
        attention,
        status=AttentionStatus.acknowledged,
        acknowledged_at=attention.created_at,
        resolved_at=None,
    )
    adjusted = await repo.adjust_message_count(
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        delta=3,
    )

    assert updated.title == "Repo 2"
    assert deleted.deleted_at is not None
    assert transitioned is transitioned_interaction
    assert transitioned.state == InteractionState.running
    assert message.content == "hello"
    assert removed.left_at is not None
    assert goal_message.content == "goal"
    assert branch.branch_point_message_id == message.id
    assert merge_record.messages_merged_count == 1
    assert attention.status == AttentionStatus.acknowledged
    assert adjusted is None
    assert session.flush_count >= 11


@pytest.mark.asyncio
async def test_interactions_repository_lookup_listing_and_counts_use_session_results() -> None:
    workspace_id = uuid4()
    conversation = build_conversation(workspace_id=workspace_id)
    interaction = build_interaction(conversation_id=conversation.id, workspace_id=workspace_id)
    message = build_message(interaction_id=interaction.id)
    participant = build_participant(interaction_id=interaction.id)
    goal_message = build_goal_message(workspace_id=workspace_id, interaction_id=interaction.id)
    attention = build_attention_request(workspace_id=workspace_id)
    branch = build_branch(conversation_id=conversation.id, parent_interaction_id=interaction.id)

    session = SessionStub(
        execute_results=[
            _ScalarsResult([conversation]),
            _ScalarResult(conversation),
            _ScalarResult(interaction),
            _ScalarsResult([interaction]),
            _ScalarResult(message),
            _ScalarsResult([message]),
            _ScalarsResult([message]),
            _ScalarResult(message),
            _ScalarResult(participant),
            _ScalarsResult([participant]),
            _ScalarsResult([goal_message]),
            _ScalarsResult([goal_message]),
            _ScalarResult(branch),
            _ScalarsResult([branch]),
            _ScalarResult(attention),
            _ScalarsResult([attention]),
            _ScalarResult("user-1"),
        ],
        scalar_results=[1, 1, 1, 1, 1],
    )
    repo = build_repository(session)

    listed_conversations, conversations_total = await repo.list_conversations(workspace_id, 1, 10)
    fetched_conversation = await repo.get_conversation(conversation.id, workspace_id)
    fetched_interaction = await repo.get_interaction(interaction.id, workspace_id)
    listed_interactions, interactions_total = await repo.list_interactions(
        conversation.id,
        workspace_id,
        1,
        10,
        None,
    )
    fetched_message = await repo.get_message(message.id)
    listed_messages, messages_total = await repo.list_messages(interaction.id, 1, 10)
    context_messages = await repo.list_messages_for_context(interaction.id, 10)
    validated_parent = await repo.validate_parent_message(
        interaction_id=interaction.id,
        parent_message_id=message.id,
    )
    fetched_participant = await repo.get_participant(interaction.id, participant.identity)
    participants = await repo.list_participants(interaction.id)
    listed_goal_messages, goal_total = await repo.list_goal_messages(
        workspace_id=workspace_id,
        goal_id=goal_message.goal_id,
        page=1,
        page_size=10,
    )
    goal_context = await repo.get_goal_messages_for_context(
        workspace_id=workspace_id,
        goal_id=goal_message.goal_id,
        limit=10,
    )
    fetched_branch = await repo.get_branch(branch.id, workspace_id)
    branches = await repo.list_branches(conversation.id, workspace_id)
    fetched_attention = await repo.get_attention_request(attention.id, workspace_id)
    attention_list, attention_total = await repo.list_attention_requests(
        workspace_id=workspace_id,
        target_identity=attention.target_identity,
        status=None,
        page=1,
        page_size=10,
    )
    initiator = await repo.get_initiator_identity(interaction.id)

    assert fetched_conversation is conversation
    assert listed_conversations == [conversation]
    assert conversations_total == 1
    assert fetched_interaction is interaction
    assert listed_interactions == [interaction]
    assert interactions_total == 1
    assert fetched_message is message
    assert listed_messages == [message]
    assert messages_total == 1
    assert context_messages == [message]
    assert validated_parent is message
    assert fetched_participant is participant
    assert participants == [participant]
    assert listed_goal_messages == [goal_message]
    assert goal_total == 1
    assert goal_context == [goal_message]
    assert fetched_branch is branch
    assert branches == [branch]
    assert fetched_attention is attention
    assert attention_list == [attention]
    assert attention_total == 1
    assert initiator == "user-1"


@pytest.mark.asyncio
async def test_interactions_repository_branch_copy_merge_and_conflict_helpers() -> None:
    workspace_id = uuid4()
    parent = build_interaction(workspace_id=workspace_id)
    root = build_message(interaction_id=parent.id, content="root")
    child = build_message(
        interaction_id=parent.id,
        content="child",
        parent_message_id=root.id,
    )
    branch = build_branch(
        conversation_id=parent.conversation_id,
        parent_interaction_id=parent.id,
        branch_interaction_id=uuid4(),
        branch_point_message_id=child.id,
    )
    branch.created_at = child.created_at
    branch_child = build_message(
        interaction_id=branch.branch_interaction_id,
        content="branch-child",
        parent_message_id=child.id,
        created_at=branch.created_at,
    )

    session = SessionStub(
        execute_results=[
            _ScalarsResult([root, child]),
            _ScalarsResult([branch_child]),
        ],
        scalar_results=[1],
    )
    repo = build_repository(session)
    copied = await repo.copy_messages_up_to(
        parent_interaction_id=parent.id,
        branch_interaction_id=branch.branch_interaction_id,
        branch_point_message_id=child.id,
    )
    merged_count = await repo.merge_branch_messages(branch=branch, merge_anchor_id=root.id)
    updated_branch = await repo.update_branch_status(branch, BranchStatus.merged)
    conflict = await repo.check_prior_merges_from_same_point(branch)

    assert len(copied) == 2
    assert copied[1].parent_message_id == copied[0].id
    assert merged_count == 1
    assert updated_branch.status == BranchStatus.merged
    assert conflict is True
