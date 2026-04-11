from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.interactions.events import (
    AttentionRequestedPayload,
    BranchMergedPayload,
    GoalMessagePostedPayload,
    InteractionCanceledPayload,
    InteractionCompletedPayload,
    InteractionFailedPayload,
    InteractionStartedPayload,
    MessageReceivedPayload,
    publish_attention_requested,
    publish_branch_merged,
    publish_goal_message_posted,
    publish_interaction_canceled,
    publish_interaction_completed,
    publish_interaction_failed,
    publish_interaction_started,
    publish_message_received,
)
from platform.interactions.exceptions import (
    AttentionRequestNotFoundError,
    BranchNotFoundError,
    ConversationNotFoundError,
    GoalNotAcceptingMessagesError,
    InteractionNotAcceptingMessagesError,
    InteractionNotFoundError,
    InvalidStateTransitionError,
    MessageLimitReachedError,
)
from platform.interactions.models import (
    AttentionStatus,
    BranchStatus,
    Conversation,
    ConversationBranch,
    Interaction,
    InteractionParticipant,
    InteractionState,
    MessageType,
    ParticipantRole,
)
from platform.interactions.repository import InteractionsRepository
from platform.interactions.schemas import (
    AttentionRequestCreate,
    AttentionRequestListResponse,
    AttentionRequestResponse,
    AttentionResolve,
    BranchCreate,
    BranchMerge,
    BranchResponse,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    GoalMessageCreate,
    GoalMessageListResponse,
    GoalMessageResponse,
    InteractionCreate,
    InteractionListResponse,
    InteractionResponse,
    InteractionTransition,
    MergeRecordResponse,
    MessageCreate,
    MessageInject,
    MessageListResponse,
    MessageResponse,
    ParticipantAdd,
    ParticipantResponse,
)
from platform.interactions.state_machine import validate_transition
from platform.workspaces.models import GoalStatus
from typing import Any
from uuid import UUID, uuid4


