from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.interactions.exceptions import (
    AttentionRequestNotFoundError,
    BranchNotFoundError,
    ConversationNotFoundError,
    GoalNotAcceptingMessagesError,
    InteractionNotAcceptingMessagesError,
    InteractionNotFoundError,
    InvalidStateTransitionError,
)
from platform.interactions.models import (
    AttentionStatus,
    AttentionUrgency,
    InteractionState,
    ParticipantRole,
)
from platform.interactions.schemas import (
    AttentionRequestCreate,
    AttentionResolve,
    BranchCreate,
    BranchMerge,
    ConversationCreate,
    ConversationUpdate,
    GoalMessageCreate,
    InteractionCreate,
    InteractionTransition,
    MessageCreate,
    MessageInject,
    ParticipantAdd,
)
from platform.interactions.service import InteractionsService
from platform.workspaces.models import GoalStatus
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.interactions_support import (
    InMemoryInteractionsRepo,
    SessionStub,
    WorkspacesServiceStub,
    build_conversation,
    build_repository,
    build_service,
)


class RaceTransitionRepo(InMemoryInteractionsRepo):
    async def transition_interaction_state(
        self,
        *,
        interaction_id,
        workspace_id,
        expected_state,
        new_state,
        error_metadata,
        started_at,
        completed_at,
    ):
        if expected_state == InteractionState.ready:
            interaction = await self.get_interaction(interaction_id, workspace_id)
            if interaction is not None:
                interaction.state = new_state
                interaction.error_metadata = error_metadata
                interaction.started_at = started_at
                interaction.completed_at = completed_at
            return None
        return await super().transition_interaction_state(
            interaction_id=interaction_id,
            workspace_id=workspace_id,
            expected_state=expected_state,
            new_state=new_state,
            error_metadata=error_metadata,
            started_at=started_at,
            completed_at=completed_at,
        )


class _ScalarResultStub:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_interactions_service_commits_conversation_creation_before_return() -> None:
    session = SessionStub()
    service = InteractionsService(
        repository=build_repository(session),
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        workspaces_service=WorkspacesServiceStub(),
        registry_service=None,
    )

    created = await service.create_conversation(
        ConversationCreate(title="Committed conversation"),
        "user-1",
        uuid4(),
    )

    assert created.title == "Committed conversation"
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.committed is True


@pytest.mark.asyncio
async def test_interactions_service_commits_interaction_creation_before_return() -> None:
    workspace_id = uuid4()
    conversation = build_conversation(workspace_id=workspace_id)
    session = SessionStub(
        execute_results=[
            _ScalarResultStub(conversation),
            _ScalarResultStub(None),
        ]
    )
    service = InteractionsService(
        repository=build_repository(session),
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        workspaces_service=WorkspacesServiceStub(),
        registry_service=None,
    )

    created = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        workspace_id,
    )

    assert created.conversation_id == conversation.id
    assert session.flush_count == 2
    assert session.commit_count == 1
    assert session.committed is True


@pytest.mark.asyncio
async def test_interactions_service_conversation_management_and_missing_paths() -> None:
    service, _repo, _workspaces, _producer = build_service()
    workspace_id = uuid4()
    conversation = await service.create_conversation(
        ConversationCreate(title="Conversation"),
        "user-1",
        workspace_id,
    )

    listed = await service.list_conversations(workspace_id, 1, 10)
    updated = await service.update_conversation(
        conversation.id,
        ConversationUpdate(title="  Updated "),
        workspace_id,
    )
    fetched = await service.get_conversation(conversation.id, workspace_id)
    await service.delete_conversation(conversation.id, workspace_id)

    assert listed.total == 1
    assert updated.title == "Updated"
    assert fetched.id == conversation.id

    with pytest.raises(ConversationNotFoundError):
        await service.get_conversation(conversation.id, workspace_id)

    with pytest.raises(ConversationNotFoundError):
        await service.update_conversation(
            uuid4(),
            ConversationUpdate(title="Missing"),
            workspace_id,
        )

    with pytest.raises(ConversationNotFoundError):
        await service.delete_conversation(uuid4(), workspace_id)


