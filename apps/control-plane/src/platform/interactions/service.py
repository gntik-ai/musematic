from __future__ import annotations

import logging
from datetime import UTC, datetime
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
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
from platform.interactions.goal_lifecycle import GoalLifecycleService
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
from platform.interactions.response_decision import ResponseDecisionEngine
from platform.interactions.schemas import (
    AgentDecisionConfigListResponse,
    AgentDecisionConfigResponse,
    AgentDecisionConfigUpsert,
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
    DecisionRationaleListResponse,
    DecisionRationaleMessageListResponse,
    DecisionRationaleResponse,
    GoalMessageCreate,
    GoalMessageListResponse,
    GoalMessageResponse,
    GoalStateTransitionRequest,
    GoalStateTransitionResponse,
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
from platform.registry.service import fqn_matches
from platform.workspaces.exceptions import GoalNotFoundError
from platform.workspaces.models import (
    GoalStatus,
    WorkspaceAgentDecisionConfig,
    WorkspaceGoalState,
)
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = logging.getLogger(__name__)


class InteractionsService:
    def __init__(
        self,
        *,
        repository: InteractionsRepository,
        settings: Any,
        producer: Any | None,
        qdrant: AsyncQdrantClient | None = None,
        workspaces_service: Any | None,
        registry_service: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.qdrant = qdrant
        self.workspaces_service = workspaces_service
        self.registry_service = registry_service
        self.goal_lifecycle = GoalLifecycleService(producer)
        self.decision_engine = ResponseDecisionEngine(settings=settings, qdrant=qdrant)

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
        requesting_agent_id: UUID | None = None,
    ) -> ParticipantResponse:
        await self._require_interaction(interaction_id, workspace_id)
        if (
            self.settings.visibility.zero_trust_enabled
            and requesting_agent_id is not None
            and self.registry_service is not None
            and hasattr(self.registry_service, "resolve_effective_visibility")
        ):
            effective_visibility = await self.registry_service.resolve_effective_visibility(
                requesting_agent_id,
                workspace_id,
            )
            if not any(
                fqn_matches(pattern, participant.identity)
                for pattern in getattr(effective_visibility, "agent_patterns", [])
            ):
                raise InteractionNotFoundError(interaction_id)
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
        goal = await self._require_goal_accepting_messages(goal_id, participant, workspace_id)
        if getattr(goal, "state", WorkspaceGoalState.ready) == WorkspaceGoalState.ready:
            await self.goal_lifecycle.transition_ready_to_working(
                goal,
                self._goal_lifecycle_session(),
            )
        created = await self.repository.create_goal_message(
            workspace_id=workspace_id,
            goal_id=goal_id,
            participant_identity=participant,
            content=message.content,
            interaction_id=message.interaction_id,
            metadata=message.metadata,
        )
        self.goal_lifecycle.update_last_message_at(goal, datetime.now(UTC))
        await self._flush_repository_session()

        subscriptions = await self._list_workspace_agent_decision_configs(workspace_id)
        if subscriptions:
            try:
                session = self._repository_session()
                if session is not None:
                    goal_context = "\n".join(
                        part for part in [goal.title, goal.description or ""] if part
                    )
                    await self.decision_engine.evaluate_for_message(
                        message_id=created.id,
                        goal_id=goal_id,
                        workspace_id=workspace_id,
                        message_content=message.content,
                        goal_context=goal_context,
                        subscriptions=subscriptions,
                        session=session,
                    )
                else:
                    LOGGER.warning(
                        (
                            "Skipping response decision evaluation for goal %s: "
                            "repository session unavailable"
                        ),
                        goal_id,
                    )
            except Exception as exc:
                LOGGER.warning(
                    "Response decision evaluation failed for goal %s message %s: %s",
                    goal_id,
                    created.id,
                    exc,
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

    async def transition_goal_state(
        self,
        goal_id: UUID,
        request: GoalStateTransitionRequest,
        workspace_id: UUID,
    ) -> GoalStateTransitionResponse:
        goal = await self._load_goal(workspace_id, goal_id, for_update=True)
        if goal is None:
            raise GoalNotFoundError()
        previous_state = getattr(goal.state, "value", str(goal.state))
        await self.goal_lifecycle.transition_working_to_complete(
            goal,
            self._goal_lifecycle_session(),
            automatic=False,
            reason=request.reason,
        )
        await self._flush_repository_session()
        transitioned_at = datetime.now(UTC)
        return GoalStateTransitionResponse(
            goal_id=goal.id,
            previous_state=previous_state,
            new_state=goal.state.value,
            automatic=False,
            transitioned_at=transitioned_at,
        )

    async def upsert_agent_decision_config(
        self,
        workspace_id: UUID,
        agent_fqn: str,
        request: AgentDecisionConfigUpsert,
        actor_id: UUID | None,
    ) -> tuple[AgentDecisionConfigResponse, bool]:
        if not self.decision_engine.is_known_strategy(request.response_decision_strategy):
            raise ValidationError(
                "UNKNOWN_RESPONSE_DECISION_STRATEGY",
                f"Unknown response decision strategy '{request.response_decision_strategy}'",
            )
        subscribed_patterns = await self._get_subscribed_agent_patterns(workspace_id, actor_id)
        if not any(fqn_matches(pattern, agent_fqn) for pattern in subscribed_patterns):
            raise NotFoundError(
                "WORKSPACE_AGENT_NOT_SUBSCRIBED",
                f"Agent '{agent_fqn}' is not subscribed to workspace '{workspace_id}'",
            )
        item, created = await self.repository.upsert_workspace_agent_decision_config(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            response_decision_strategy=request.response_decision_strategy,
            response_decision_config=request.response_decision_config,
        )
        return self._agent_decision_config_response(item), created

    async def list_agent_decision_configs(
        self,
        workspace_id: UUID,
        actor_id: UUID | None,
    ) -> AgentDecisionConfigListResponse:
        await self._get_subscribed_agent_patterns(workspace_id, actor_id)
        items = await self.repository.list_workspace_agent_decision_configs(
            workspace_id=workspace_id,
        )
        return AgentDecisionConfigListResponse(
            items=[self._agent_decision_config_response(item) for item in items],
            total=len(items),
        )

    async def list_rationale_for_message(
        self,
        goal_id: UUID,
        message_id: UUID,
        workspace_id: UUID,
    ) -> DecisionRationaleMessageListResponse:
        message = await self.repository.get_goal_message(
            workspace_id=workspace_id,
            goal_id=goal_id,
            message_id=message_id,
        )
        if message is None:
            raise NotFoundError(
                "GOAL_MESSAGE_NOT_FOUND",
                f"Goal message '{message_id}' was not found",
            )
        items = await self.repository.list_decision_rationales_for_message(
            workspace_id=workspace_id,
            message_id=message_id,
        )
        return DecisionRationaleMessageListResponse(
            items=[self._decision_rationale_response(item) for item in items],
            total=len(items),
        )

    async def list_rationale_for_goal(
        self,
        goal_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
        agent_fqn: str | None = None,
        decision: str | None = None,
    ) -> DecisionRationaleListResponse:
        goal = await self._load_goal(workspace_id, goal_id, for_update=False)
        if goal is None:
            raise GoalNotFoundError()
        items, total = await self.repository.list_decision_rationales_for_goal(
            workspace_id=workspace_id,
            goal_id=goal_id,
            page=page,
            page_size=page_size,
            agent_fqn=agent_fqn,
            decision=decision,
        )
        return DecisionRationaleListResponse(
            items=[self._decision_rationale_response(item) for item in items],
            **self._page_meta(total, page, page_size),
        )

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
        goal = await self._load_goal(
            workspace_id,
            goal_id,
            participant=participant,
            for_update=True,
            require_membership=True,
        )
        if goal is None:
            raise GoalNotAcceptingMessagesError(goal_id, "missing")
        status = getattr(goal, "status", None)
        status_value = getattr(status, "value", status)
        if status_value in {GoalStatus.completed.value, GoalStatus.cancelled.value, "abandoned"}:
            raise GoalNotAcceptingMessagesError(goal_id, str(status_value))
        self.goal_lifecycle.assert_accepts_messages(goal)
        return goal

    async def _load_goal(
        self,
        workspace_id: UUID,
        goal_id: UUID,
        *,
        participant: str | None = None,
        requester_id: UUID | None = None,
        for_update: bool,
        require_membership: bool = False,
    ) -> Any | None:
        resolved_requester = requester_id
        if resolved_requester is None and participant is not None:
            try:
                resolved_requester = UUID(str(participant))
            except ValueError:
                resolved_requester = None
        if (
            require_membership
            and resolved_requester is not None
            and self.workspaces_service is not None
        ):
            getter = getattr(self.workspaces_service, "get_goal", None)
            if callable(getter):
                try:
                    await getter(workspace_id, resolved_requester, goal_id)
                except (LookupError, NotFoundError, ValidationError, AuthorizationError):
                    return None
        goal: Any | None = None
        getter_name = "get_goal_for_update" if for_update else None
        if getter_name is not None:
            repository_getter = getattr(self.repository, getter_name, None)
            if callable(repository_getter):
                goal = await repository_getter(workspace_id=workspace_id, goal_id=goal_id)
        if goal is None:
            workspace_repo = (
                getattr(self.workspaces_service, "repo", None)
                if self.workspaces_service is not None
                else None
            )
            workspace_getter = getattr(workspace_repo, "get_goal", None)
            if callable(workspace_getter):
                goal = await workspace_getter(workspace_id, goal_id)
        return goal

    def _repository_session(self) -> Any | None:
        return getattr(self.repository, "session", None)

    def _goal_lifecycle_session(self) -> AsyncSession | None:
        return cast(AsyncSession | None, self._repository_session())

    async def _flush_repository_session(self) -> None:
        session = self._repository_session()
        if session is not None and hasattr(session, "flush"):
            await session.flush()

    async def _get_subscribed_agent_patterns(
        self,
        workspace_id: UUID,
        actor_id: UUID | None,
    ) -> list[str]:
        if self.workspaces_service is None or actor_id is None:
            return []
        getter = getattr(self.workspaces_service, "get_settings", None)
        if getter is None:
            return []
        settings = await getter(workspace_id, actor_id)
        return list(getattr(settings, "subscribed_agents", []))

    async def _list_workspace_agent_decision_configs(
        self,
        workspace_id: UUID,
    ) -> list[WorkspaceAgentDecisionConfig]:
        list_configs = getattr(self.repository, "list_workspace_agent_decision_configs", None)
        if callable(list_configs):
            result = await list_configs(workspace_id=workspace_id)
            return cast(list[WorkspaceAgentDecisionConfig], result)
        return []

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
    def _agent_decision_config_response(item: Any) -> AgentDecisionConfigResponse:
        return AgentDecisionConfigResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            agent_fqn=item.agent_fqn,
            response_decision_strategy=item.response_decision_strategy,
            response_decision_config=dict(item.response_decision_config or {}),
            subscribed_at=item.subscribed_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _decision_rationale_response(item: Any) -> DecisionRationaleResponse:
        return DecisionRationaleResponse(
            id=item.id,
            goal_id=item.goal_id,
            message_id=item.message_id,
            agent_fqn=item.agent_fqn,
            strategy_name=item.strategy_name,
            decision=item.decision,
            score=item.score,
            matched_terms=list(item.matched_terms or []),
            rationale=item.rationale,
            error=item.error,
            created_at=item.created_at,
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