class InteractionsService:
    def __init__(
        self,
        *,
        repository: InteractionsRepository,
        settings: Any,
        producer: Any | None,
        workspaces_service: Any | None,
        registry_service: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.workspaces_service = workspaces_service
        self.registry_service = registry_service

    async def create_conversation(
        self,
        request: ConversationCreate,
        created_by: str,
        workspace_id: UUID,
    ) -> ConversationResponse:
        conversation = await self.repository.create_conversation(
            workspace_id=workspace_id,
            title=request.title,
            created_by=created_by,
            metadata=request.metadata,
        )
        return self._conversation_response(conversation)

    async def get_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
    ) -> ConversationResponse:
        conversation = await self.repository.get_conversation(conversation_id, workspace_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return self._conversation_response(conversation)

    async def list_conversations(
        self,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> ConversationListResponse:
        items, total = await self.repository.list_conversations(workspace_id, page, page_size)
        return self._conversation_page(items, total, page, page_size)

    async def update_conversation(
        self,
        conversation_id: UUID,
        request: ConversationUpdate,
        workspace_id: UUID,
    ) -> ConversationResponse:
        conversation = await self.repository.get_conversation(conversation_id, workspace_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        updated = await self.repository.update_conversation(
            conversation,
            title=request.title if "title" in request.model_fields_set else None,
            metadata=request.metadata if "metadata" in request.model_fields_set else None,
        )
        return self._conversation_response(updated)

    async def delete_conversation(self, conversation_id: UUID, workspace_id: UUID) -> None:
        conversation = await self.repository.get_conversation(conversation_id, workspace_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        await self.repository.soft_delete_conversation(conversation)

    async def create_interaction(
        self,
        request: InteractionCreate,
        created_by: str,
        workspace_id: UUID,
    ) -> InteractionResponse:
        conversation = await self.repository.get_conversation(request.conversation_id, workspace_id)
        if conversation is None:
            raise ConversationNotFoundError(request.conversation_id)
        interaction = await self.repository.create_interaction(
            conversation_id=conversation.id,
            workspace_id=workspace_id,
            goal_id=request.goal_id,
        )
        await self.repository.add_participant(
            interaction_id=interaction.id,
            identity=created_by,
            role=ParticipantRole.initiator,
        )
        return self._interaction_response(interaction)

    async def get_interaction(
        self,
        interaction_id: UUID,
        workspace_id: UUID,
    ) -> InteractionResponse:
        interaction = await self.repository.get_interaction(interaction_id, workspace_id)
        if interaction is None:
            raise InteractionNotFoundError(interaction_id)
        return self._interaction_response(interaction)

    async def list_interactions(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
        state: InteractionState | None = None,
    ) -> InteractionListResponse:
        conversation = await self.repository.get_conversation(conversation_id, workspace_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        items, total = await self.repository.list_interactions(
            conversation_id,
            workspace_id,
            page,
            page_size,
            state,
        )
        return self._interaction_page(items, total, page, page_size)

    async def transition_interaction(
        self,
        interaction_id: UUID,
        transition: InteractionTransition,
        workspace_id: UUID,
    ) -> InteractionResponse:
        interaction = await self.repository.get_interaction(interaction_id, workspace_id)
        if interaction is None:
            raise InteractionNotFoundError(interaction_id)
        next_state = validate_transition(interaction.state, transition.trigger)
        now = datetime.now(UTC)
        started_at = interaction.started_at
        completed_at = interaction.completed_at
        if transition.trigger == "start" and started_at is None:
            started_at = now
        if next_state in {
            InteractionState.completed,
            InteractionState.failed,
            InteractionState.canceled,
        }:
            completed_at = now
        updated = await self.repository.transition_interaction_state(
            interaction_id=interaction.id,
            workspace_id=workspace_id,
            expected_state=interaction.state,
            new_state=next_state,
            error_metadata=transition.error_metadata,
            started_at=started_at,
            completed_at=completed_at,
        )
        if updated is None:
            actual = await self.repository.get_interaction(interaction_id, workspace_id)
            current = actual.state.value if actual is not None else interaction.state.value
            raise InvalidStateTransitionError(current, transition.trigger)
        correlation = self._correlation(
            workspace_id=workspace_id,
            conversation_id=updated.conversation_id,
            interaction_id=updated.id,
            goal_id=updated.goal_id,
        )
        initiator = await self.repository.get_initiator_identity(updated.id) or "unknown"
        if transition.trigger == "start":
            await publish_interaction_started(
                self.producer,
                InteractionStartedPayload(
                    interaction_id=updated.id,
                    conversation_id=updated.conversation_id,
                    workspace_id=updated.workspace_id,
                    goal_id=updated.goal_id,
                    created_by=initiator,
                ),
                correlation,
            )
        elif transition.trigger == "complete":
            await publish_interaction_completed(
                self.producer,
                InteractionCompletedPayload(
                    interaction_id=updated.id,
                    conversation_id=updated.conversation_id,
                    workspace_id=updated.workspace_id,
                    duration_seconds=self._duration_seconds(updated),
                ),
                correlation,
            )
        elif transition.trigger == "fail":
            await publish_interaction_failed(
                self.producer,
                InteractionFailedPayload(
                    interaction_id=updated.id,
                    conversation_id=updated.conversation_id,
                    workspace_id=updated.workspace_id,
                    error_metadata=transition.error_metadata or {},
                ),
                correlation,
            )
        elif transition.trigger == "cancel":
            await publish_interaction_canceled(
                self.producer,
                InteractionCanceledPayload(
                    interaction_id=updated.id,
                    conversation_id=updated.conversation_id,
                    workspace_id=updated.workspace_id,
                ),
                correlation,
            )
        return self._interaction_response(updated)

    async def send_message(
        self,
        interaction_id: UUID,
        message: MessageCreate,
        sender: str,
        workspace_id: UUID,
    ) -> MessageResponse:
        interaction = await self._require_interaction(interaction_id, workspace_id)
        if interaction.state not in {InteractionState.running, InteractionState.waiting}:
            raise InteractionNotAcceptingMessagesError(interaction_id, interaction.state.value)
        await self.repository.validate_parent_message(
            interaction_id=interaction.id,
            parent_message_id=message.parent_message_id,
        )
        limit = int(self.settings.interactions.max_messages_per_conversation)
        incremented = await self.repository.increment_message_count(
            conversation_id=interaction.conversation_id,
            workspace_id=workspace_id,
            limit=limit,
        )
        if incremented is None:
            raise MessageLimitReachedError(limit)
        created = await self.repository.create_message(
            interaction_id=interaction.id,
            parent_message_id=message.parent_message_id,
            sender_identity=sender,
            message_type=message.message_type,
            content=message.content,
            metadata=message.metadata,
        )
        await publish_message_received(
            self.producer,
            MessageReceivedPayload(
                message_id=created.id,
                interaction_id=interaction.id,
                conversation_id=interaction.conversation_id,
                workspace_id=workspace_id,
                sender_identity=sender,
                message_type=created.message_type,
            ),
            self._correlation(
                workspace_id=workspace_id,
                conversation_id=interaction.conversation_id,
                interaction_id=interaction.id,
                goal_id=interaction.goal_id,
            ),
        )
        return self._message_response(created)

    async def inject_message(
        self,
        interaction_id: UUID,
        injection: MessageInject,
        sender: str,
        workspace_id: UUID,
    ) -> MessageResponse:
        interaction = await self._require_interaction(interaction_id, workspace_id)
        if interaction.state != InteractionState.running:
            raise InteractionNotAcceptingMessagesError(interaction_id, interaction.state.value)
        latest_agent = await self.repository.get_latest_agent_message(interaction_id)
        return await self.send_message(
            interaction_id,
            MessageCreate(
                content=injection.content,
                parent_message_id=latest_agent.id if latest_agent is not None else None,
                message_type=MessageType.injection,
                metadata=injection.metadata,
            ),
            sender,
            workspace_id,
        )

    async def list_messages(
        self,
        interaction_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> MessageListResponse:
        await self._require_interaction(interaction_id, workspace_id)
        items, total = await self.repository.list_messages(interaction_id, page, page_size)
        return self._message_page(items, total, page, page_size)

    async def add_participant(
        self,
        interaction_id: UUID,
        participant: ParticipantAdd,
        workspace_id: UUID,
    ) -> ParticipantResponse:
        await self._require_interaction(interaction_id, workspace_id)
        created = await self.repository.add_participant(
            interaction_id=interaction_id,
            identity=participant.identity,
            role=participant.role,
        )
        return self._participant_response(created)

    async def remove_participant(
        self,
        interaction_id: UUID,
        identity: str,
        workspace_id: UUID,
    ) -> None:
        await self._require_interaction(interaction_id, workspace_id)
        participant = await self.repository.get_participant(interaction_id, identity)
        if participant is None:
            return
        await self.repository.remove_participant(participant)

    async def list_participants(
        self,
        interaction_id: UUID,
        workspace_id: UUID,
    ) -> list[ParticipantResponse]:
        await self._require_interaction(interaction_id, workspace_id)
        items = await self.repository.list_participants(interaction_id)
        return [self._participant_response(item) for item in items]

    async def post_goal_message(
        self,
        goal_id: UUID,
        message: GoalMessageCreate,
        participant: str,
        workspace_id: UUID,
    ) -> GoalMessageResponse:
        await self._require_goal_accepting_messages(goal_id, participant, workspace_id)
        created = await self.repository.create_goal_message(
            workspace_id=workspace_id,
            goal_id=goal_id,
            participant_identity=participant,
            content=message.content,
            interaction_id=message.interaction_id,
            metadata=message.metadata,
        )
        await publish_goal_message_posted(
            self.producer,
            GoalMessagePostedPayload(
                message_id=created.id,
                goal_id=goal_id,
                workspace_id=workspace_id,
                participant_identity=participant,
                interaction_id=message.interaction_id,
            ),
            self._correlation(workspace_id=workspace_id, goal_id=goal_id),
        )
        return self._goal_message_response(created)

    async def list_goal_messages(
        self,
        goal_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> GoalMessageListResponse:
        items, total = await self.repository.list_goal_messages(
            workspace_id=workspace_id,
            goal_id=goal_id,
            page=page,
            page_size=page_size,
        )
        return self._goal_message_page(items, total, page, page_size)

    async def get_goal_messages(
        self,
        workspace_id: UUID,
        goal_id: UUID,
        limit: int = 100,
    ) -> list[GoalMessageResponse]:
        items = await self.repository.get_goal_messages_for_context(
            workspace_id=workspace_id,
            goal_id=goal_id,
            limit=limit,
        )
        return [self._goal_message_response(item) for item in items]

    async def create_branch(
        self,
        request: BranchCreate,
        workspace_id: UUID,
    ) -> BranchResponse:
        parent = await self._require_interaction(request.parent_interaction_id, workspace_id)
        await self.repository.validate_parent_message(
            interaction_id=parent.id,
            parent_message_id=request.branch_point_message_id,
        )
        branch_state = (
            parent.state
            if parent.state
            in {
                InteractionState.running,
                InteractionState.waiting,
                InteractionState.paused,
            }
            else InteractionState.ready
        )
        branch_interaction = await self.repository.create_interaction(
            conversation_id=parent.conversation_id,
            workspace_id=workspace_id,
            goal_id=parent.goal_id,
            state=branch_state,
            started_at=parent.started_at if branch_state == InteractionState.running else None,
        )
        participants = await self.repository.list_participants(parent.id)
        for item in participants:
            await self.repository.add_participant(
                interaction_id=branch_interaction.id,
                identity=item.identity,
                role=item.role,
                joined_at=item.joined_at,
            )
        await self.repository.copy_messages_up_to(
            parent_interaction_id=parent.id,
            branch_interaction_id=branch_interaction.id,
            branch_point_message_id=request.branch_point_message_id,
        )
        copied_messages = await self.repository.list_messages_for_context(
            branch_interaction.id,
            10_000,
        )
        await self.repository.adjust_message_count(
            conversation_id=parent.conversation_id,
            workspace_id=workspace_id,
            delta=len(copied_messages),
        )
        branch = await self.repository.create_branch(
            conversation_id=parent.conversation_id,
            parent_interaction_id=parent.id,
            branch_interaction_id=branch_interaction.id,
            branch_point_message_id=request.branch_point_message_id,
        )
        return self._branch_response(branch)

    async def merge_branch(
        self,
        branch_id: UUID,
        merge: BranchMerge,
        merged_by: str,
        workspace_id: UUID,
    ) -> MergeRecordResponse:
        branch = await self.repository.get_branch(branch_id, workspace_id)
        if branch is None:
            raise BranchNotFoundError(branch_id)
        conflict_detected = await self.repository.check_prior_merges_from_same_point(branch)
        latest_parent_message = await self.repository.get_latest_message(
            branch.parent_interaction_id
        )
        merged_count = await self.repository.merge_branch_messages(
            branch=branch,
            merge_anchor_id=latest_parent_message.id if latest_parent_message is not None else None,
        )
        if merged_count:
            await self.repository.adjust_message_count(
                conversation_id=branch.conversation_id,
                workspace_id=workspace_id,
                delta=merged_count,
            )
        record = await self.repository.create_merge_record(
            branch_id=branch.id,
            merged_by=merged_by,
            conflict_detected=conflict_detected,
            conflict_resolution=merge.conflict_resolution,
            messages_merged_count=merged_count,
        )
        await self.repository.update_branch_status(branch, BranchStatus.merged)
        parent = await self._require_interaction(branch.parent_interaction_id, workspace_id)
        await publish_branch_merged(
            self.producer,
            BranchMergedPayload(
                branch_id=branch.id,
                parent_interaction_id=branch.parent_interaction_id,
                branch_interaction_id=branch.branch_interaction_id,
                conversation_id=branch.conversation_id,
                workspace_id=workspace_id,
                conflict_detected=conflict_detected,
            ),
            self._correlation(
                workspace_id=workspace_id,
                conversation_id=branch.conversation_id,
                interaction_id=parent.id,
                goal_id=parent.goal_id,
            ),
        )
        return self._merge_record_response(record)

    async def abandon_branch(
        self,
        branch_id: UUID,
        workspace_id: UUID,
    ) -> BranchResponse:
        branch = await self.repository.get_branch(branch_id, workspace_id)
        if branch is None:
            raise BranchNotFoundError(branch_id)
        updated = await self.repository.update_branch_status(branch, BranchStatus.abandoned)
        return self._branch_response(updated)

    async def list_branches(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
    ) -> list[BranchResponse]:
        await self.get_conversation(conversation_id, workspace_id)
        items = await self.repository.list_branches(conversation_id, workspace_id)
        return [self._branch_response(item) for item in items]

    async def create_attention_request(
        self,
        request: AttentionRequestCreate,
        source_agent_fqn: str,
        workspace_id: UUID,
    ) -> AttentionRequestResponse:
        if request.related_interaction_id is not None:
            await self._require_interaction(request.related_interaction_id, workspace_id)
        created = await self.repository.create_attention_request(
            workspace_id=workspace_id,
            source_agent_fqn=source_agent_fqn,
            target_identity=request.target_identity,
            urgency=request.urgency,
            context_summary=request.context_summary,
            related_execution_id=request.related_execution_id,
            related_interaction_id=request.related_interaction_id,
            related_goal_id=request.related_goal_id,
        )
        await publish_attention_requested(
            self.producer,
            AttentionRequestedPayload(
                request_id=created.id,
                workspace_id=workspace_id,
                source_agent_fqn=created.source_agent_fqn,
                target_identity=created.target_identity,
                urgency=created.urgency,
                related_interaction_id=created.related_interaction_id,
                related_goal_id=created.related_goal_id,
            ),
            self._correlation(
                workspace_id=workspace_id,
                interaction_id=created.related_interaction_id,
                goal_id=created.related_goal_id,
                execution_id=created.related_execution_id,
            ),
        )
        return self._attention_response(created)

    async def list_attention_requests(
        self,
        target_identity: str,
        workspace_id: UUID,
        status: AttentionStatus | None,
        page: int,
        page_size: int,
    ) -> AttentionRequestListResponse:
        items, total = await self.repository.list_attention_requests(
            workspace_id=workspace_id,
            target_identity=target_identity,
            status=status,
            page=page,
            page_size=page_size,
        )
        return self._attention_page(items, total, page, page_size)

    async def resolve_attention_request(
        self,
        request_id: UUID,
        action: AttentionResolve,
        workspace_id: UUID,
        requester_identity: str | None = None,
    ) -> AttentionRequestResponse:
        request = await self.repository.get_attention_request(request_id, workspace_id)
        if request is None:
            raise AttentionRequestNotFoundError(request_id)
        if requester_identity is not None and requester_identity != request.target_identity:
            raise AuthorizationError(
                "ATTENTION_NOT_TARGET",
                "Attention request can only be resolved by its target",
            )
        now = datetime.now(UTC)
        acknowledged_at = request.acknowledged_at
        resolved_at = request.resolved_at
        if action.action == "acknowledge":
            if request.status != AttentionStatus.pending:
                raise ValidationError(
                    "ATTENTION_INVALID_TRANSITION",
                    "Attention request cannot be acknowledged",
                )
            next_status = AttentionStatus.acknowledged
            acknowledged_at = now
        elif action.action == "resolve":
            if request.status not in {AttentionStatus.pending, AttentionStatus.acknowledged}:
                raise ValidationError(
                    "ATTENTION_INVALID_TRANSITION",
                    "Attention request cannot be resolved",
                )
            next_status = AttentionStatus.resolved
            acknowledged_at = acknowledged_at or now
            resolved_at = now
        else:
            if request.status not in {AttentionStatus.pending, AttentionStatus.acknowledged}:
                raise ValidationError(
                    "ATTENTION_INVALID_TRANSITION",
                    "Attention request cannot be dismissed",
                )
            next_status = AttentionStatus.dismissed
            acknowledged_at = acknowledged_at or now
            resolved_at = now
        updated = await self.repository.update_attention_status(
            request,
            status=next_status,
            acknowledged_at=acknowledged_at,
            resolved_at=resolved_at,
        )
        return self._attention_response(updated)

    async def get_conversation_history(
        self,
        interaction_id: UUID,
        step_id: UUID | None = None,
        limit: int = 50,
    ) -> list[MessageResponse]:
        resolved_interaction_id = step_id if step_id is not None else interaction_id
        items = await self.repository.list_messages_for_context(resolved_interaction_id, limit)
        return [self._message_response(item) for item in items]

    async def list_conversation_history(
        self,
        execution_id: UUID,
        step_id: UUID,
        *,
        limit: int,
    ) -> list[MessageResponse]:
        return await self.get_conversation_history(execution_id, step_id, limit=limit)

    async def check_subscription_access(
        self,
        user_id: str,
        channel_type: str,
        channel_id: UUID,
        workspace_id: UUID,
    ) -> bool:
        if self.workspaces_service is None:
            return False
        try:
            parsed_user_id = UUID(str(user_id))
        except ValueError:
            return False
        workspace_ids = await self.workspaces_service.get_user_workspace_ids(parsed_user_id)
        if workspace_id not in {UUID(str(item)) for item in workspace_ids}:
            return False
        if channel_type == "conversation":
            return await self.repository.get_conversation(channel_id, workspace_id) is not None
        if channel_type == "interaction":
            return await self.repository.get_interaction(channel_id, workspace_id) is not None
        if channel_type == "attention":
            return str(channel_id) == str(parsed_user_id)
        return False

    async def _require_interaction(self, interaction_id: UUID, workspace_id: UUID) -> Interaction:
        interaction = await self.repository.get_interaction(interaction_id, workspace_id)
        if interaction is None:
            raise InteractionNotFoundError(interaction_id)
        return interaction

    async def _require_goal_accepting_messages(
        self,
        goal_id: UUID,
        participant: str,
        workspace_id: UUID,
    ) -> Any:
        if self.workspaces_service is None:
            raise GoalNotAcceptingMessagesError(goal_id, "unknown")
        goal: Any | None = None
        try:
            requester_id = UUID(str(participant))
        except ValueError:
            requester_id = None
        if requester_id is not None and hasattr(self.workspaces_service, "get_goal"):
            goal = await self.workspaces_service.get_goal(workspace_id, requester_id, goal_id)
        else:
            repo = getattr(self.workspaces_service, "repo", None)
            if repo is not None and hasattr(repo, "get_goal"):
                goal = await repo.get_goal(workspace_id, goal_id)
        if goal is None:
            raise GoalNotAcceptingMessagesError(goal_id, "missing")
        status = getattr(goal, "status", None)
        status_value = getattr(status, "value", status)
        if status_value in {GoalStatus.completed.value, GoalStatus.cancelled.value, "abandoned"}:
            raise GoalNotAcceptingMessagesError(goal_id, str(status_value))
        return goal

    @staticmethod
    def _duration_seconds(interaction: Interaction) -> float:
        started_at = interaction.started_at or interaction.created_at
        finished_at = interaction.completed_at or datetime.now(UTC)
        return max(0.0, (finished_at - started_at).total_seconds())

    @staticmethod
    def _conversation_response(conversation: Conversation) -> ConversationResponse:
        return ConversationResponse(
            id=conversation.id,
            workspace_id=conversation.workspace_id,
            title=conversation.title,
            created_by=conversation.created_by,
            metadata=dict(conversation.metadata_json),
            message_count=conversation.message_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def _interaction_response(interaction: Interaction) -> InteractionResponse:
        return InteractionResponse(
            id=interaction.id,
            conversation_id=interaction.conversation_id,
            workspace_id=interaction.workspace_id,
            goal_id=interaction.goal_id,
            state=interaction.state,
            state_changed_at=interaction.state_changed_at,
            error_metadata=interaction.error_metadata,
            started_at=interaction.started_at,
            completed_at=interaction.completed_at,
            created_at=interaction.created_at,
        )

    @staticmethod
    def _message_response(message: Any) -> MessageResponse:
        return MessageResponse(
            id=message.id,
            interaction_id=message.interaction_id,
            parent_message_id=message.parent_message_id,
            sender_identity=message.sender_identity,
            message_type=message.message_type,
            content=message.content,
            metadata=dict(getattr(message, "metadata_json", {})),
            created_at=message.created_at,
        )

    @staticmethod
    def _participant_response(participant: InteractionParticipant) -> ParticipantResponse:
        return ParticipantResponse(
            id=participant.id,
            interaction_id=participant.interaction_id,
            identity=participant.identity,
            role=participant.role,
            joined_at=participant.joined_at,
            left_at=participant.left_at,
        )

    @staticmethod
    def _goal_message_response(message: Any) -> GoalMessageResponse:
        return GoalMessageResponse(
            id=message.id,
            workspace_id=message.workspace_id,
            goal_id=message.goal_id,
            participant_identity=message.participant_identity,
            content=message.content,
            interaction_id=message.interaction_id,
            metadata=dict(getattr(message, "metadata_json", {})),
            created_at=message.created_at,
        )

    @staticmethod
    def _branch_response(branch: ConversationBranch) -> BranchResponse:
        return BranchResponse(
            id=branch.id,
            conversation_id=branch.conversation_id,
            parent_interaction_id=branch.parent_interaction_id,
            branch_interaction_id=branch.branch_interaction_id,
            branch_point_message_id=branch.branch_point_message_id,
            status=branch.status,
            created_at=branch.created_at,
        )

    @staticmethod
    def _merge_record_response(record: Any) -> MergeRecordResponse:
        return MergeRecordResponse(
            id=record.id,
            branch_id=record.branch_id,
            merged_by=record.merged_by,
            conflict_detected=record.conflict_detected,
            conflict_resolution=record.conflict_resolution,
            messages_merged_count=record.messages_merged_count,
            created_at=record.created_at,
        )

    @staticmethod
    def _attention_response(request: Any) -> AttentionRequestResponse:
        return AttentionRequestResponse(
            id=request.id,
            workspace_id=request.workspace_id,
            source_agent_fqn=request.source_agent_fqn,
            target_identity=request.target_identity,
            urgency=request.urgency,
            context_summary=request.context_summary,
            related_execution_id=request.related_execution_id,
            related_interaction_id=request.related_interaction_id,
            related_goal_id=request.related_goal_id,
            status=request.status,
            acknowledged_at=request.acknowledged_at,
            resolved_at=request.resolved_at,
            created_at=request.created_at,
        )

    @staticmethod
    def _page_meta(total: int, page: int, page_size: int) -> dict[str, int | bool]:
        total_pages = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        }

    def _conversation_page(
        self,
        items: list[Conversation],
        total: int,
        page: int,
        page_size: int,
    ) -> ConversationListResponse:
        return ConversationListResponse(
            items=[self._conversation_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

    def _interaction_page(
        self,
        items: list[Interaction],
        total: int,
        page: int,
        page_size: int,
    ) -> InteractionListResponse:
        return InteractionListResponse(
            items=[self._interaction_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

    def _message_page(
        self,
        items: list[Any],
        total: int,
        page: int,
        page_size: int,
    ) -> MessageListResponse:
        return MessageListResponse(
            items=[self._message_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

    def _goal_message_page(
        self,
        items: list[Any],
        total: int,
        page: int,
        page_size: int,
    ) -> GoalMessageListResponse:
        return GoalMessageListResponse(
            items=[self._goal_message_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

    def _attention_page(
        self,
        items: list[Any],
        total: int,
        page: int,
        page_size: int,
    ) -> AttentionRequestListResponse:
        return AttentionRequestListResponse(
            items=[self._attention_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

    @staticmethod
    def _correlation(
        *,
        workspace_id: UUID | None = None,
        conversation_id: UUID | None = None,
        interaction_id: UUID | None = None,
        execution_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            execution_id=execution_id,
            goal_id=goal_id,
        )
