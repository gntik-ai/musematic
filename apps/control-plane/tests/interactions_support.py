from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.interactions.exceptions import MessageNotInInteractionError
from platform.interactions.models import (
    AttentionRequest,
    AttentionStatus,
    AttentionUrgency,
    BranchMergeRecord,
    BranchStatus,
    Conversation,
    ConversationBranch,
    Interaction,
    InteractionMessage,
    InteractionParticipant,
    InteractionState,
    MessageType,
    ParticipantRole,
    WorkspaceGoalMessage,
)
from platform.interactions.repository import InteractionsRepository
from platform.interactions.service import InteractionsService
from platform.workspaces.models import GoalStatus
from typing import Any
from uuid import UUID, uuid4

from tests.auth_support import RecordingProducer
from tests.workspaces_support import build_goal


def _now() -> datetime:
    return datetime.now(UTC)


def build_conversation(
    *,
    conversation_id: UUID | None = None,
    workspace_id: UUID | None = None,
    title: str = "Conversation",
    created_by: str = "user-1",
    metadata: dict[str, Any] | None = None,
    message_count: int = 0,
) -> Conversation:
    item = Conversation(
        id=conversation_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        title=title,
        created_by=created_by,
        metadata_json=metadata or {},
        message_count=message_count,
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


def build_interaction(
    *,
    interaction_id: UUID | None = None,
    conversation_id: UUID | None = None,
    workspace_id: UUID | None = None,
    goal_id: UUID | None = None,
    state: InteractionState = InteractionState.initializing,
) -> Interaction:
    item = Interaction(
        id=interaction_id or uuid4(),
        conversation_id=conversation_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        goal_id=goal_id,
        state=state,
        state_changed_at=_now(),
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


def build_message(
    *,
    message_id: UUID | None = None,
    interaction_id: UUID | None = None,
    parent_message_id: UUID | None = None,
    sender_identity: str = "user-1",
    message_type: MessageType = MessageType.user,
    content: str = "hello",
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> InteractionMessage:
    created = created_at or _now()
    item = InteractionMessage(
        id=message_id or uuid4(),
        interaction_id=interaction_id or uuid4(),
        parent_message_id=parent_message_id,
        sender_identity=sender_identity,
        message_type=message_type,
        content=content,
        metadata_json=metadata or {},
    )
    item.created_at = created
    item.updated_at = created
    return item


def build_participant(
    *,
    participant_id: UUID | None = None,
    interaction_id: UUID | None = None,
    identity: str = "user-1",
    role: ParticipantRole = ParticipantRole.initiator,
    joined_at: datetime | None = None,
    left_at: datetime | None = None,
) -> InteractionParticipant:
    joined = joined_at or _now()
    item = InteractionParticipant(
        id=participant_id or uuid4(),
        interaction_id=interaction_id or uuid4(),
        identity=identity,
        role=role,
        joined_at=joined,
        left_at=left_at,
    )
    item.created_at = joined
    item.updated_at = joined
    return item


def build_goal_message(
    *,
    goal_message_id: UUID | None = None,
    workspace_id: UUID | None = None,
    goal_id: UUID | None = None,
    participant_identity: str = "user-1",
    content: str = "goal-message",
    interaction_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorkspaceGoalMessage:
    item = WorkspaceGoalMessage(
        id=goal_message_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        goal_id=goal_id or uuid4(),
        participant_identity=participant_identity,
        content=content,
        interaction_id=interaction_id,
        metadata_json=metadata or {},
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


def build_branch(
    *,
    branch_id: UUID | None = None,
    conversation_id: UUID | None = None,
    parent_interaction_id: UUID | None = None,
    branch_interaction_id: UUID | None = None,
    branch_point_message_id: UUID | None = None,
    status: BranchStatus = BranchStatus.active,
) -> ConversationBranch:
    item = ConversationBranch(
        id=branch_id or uuid4(),
        conversation_id=conversation_id or uuid4(),
        parent_interaction_id=parent_interaction_id or uuid4(),
        branch_interaction_id=branch_interaction_id or uuid4(),
        branch_point_message_id=branch_point_message_id or uuid4(),
        status=status,
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


def build_merge_record(
    *,
    merge_id: UUID | None = None,
    branch_id: UUID | None = None,
    merged_by: str = "user-1",
    conflict_detected: bool = False,
    conflict_resolution: str | None = None,
    messages_merged_count: int = 0,
) -> BranchMergeRecord:
    item = BranchMergeRecord(
        id=merge_id or uuid4(),
        branch_id=branch_id or uuid4(),
        merged_by=merged_by,
        conflict_detected=conflict_detected,
        conflict_resolution=conflict_resolution,
        messages_merged_count=messages_merged_count,
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


def build_attention_request(
    *,
    request_id: UUID | None = None,
    workspace_id: UUID | None = None,
    source_agent_fqn: str = "ops:agent",
    target_identity: str = "user-1",
    urgency: AttentionUrgency = AttentionUrgency.high,
    context_summary: str = "Need approval",
    related_execution_id: UUID | None = None,
    related_interaction_id: UUID | None = None,
    related_goal_id: UUID | None = None,
    status: AttentionStatus = AttentionStatus.pending,
) -> AttentionRequest:
    item = AttentionRequest(
        id=request_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        source_agent_fqn=source_agent_fqn,
        target_identity=target_identity,
        urgency=urgency,
        context_summary=context_summary,
        related_execution_id=related_execution_id,
        related_interaction_id=related_interaction_id,
        related_goal_id=related_goal_id,
        status=status,
    )
    item.created_at = _now()
    item.updated_at = item.created_at
    return item


class WorkspacesRepoShim:
    def __init__(self, goals: dict[tuple[UUID, UUID], Any]) -> None:
        self.goals = goals

    async def get_goal(self, workspace_id: UUID, goal_id: UUID) -> Any | None:
        return self.goals.get((workspace_id, goal_id))


class WorkspacesServiceStub:
    def __init__(self) -> None:
        self.workspace_memberships: dict[UUID, set[UUID]] = {}
        self.goals: dict[tuple[UUID, UUID], Any] = {}
        self.repo = WorkspacesRepoShim(self.goals)

    def add_member(self, workspace_id: UUID, user_id: UUID) -> None:
        self.workspace_memberships.setdefault(workspace_id, set()).add(user_id)

    def add_goal(
        self,
        workspace_id: UUID,
        goal_id: UUID,
        *,
        status: GoalStatus = GoalStatus.open,
    ) -> Any:
        goal = build_goal(workspace_id=workspace_id, goal_id=goal_id, status=status)
        self.goals[(workspace_id, goal_id)] = goal
        return goal

    async def get_goal(self, workspace_id: UUID, requester_id: UUID, goal_id: UUID) -> Any:
        if requester_id not in self.workspace_memberships.get(workspace_id, set()):
            raise LookupError("not a member")
        goal = self.goals.get((workspace_id, goal_id))
        if goal is None:
            raise LookupError("goal missing")
        return goal

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        return [
            workspace_id
            for workspace_id, members in self.workspace_memberships.items()
            if user_id in members
        ]


class InMemoryInteractionsRepo:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.interactions: dict[UUID, Interaction] = {}
        self.messages: dict[UUID, InteractionMessage] = {}
        self.participants: dict[tuple[UUID, str], InteractionParticipant] = {}
        self.goal_messages: dict[UUID, WorkspaceGoalMessage] = {}
        self.branches: dict[UUID, ConversationBranch] = {}
        self.merge_records: dict[UUID, BranchMergeRecord] = {}
        self.attention_requests: dict[UUID, AttentionRequest] = {}

    async def create_conversation(
        self, *, workspace_id: UUID, title: str, created_by: str, metadata: dict[str, Any]
    ) -> Conversation:
        conversation = build_conversation(
            workspace_id=workspace_id,
            title=title,
            created_by=created_by,
            metadata=metadata,
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def get_conversation(
        self, conversation_id: UUID, workspace_id: UUID
    ) -> Conversation | None:
        conversation = self.conversations.get(conversation_id)
        if (
            conversation is None
            or conversation.workspace_id != workspace_id
            or conversation.deleted_at is not None
        ):
            return None
        return conversation

    async def list_conversations(
        self, workspace_id: UUID, page: int, page_size: int
    ) -> tuple[list[Conversation], int]:
        items = [
            item
            for item in self.conversations.values()
            if item.workspace_id == workspace_id and item.deleted_at is None
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def soft_delete_conversation(self, conversation: Conversation) -> Conversation:
        conversation.deleted_at = _now()
        return conversation

    async def update_conversation(
        self,
        conversation: Conversation,
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        if title is not None:
            conversation.title = title
        if metadata is not None:
            conversation.metadata_json = dict(metadata)
        conversation.updated_at = _now()
        return conversation

    async def create_interaction(
        self,
        *,
        conversation_id: UUID,
        workspace_id: UUID,
        goal_id: UUID | None,
        state: InteractionState = InteractionState.initializing,
        state_changed_at: datetime | None = None,
        started_at: datetime | None = None,
    ) -> Interaction:
        interaction = build_interaction(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            goal_id=goal_id,
            state=state,
        )
        if state_changed_at is not None:
            interaction.state_changed_at = state_changed_at
        interaction.started_at = started_at
        self.interactions[interaction.id] = interaction
        return interaction

    async def get_interaction(self, interaction_id: UUID, workspace_id: UUID) -> Interaction | None:
        interaction = self.interactions.get(interaction_id)
        if interaction is None or interaction.workspace_id != workspace_id:
            return None
        conversation = self.conversations.get(interaction.conversation_id)
        if conversation is None or conversation.deleted_at is not None:
            return None
        return interaction

    async def list_interactions(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
        state: InteractionState | None = None,
    ) -> tuple[list[Interaction], int]:
        items = [
            item
            for item in self.interactions.values()
            if item.conversation_id == conversation_id
            and item.workspace_id == workspace_id
            and (state is None or item.state == state)
        ]
        items.sort(key=lambda item: (item.created_at, item.id))
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def transition_interaction_state(
        self,
        *,
        interaction_id: UUID,
        workspace_id: UUID,
        expected_state: InteractionState,
        new_state: InteractionState,
        error_metadata: dict[str, Any] | None,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> Interaction | None:
        interaction = await self.get_interaction(interaction_id, workspace_id)
        if interaction is None or interaction.state != expected_state:
            return None
        interaction.state = new_state
        interaction.state_changed_at = _now()
        interaction.error_metadata = error_metadata
        if started_at is not None:
            interaction.started_at = started_at
        if completed_at is not None:
            interaction.completed_at = completed_at
        interaction.updated_at = _now()
        return interaction

    async def create_message(
        self,
        *,
        interaction_id: UUID,
        parent_message_id: UUID | None,
        sender_identity: str,
        message_type: Any,
        content: str,
        metadata: dict[str, Any],
        created_at: datetime | None = None,
    ) -> InteractionMessage:
        message = build_message(
            interaction_id=interaction_id,
            parent_message_id=parent_message_id,
            sender_identity=sender_identity,
            message_type=message_type,
            content=content,
            metadata=metadata,
            created_at=created_at,
        )
        self.messages[message.id] = message
        return message

    async def get_message(
        self, message_id: UUID, interaction_id: UUID | None = None
    ) -> InteractionMessage | None:
        message = self.messages.get(message_id)
        if message is None:
            return None
        if interaction_id is not None and message.interaction_id != interaction_id:
            return None
        return message

    async def list_messages(
        self, interaction_id: UUID, page: int, page_size: int
    ) -> tuple[list[InteractionMessage], int]:
        items = [item for item in self.messages.values() if item.interaction_id == interaction_id]
        items.sort(key=lambda item: (item.created_at, item.id))
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def list_messages_for_context(
        self, interaction_id: UUID, limit: int
    ) -> list[InteractionMessage]:
        items = [item for item in self.messages.values() if item.interaction_id == interaction_id]
        items.sort(key=lambda item: (item.created_at, item.id))
        return items[-limit:]

    async def validate_parent_message(
        self,
        *,
        interaction_id: UUID,
        parent_message_id: UUID | None,
    ) -> InteractionMessage | None:
        if parent_message_id is None:
            return None
        message = self.messages.get(parent_message_id)
        if message is None or message.interaction_id != interaction_id:
            raise MessageNotInInteractionError(parent_message_id, interaction_id)
        return message

    async def increment_message_count(
        self, *, conversation_id: UUID, workspace_id: UUID, limit: int
    ) -> int | None:
        conversation = await self.get_conversation(conversation_id, workspace_id)
        if conversation is None or conversation.message_count >= limit:
            return None
        conversation.message_count += 1
        conversation.updated_at = _now()
        return conversation.message_count

    async def adjust_message_count(
        self,
        *,
        conversation_id: UUID,
        workspace_id: UUID,
        delta: int,
    ) -> int | None:
        conversation = await self.get_conversation(conversation_id, workspace_id)
        if conversation is None:
            return None
        conversation.message_count += delta
        conversation.updated_at = _now()
        return conversation.message_count

    async def get_latest_message(self, interaction_id: UUID) -> InteractionMessage | None:
        items = await self.list_messages_for_context(interaction_id, limit=10_000)
        return items[-1] if items else None

    async def get_latest_agent_message(self, interaction_id: UUID) -> InteractionMessage | None:
        items = [
            item
            for item in await self.list_messages_for_context(interaction_id, limit=10_000)
            if item.message_type == MessageType.agent
        ]
        return items[-1] if items else None

    async def add_participant(
        self,
        *,
        interaction_id: UUID,
        identity: str,
        role: ParticipantRole,
        joined_at: datetime | None = None,
    ) -> InteractionParticipant:
        participant = self.participants.get((interaction_id, identity))
        if participant is None:
            participant = build_participant(
                interaction_id=interaction_id,
                identity=identity,
                role=role,
                joined_at=joined_at,
            )
            self.participants[(interaction_id, identity)] = participant
        else:
            participant.role = role
            participant.left_at = None
        return participant

    async def get_participant(
        self, interaction_id: UUID, identity: str
    ) -> InteractionParticipant | None:
        return self.participants.get((interaction_id, identity))

    async def remove_participant(
        self, participant: InteractionParticipant
    ) -> InteractionParticipant:
        participant.left_at = _now()
        return participant

    async def list_participants(self, interaction_id: UUID) -> list[InteractionParticipant]:
        items = [
            item
            for (candidate_interaction_id, _identity), item in self.participants.items()
            if candidate_interaction_id == interaction_id
        ]
        items.sort(key=lambda item: (item.joined_at, item.id))
        return items

    async def create_goal_message(
        self,
        *,
        workspace_id: UUID,
        goal_id: UUID,
        participant_identity: str,
        content: str,
        interaction_id: UUID | None,
        metadata: dict[str, Any],
    ) -> WorkspaceGoalMessage:
        message = build_goal_message(
            workspace_id=workspace_id,
            goal_id=goal_id,
            participant_identity=participant_identity,
            content=content,
            interaction_id=interaction_id,
            metadata=metadata,
        )
        self.goal_messages[message.id] = message
        return message

    async def list_goal_messages(
        self,
        *,
        workspace_id: UUID,
        goal_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[WorkspaceGoalMessage], int]:
        items = [
            item
            for item in self.goal_messages.values()
            if item.workspace_id == workspace_id and item.goal_id == goal_id
        ]
        items.sort(key=lambda item: (item.created_at, item.id))
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def get_goal_messages_for_context(
        self, *, workspace_id: UUID, goal_id: UUID, limit: int
    ) -> list[WorkspaceGoalMessage]:
        items = [
            item
            for item in self.goal_messages.values()
            if item.workspace_id == workspace_id and item.goal_id == goal_id
        ]
        items.sort(key=lambda item: (item.created_at, item.id))
        return items[-limit:]

    async def create_branch(
        self,
        *,
        conversation_id: UUID,
        parent_interaction_id: UUID,
        branch_interaction_id: UUID,
        branch_point_message_id: UUID,
    ) -> ConversationBranch:
        branch = build_branch(
            conversation_id=conversation_id,
            parent_interaction_id=parent_interaction_id,
            branch_interaction_id=branch_interaction_id,
            branch_point_message_id=branch_point_message_id,
        )
        self.branches[branch.id] = branch
        return branch

    async def get_branch(self, branch_id: UUID, workspace_id: UUID) -> ConversationBranch | None:
        branch = self.branches.get(branch_id)
        if branch is None:
            return None
        conversation = await self.get_conversation(branch.conversation_id, workspace_id)
        return branch if conversation is not None else None

    async def list_branches(
        self, conversation_id: UUID, workspace_id: UUID
    ) -> list[ConversationBranch]:
        if await self.get_conversation(conversation_id, workspace_id) is None:
            return []
        items = [item for item in self.branches.values() if item.conversation_id == conversation_id]
        items.sort(key=lambda item: (item.created_at, item.id))
        return items

    async def update_branch_status(
        self, branch: ConversationBranch, status: BranchStatus
    ) -> ConversationBranch:
        branch.status = status
        branch.updated_at = _now()
        return branch

    async def copy_messages_up_to(
        self,
        *,
        parent_interaction_id: UUID,
        branch_interaction_id: UUID,
        branch_point_message_id: UUID,
    ) -> list[InteractionMessage]:
        source_messages = [
            item for item in self.messages.values() if item.interaction_id == parent_interaction_id
        ]
        source_messages.sort(key=lambda item: (item.created_at, item.id))
        copied: list[InteractionMessage] = []
        mapping: dict[UUID, UUID] = {}
        for source in source_messages:
            copy_parent = (
                mapping.get(source.parent_message_id)
                if source.parent_message_id is not None
                else None
            )
            copied_message = await self.create_message(
                interaction_id=branch_interaction_id,
                parent_message_id=copy_parent,
                sender_identity=source.sender_identity,
                message_type=source.message_type,
                content=source.content,
                metadata=dict(source.metadata_json),
                created_at=source.created_at,
            )
            mapping[source.id] = copied_message.id
            copied.append(copied_message)
            if source.id == branch_point_message_id:
                break
        return copied

    async def merge_branch_messages(
        self, *, branch: ConversationBranch, merge_anchor_id: UUID | None
    ) -> int:
        branch_messages = [
            item
            for item in self.messages.values()
            if item.interaction_id == branch.branch_interaction_id
            and item.created_at >= branch.created_at
        ]
        branch_messages.sort(key=lambda item: (item.created_at, item.id))
        mapping: dict[UUID, UUID] = {}
        for source in branch_messages:
            if source.parent_message_id is not None and source.parent_message_id in mapping:
                parent_id = mapping[source.parent_message_id]
            else:
                parent_id = merge_anchor_id
            merged = await self.create_message(
                interaction_id=branch.parent_interaction_id,
                parent_message_id=parent_id,
                sender_identity=source.sender_identity,
                message_type=source.message_type,
                content=source.content,
                metadata=dict(source.metadata_json),
                created_at=source.created_at,
            )
            mapping[source.id] = merged.id
        return len(branch_messages)

    async def check_prior_merges_from_same_point(self, branch: ConversationBranch) -> bool:
        for record in self.merge_records.values():
            other = self.branches[record.branch_id]
            if (
                other.id != branch.id
                and other.parent_interaction_id == branch.parent_interaction_id
                and other.branch_point_message_id == branch.branch_point_message_id
            ):
                return True
        return False

    async def create_merge_record(
        self,
        *,
        branch_id: UUID,
        merged_by: str,
        conflict_detected: bool,
        conflict_resolution: str | None,
        messages_merged_count: int,
    ) -> BranchMergeRecord:
        record = build_merge_record(
            branch_id=branch_id,
            merged_by=merged_by,
            conflict_detected=conflict_detected,
            conflict_resolution=conflict_resolution,
            messages_merged_count=messages_merged_count,
        )
        self.merge_records[record.id] = record
        return record

    async def create_attention_request(
        self,
        *,
        workspace_id: UUID,
        source_agent_fqn: str,
        target_identity: str,
        urgency: Any,
        context_summary: str,
        related_execution_id: UUID | None,
        related_interaction_id: UUID | None,
        related_goal_id: UUID | None,
    ) -> AttentionRequest:
        request = build_attention_request(
            workspace_id=workspace_id,
            source_agent_fqn=source_agent_fqn,
            target_identity=target_identity,
            urgency=urgency,
            context_summary=context_summary,
            related_execution_id=related_execution_id,
            related_interaction_id=related_interaction_id,
            related_goal_id=related_goal_id,
        )
        self.attention_requests[request.id] = request
        return request

    async def get_attention_request(
        self, request_id: UUID, workspace_id: UUID
    ) -> AttentionRequest | None:
        request = self.attention_requests.get(request_id)
        if request is None or request.workspace_id != workspace_id:
            return None
        return request

    async def list_attention_requests(
        self,
        *,
        workspace_id: UUID,
        target_identity: str,
        status: AttentionStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AttentionRequest], int]:
        items = [
            item
            for item in self.attention_requests.values()
            if item.workspace_id == workspace_id
            and item.target_identity == target_identity
            and (status is None or item.status == status)
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def update_attention_status(
        self,
        request: AttentionRequest,
        *,
        status: AttentionStatus,
        acknowledged_at: datetime | None,
        resolved_at: datetime | None,
    ) -> AttentionRequest:
        request.status = status
        request.acknowledged_at = acknowledged_at
        request.resolved_at = resolved_at
        request.updated_at = _now()
        return request

    async def get_initiator_identity(self, interaction_id: UUID) -> str | None:
        participant = self.participants.get((interaction_id, "user-1"))
        if (
            participant is not None
            and participant.role == ParticipantRole.initiator
            and participant.left_at is None
        ):
            return participant.identity
        for (candidate_interaction_id, _), candidate in self.participants.items():
            if (
                candidate_interaction_id == interaction_id
                and candidate.role == ParticipantRole.initiator
                and candidate.left_at is None
            ):
                return candidate.identity
        return None


def build_service(
    *,
    repo: InMemoryInteractionsRepo | None = None,
    workspaces_service: WorkspacesServiceStub | None = None,
    producer: RecordingProducer | None = None,
    settings: PlatformSettings | None = None,
) -> tuple[InteractionsService, InMemoryInteractionsRepo, WorkspacesServiceStub, RecordingProducer]:
    repository = repo or InMemoryInteractionsRepo()
    workspaces = workspaces_service or WorkspacesServiceStub()
    event_producer = producer or RecordingProducer()
    service = InteractionsService(
        repository=repository,  # type: ignore[arg-type]
        settings=settings or PlatformSettings(),
        producer=event_producer,  # type: ignore[arg-type]
        workspaces_service=workspaces,  # type: ignore[arg-type]
        registry_service=None,
    )
    return service, repository, workspaces, event_producer


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _ScalarsResult:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def scalars(self) -> _ScalarsResult:
        return self

    def all(self) -> list[Any]:
        return list(self.values)


class SessionStub:
    def __init__(
        self,
        *,
        execute_results: list[Any] | None = None,
        scalar_results: list[Any] | None = None,
    ) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added: list[Any] = []
        self.flush_count = 0

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = _now()
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = obj.created_at
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, query: Any) -> Any:
        del query
        return self.execute_results.pop(0)

    async def scalar(self, query: Any) -> Any:
        del query
        return self.scalar_results.pop(0)


def build_repository(session: SessionStub) -> InteractionsRepository:
    return InteractionsRepository(session)  # type: ignore[arg-type]


def make_current_user(workspace_id: UUID, user_id: UUID) -> dict[str, str]:
    return {"sub": str(user_id), "workspace_id": str(workspace_id)}