@pytest.mark.asyncio
async def test_interactions_service_interaction_listing_and_participant_edges() -> None:
    service, _repo, _workspaces, _producer = build_service()
    workspace_id = uuid4()
    conversation = await service.create_conversation(
        ConversationCreate(title="Interactions"),
        "user-1",
        workspace_id,
    )

    with pytest.raises(ConversationNotFoundError):
        await service.create_interaction(
            InteractionCreate(conversation_id=uuid4()),
            "user-1",
            workspace_id,
        )

    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        workspace_id,
    )
    listed = await service.list_interactions(
        conversation.id,
        workspace_id,
        1,
        10,
        InteractionState.initializing,
    )
    participant = await service.add_participant(
        interaction.id,
        ParticipantAdd(identity="observer", role=ParticipantRole.observer),
        workspace_id,
    )
    participants = await service.list_participants(interaction.id, workspace_id)
    await service.remove_participant(interaction.id, "missing", workspace_id)

    assert listed.total == 1
    assert participant.identity == "observer"
    assert [item.identity for item in participants] == ["user-1", "observer"]

    with pytest.raises(InteractionNotFoundError):
        await service.get_interaction(uuid4(), workspace_id)

    with pytest.raises(ConversationNotFoundError):
        await service.list_interactions(uuid4(), workspace_id, 1, 10)


@pytest.mark.asyncio
async def test_interactions_service_transition_race_and_injection_guard() -> None:
    workspaces = WorkspacesServiceStub()
    service = InteractionsService(
        repository=RaceTransitionRepo(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        workspaces_service=workspaces,  # type: ignore[arg-type]
        registry_service=None,
    )
    workspace_id = uuid4()
    conversation = await service.create_conversation(
        ConversationCreate(title="Race"),
        "user-1",
        workspace_id,
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        workspace_id,
    )
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="ready"),
        workspace_id,
    )

    with pytest.raises(InvalidStateTransitionError) as transition_error:
        await service.transition_interaction(
            interaction.id,
            InteractionTransition(trigger="start"),
            workspace_id,
        )

    assert transition_error.value.current_state == InteractionState.running.value

    regular_service, _repo, _workspaces, _producer = build_service()
    regular_conversation = await regular_service.create_conversation(
        ConversationCreate(title="Injection"),
        "user-1",
        uuid4(),
    )
    regular_interaction = await regular_service.create_interaction(
        InteractionCreate(conversation_id=regular_conversation.id),
        "user-1",
        regular_conversation.workspace_id,
    )

    with pytest.raises(InteractionNotAcceptingMessagesError):
        await regular_service.inject_message(
            regular_interaction.id,
            MessageInject(content="blocked"),
            "user-1",
            regular_conversation.workspace_id,
        )


@pytest.mark.asyncio
async def test_interactions_service_goal_branch_attention_and_subscription_edges() -> None:
    service, repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    member_id = uuid4()
    other_member_id = uuid4()
    workspaces.add_member(workspace_id, member_id)
    workspaces.add_member(workspace_id, other_member_id)

    conversation = await service.create_conversation(
        ConversationCreate(title="Workspace"),
        str(member_id),
        workspace_id,
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        str(member_id),
        workspace_id,
    )
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="ready"),
        workspace_id,
    )
    await service.transition_interaction(
        interaction.id,
        InteractionTransition(trigger="start"),
        workspace_id,
    )
    root = await service.send_message(
        interaction.id,
        MessageCreate(content="root"),
        str(member_id),
        workspace_id,
    )

    repo.interactions[interaction.id].state = InteractionState.completed
    branch = await service.create_branch(
        BranchCreate(
            parent_interaction_id=interaction.id,
            branch_point_message_id=root.id,
        ),
        workspace_id,
    )

    assert repo.interactions[branch.branch_interaction_id].state == InteractionState.ready

    with pytest.raises(BranchNotFoundError):
        await service.merge_branch(
            uuid4(),
            BranchMerge(conflict_resolution="accept"),
            str(member_id),
            workspace_id,
        )

    with pytest.raises(BranchNotFoundError):
        await service.abandon_branch(uuid4(), workspace_id)

    open_goal_id = uuid4()
    completed_goal_id = uuid4()
    missing_goal_id = uuid4()
    workspaces.add_goal(workspace_id, open_goal_id, status=GoalStatus.open)
    workspaces.add_goal(workspace_id, completed_goal_id, status=GoalStatus.completed)

    posted = await service.post_goal_message(
        open_goal_id,
        GoalMessageCreate(content="open"),
        "ops:agent",
        workspace_id,
    )
    assert posted.participant_identity == "ops:agent"

    with pytest.raises(GoalNotAcceptingMessagesError):
        await service.post_goal_message(
            missing_goal_id,
            GoalMessageCreate(content="missing"),
            "ops:agent",
            workspace_id,
        )

    with pytest.raises(GoalNotAcceptingMessagesError):
        await service.post_goal_message(
            completed_goal_id,
            GoalMessageCreate(content="done"),
            "ops:agent",
            workspace_id,
        )

    service_without_workspaces = InteractionsService(
        repository=InMemoryInteractionsRepo(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        workspaces_service=None,
        registry_service=None,
    )
    with pytest.raises(GoalNotAcceptingMessagesError):
        await service_without_workspaces.post_goal_message(
            uuid4(),
            GoalMessageCreate(content="unknown"),
            "ops:agent",
            workspace_id,
        )

    with pytest.raises(InteractionNotFoundError):
        await service.create_attention_request(
            AttentionRequestCreate(
                target_identity=str(member_id),
                urgency=AttentionUrgency.high,
                context_summary="Needs context",
                related_interaction_id=uuid4(),
            ),
            "ops:agent",
            workspace_id,
        )

    created_attention = await service.create_attention_request(
        AttentionRequestCreate(
            target_identity=str(member_id),
            urgency=AttentionUrgency.critical,
            context_summary="Escalate",
        ),
        "ops:agent",
        workspace_id,
    )
    attention_id = created_attention.id

    with pytest.raises(AttentionRequestNotFoundError):
        await service.resolve_attention_request(
            uuid4(),
            AttentionResolve(action="resolve"),
            workspace_id,
            requester_identity=str(member_id),
        )

    with pytest.raises(AuthorizationError):
        await service.resolve_attention_request(
            attention_id,
            AttentionResolve(action="acknowledge"),
            workspace_id,
            requester_identity=str(other_member_id),
        )

    repo.attention_requests[attention_id].status = AttentionStatus.acknowledged
    with pytest.raises(ValidationError):
        await service.resolve_attention_request(
            attention_id,
            AttentionResolve(action="acknowledge"),
            workspace_id,
            requester_identity=str(member_id),
        )

    repo.attention_requests[attention_id].status = AttentionStatus.dismissed
    with pytest.raises(ValidationError):
        await service.resolve_attention_request(
            attention_id,
            AttentionResolve(action="resolve"),
            workspace_id,
            requester_identity=str(member_id),
        )

    repo.attention_requests[attention_id].status = AttentionStatus.resolved
    with pytest.raises(ValidationError):
        await service.resolve_attention_request(
            attention_id,
            AttentionResolve(action="dismiss"),
            workspace_id,
            requester_identity=str(member_id),
        )

    assert (
        await service.check_subscription_access(
            str(member_id),
            "conversation",
            conversation.id,
            workspace_id,
        )
        is True
    )
    assert (
        await service.check_subscription_access(
            str(member_id),
            "interaction",
            interaction.id,
            workspace_id,
        )
        is True
    )
    assert (
        await service.check_subscription_access(
            str(member_id),
            "attention",
            member_id,
            workspace_id,
        )
        is True
    )
    assert (
        await service.check_subscription_access(
            "not-a-uuid",
            "conversation",
            conversation.id,
            workspace_id,
        )
        is False
    )
    assert (
        await service.check_subscription_access(
            str(member_id),
            "unknown",
            conversation.id,
            workspace_id,
        )
        is False
    )
    assert (
        await service_without_workspaces.check_subscription_access(
            str(member_id),
            "conversation",
            conversation.id,
            workspace_id,
        )
        is False
    )



@pytest.mark.asyncio
async def test_interactions_service_attention_success_paths_and_goal_message_views() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    member_id = uuid4()
    workspaces.add_member(workspace_id, member_id)
    goal_id = uuid4()
    workspaces.add_goal(workspace_id, goal_id, status=GoalStatus.open)

    await service.post_goal_message(
        goal_id,
        GoalMessageCreate(content="first"),
        str(member_id),
        workspace_id,
    )
    await service.post_goal_message(
        goal_id,
        GoalMessageCreate(content="second"),
        str(member_id),
        workspace_id,
    )

    goal_page = await service.list_goal_messages(goal_id, workspace_id, 1, 10)
    goal_context = await service.get_goal_messages(workspace_id, goal_id, limit=10)

    pending = await service.create_attention_request(
        AttentionRequestCreate(
            target_identity=str(member_id),
            urgency=AttentionUrgency.high,
            context_summary="Needs action",
        ),
        "ops:agent",
        workspace_id,
    )
    resolved = await service.create_attention_request(
        AttentionRequestCreate(
            target_identity=str(member_id),
            urgency=AttentionUrgency.medium,
            context_summary="Resolve this",
        ),
        "ops:agent",
        workspace_id,
    )
    dismissed = await service.create_attention_request(
        AttentionRequestCreate(
            target_identity=str(member_id),
            urgency=AttentionUrgency.low,
            context_summary="Dismiss this",
        ),
        "ops:agent",
        workspace_id,
    )

    listed = await service.list_attention_requests(str(member_id), workspace_id, None, 1, 10)
    acknowledged = await service.resolve_attention_request(
        pending.id,
        AttentionResolve(action="acknowledge"),
        workspace_id,
        requester_identity=str(member_id),
    )
    resolved_item = await service.resolve_attention_request(
        resolved.id,
        AttentionResolve(action="resolve"),
        workspace_id,
        requester_identity=str(member_id),
    )
    dismissed_item = await service.resolve_attention_request(
        dismissed.id,
        AttentionResolve(action="dismiss"),
        workspace_id,
        requester_identity=str(member_id),
    )

    assert goal_page.total == 2
    assert len(goal_page.items) == 2
    assert [item.content for item in goal_context] == ["first", "second"]
    assert listed.total == 3
    assert acknowledged.status == AttentionStatus.acknowledged
    assert acknowledged.acknowledged_at is not None
    assert resolved_item.status == AttentionStatus.resolved
    assert resolved_item.acknowledged_at is not None
    assert resolved_item.resolved_at is not None
    assert dismissed_item.status == AttentionStatus.dismissed
    assert dismissed_item.resolved_at is not None


@pytest.mark.asyncio
async def test_create_attention_request_marks_event_when_alert_is_created() -> None:
    handled_payloads = []

    async def _handle_attention_alert(payload):
        handled_payloads.append(payload)
        return object()

    service, _repo, _workspaces, producer = build_service(
        attention_alert_handler=_handle_attention_alert,
    )
    workspace_id = uuid4()
    member_id = uuid4()

    created = await service.create_attention_request(
        AttentionRequestCreate(
            target_identity=str(member_id),
            urgency=AttentionUrgency.high,
            context_summary="Needs action",
        ),
        "ops:agent",
        workspace_id,
    )

    assert created.target_identity == str(member_id)
    assert handled_payloads[0].request_id == created.id
    assert producer.events[-1]["event_type"] == "attention.requested"
    assert producer.events[-1]["payload"]["alert_already_created"] is True
