from __future__ import annotations

from datetime import UTC, datetime
from platform.interactions.exceptions import MessageNotInInteractionError
from platform.interactions.models import (
    AttentionRequest,
    AttentionStatus,
    BranchMergeRecord,
    BranchStatus,
    Conversation,
    ConversationBranch,
    Interaction,
    InteractionMessage,
    InteractionParticipant,
    InteractionState,
    ParticipantRole,
    WorkspaceGoalMessage,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class InteractionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(
        self,
        *,
        workspace_id: UUID,
        title: str,
        created_by: str,
        metadata: dict[str, Any],
    ) -> Conversation:
        conversation = Conversation(
            workspace_id=workspace_id,
            title=title,
            created_by=created_by,
            metadata_json=dict(metadata),
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        filters = [
            Conversation.workspace_id == workspace_id,
            Conversation.deleted_at.is_(None),
        ]
        total = await self.session.scalar(
            select(func.count()).select_from(Conversation).where(*filters)
        )
        result = await self.session.execute(
            select(Conversation)
            .where(*filters)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def soft_delete_conversation(self, conversation: Conversation) -> Conversation:
        conversation.deleted_at = datetime.now(UTC)
        await self.session.flush()
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
        await self.session.flush()
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
        interaction = Interaction(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            goal_id=goal_id,
            state=state,
            state_changed_at=state_changed_at or datetime.now(UTC),
            started_at=started_at,
        )
        self.session.add(interaction)
        await self.session.flush()
        return interaction

    async def get_interaction(self, interaction_id: UUID, workspace_id: UUID) -> Interaction | None:
        result = await self.session.execute(
            select(Interaction)
            .join(Conversation, Conversation.id == Interaction.conversation_id)
            .where(
                Interaction.id == interaction_id,
                Interaction.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_interactions(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        page: int,
        page_size: int,
        state: InteractionState | None = None,
    ) -> tuple[list[Interaction], int]:
        filters = [
            Interaction.conversation_id == conversation_id,
            Interaction.workspace_id == workspace_id,
        ]
        if state is not None:
            filters.append(Interaction.state == state)
        total = await self.session.scalar(
            select(func.count()).select_from(Interaction).where(*filters)
        )
        result = await self.session.execute(
            select(Interaction)
            .where(*filters)
            .order_by(Interaction.created_at.asc(), Interaction.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

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
        values: dict[str, Any] = {
            "state": new_state,
            "state_changed_at": datetime.now(UTC),
            "error_metadata": error_metadata,
        }
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        result = await self.session.execute(
            update(Interaction)
            .where(
                Interaction.id == interaction_id,
                Interaction.workspace_id == workspace_id,
                Interaction.state == expected_state,
            )
            .values(**values)
            .returning(Interaction.id)
        )
        updated_id = result.scalar_one_or_none()
        if updated_id is None:
            return None
        await self.session.flush()
        return await self.get_interaction(interaction_id, workspace_id)

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
        message = InteractionMessage(
            interaction_id=interaction_id,
            parent_message_id=parent_message_id,
            sender_identity=sender_identity,
            message_type=message_type,
            content=content,
            metadata_json=dict(metadata),
        )
        if created_at is not None:
            message.created_at = created_at
            message.updated_at = created_at
        self.session.add(message)
        await self.session.flush()
        return message

    async def get_message(
        self,
        message_id: UUID,
        interaction_id: UUID | None = None,
    ) -> InteractionMessage | None:
        query = select(InteractionMessage).where(InteractionMessage.id == message_id)
        if interaction_id is not None:
            query = query.where(InteractionMessage.interaction_id == interaction_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_messages(
        self,
        interaction_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[InteractionMessage], int]:
        filters = [InteractionMessage.interaction_id == interaction_id]
        total = await self.session.scalar(
            select(func.count()).select_from(InteractionMessage).where(*filters)
        )
        result = await self.session.execute(
            select(InteractionMessage)
            .where(*filters)
            .order_by(InteractionMessage.created_at.asc(), InteractionMessage.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_messages_for_context(
        self,
        interaction_id: UUID,
        limit: int,
    ) -> list[InteractionMessage]:
        result = await self.session.execute(
            select(InteractionMessage)
            .where(InteractionMessage.interaction_id == interaction_id)
            .order_by(InteractionMessage.created_at.desc(), InteractionMessage.id.desc())
            .limit(limit)
        )
        items = list(result.scalars().all())
        return list(reversed(items))

    async def validate_parent_message(
        self,
        *,
        interaction_id: UUID,
        parent_message_id: UUID | None,
    ) -> InteractionMessage | None:
        if parent_message_id is None:
            return None
        parent = await self.get_message(parent_message_id)
        if parent is None or parent.interaction_id != interaction_id:
            raise MessageNotInInteractionError(parent_message_id, interaction_id)
        return parent

    async def increment_message_count(
        self,
        *,
        conversation_id: UUID,
        workspace_id: UUID,
        limit: int,
    ) -> int | None:
        # Single UPDATE + WHERE + RETURNING keeps the limit check race-free under concurrent writes.
        result = await self.session.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
                Conversation.message_count < limit,
            )
            .values(message_count=Conversation.message_count + 1)
            .returning(Conversation.message_count)
        )
        await self.session.flush()
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def adjust_message_count(
        self,
        *,
        conversation_id: UUID,
        workspace_id: UUID,
        delta: int,
    ) -> int | None:
        result = await self.session.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
            )
            .values(message_count=Conversation.message_count + delta)
            .returning(Conversation.message_count)
        )
        await self.session.flush()
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def get_latest_message(
        self,
        interaction_id: UUID,
    ) -> InteractionMessage | None:
        result = await self.session.execute(
            select(InteractionMessage)
            .where(InteractionMessage.interaction_id == interaction_id)
            .order_by(InteractionMessage.created_at.desc(), InteractionMessage.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_agent_message(self, interaction_id: UUID) -> InteractionMessage | None:
        result = await self.session.execute(
            select(InteractionMessage)
            .where(
                InteractionMessage.interaction_id == interaction_id,
                InteractionMessage.message_type == "agent",
            )
            .order_by(InteractionMessage.created_at.desc(), InteractionMessage.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_participant(
        self,
        *,
        interaction_id: UUID,
        identity: str,
        role: ParticipantRole,
        joined_at: datetime | None = None,
    ) -> InteractionParticipant:
        existing = await self.get_participant(interaction_id, identity)
        if existing is not None:
            existing.role = role
            existing.left_at = None
            if joined_at is not None:
                existing.joined_at = joined_at
            await self.session.flush()
            return existing
        participant = InteractionParticipant(
            interaction_id=interaction_id,
            identity=identity,
            role=role,
        )
        if joined_at is not None:
            participant.joined_at = joined_at
            participant.created_at = joined_at
            participant.updated_at = joined_at
        self.session.add(participant)
        await self.session.flush()
        return participant

    async def get_participant(
        self,
        interaction_id: UUID,
        identity: str,
    ) -> InteractionParticipant | None:
        result = await self.session.execute(
            select(InteractionParticipant).where(
                InteractionParticipant.interaction_id == interaction_id,
                InteractionParticipant.identity == identity,
            )
        )
        return result.scalar_one_or_none()

    async def remove_participant(
        self,
        participant: InteractionParticipant,
    ) -> InteractionParticipant:
        participant.left_at = datetime.now(UTC)
        await self.session.flush()
        return participant

    async def list_participants(self, interaction_id: UUID) -> list[InteractionParticipant]:
        result = await self.session.execute(
            select(InteractionParticipant)
            .where(InteractionParticipant.interaction_id == interaction_id)
            .order_by(InteractionParticipant.joined_at.asc(), InteractionParticipant.id.asc())
        )
        return list(result.scalars().all())

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
        message = WorkspaceGoalMessage(
            workspace_id=workspace_id,
            goal_id=goal_id,
            participant_identity=participant_identity,
            content=content,
            interaction_id=interaction_id,
            metadata_json=dict(metadata),
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_goal_messages(
        self,
        *,
        workspace_id: UUID,
        goal_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[WorkspaceGoalMessage], int]:
        filters = [
            WorkspaceGoalMessage.workspace_id == workspace_id,
            WorkspaceGoalMessage.goal_id == goal_id,
        ]
        total = await self.session.scalar(
            select(func.count()).select_from(WorkspaceGoalMessage).where(*filters)
        )
        result = await self.session.execute(
            select(WorkspaceGoalMessage)
            .where(*filters)
            .order_by(WorkspaceGoalMessage.created_at.asc(), WorkspaceGoalMessage.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_goal_messages_for_context(
        self,
        *,
        workspace_id: UUID,
        goal_id: UUID,
        limit: int,
    ) -> list[WorkspaceGoalMessage]:
        result = await self.session.execute(
            select(WorkspaceGoalMessage)
            .where(
                WorkspaceGoalMessage.workspace_id == workspace_id,
                WorkspaceGoalMessage.goal_id == goal_id,
            )
            .order_by(WorkspaceGoalMessage.created_at.desc(), WorkspaceGoalMessage.id.desc())
            .limit(limit)
        )
        items = list(result.scalars().all())
        return list(reversed(items))

    async def create_branch(
        self,
        *,
        conversation_id: UUID,
        parent_interaction_id: UUID,
        branch_interaction_id: UUID,
        branch_point_message_id: UUID,
    ) -> ConversationBranch:
        branch = ConversationBranch(
            conversation_id=conversation_id,
            parent_interaction_id=parent_interaction_id,
            branch_interaction_id=branch_interaction_id,
            branch_point_message_id=branch_point_message_id,
        )
        self.session.add(branch)
        await self.session.flush()
        return branch

    async def get_branch(self, branch_id: UUID, workspace_id: UUID) -> ConversationBranch | None:
        result = await self.session.execute(
            select(ConversationBranch)
            .join(Conversation, Conversation.id == ConversationBranch.conversation_id)
            .where(
                ConversationBranch.id == branch_id,
                Conversation.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_branches(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
    ) -> list[ConversationBranch]:
        result = await self.session.execute(
            select(ConversationBranch)
            .join(Conversation, Conversation.id == ConversationBranch.conversation_id)
            .where(
                ConversationBranch.conversation_id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(ConversationBranch.created_at.asc(), ConversationBranch.id.asc())
        )
        return list(result.scalars().all())

    async def update_branch_status(
        self,
        branch: ConversationBranch,
        status: BranchStatus,
    ) -> ConversationBranch:
        branch.status = status
        await self.session.flush()
        return branch

    async def copy_messages_up_to(
        self,
        *,
        parent_interaction_id: UUID,
        branch_interaction_id: UUID,
        branch_point_message_id: UUID,
    ) -> list[InteractionMessage]:
        result = await self.session.execute(
            select(InteractionMessage)
            .where(InteractionMessage.interaction_id == parent_interaction_id)
            .order_by(InteractionMessage.created_at.asc(), InteractionMessage.id.asc())
        )
        source_messages = list(result.scalars().all())
        copied: list[InteractionMessage] = []
        remap: dict[UUID, UUID] = {}
        found = False
        for source in source_messages:
            copied_parent_id = (
                remap.get(source.parent_message_id)
                if source.parent_message_id is not None
                else None
            )
            copied_message = InteractionMessage(
                interaction_id=branch_interaction_id,
                parent_message_id=copied_parent_id,
                sender_identity=source.sender_identity,
                message_type=source.message_type,
                content=source.content,
                metadata_json=dict(source.metadata_json),
            )
            copied_message.created_at = source.created_at
            copied_message.updated_at = source.updated_at
            self.session.add(copied_message)
            await self.session.flush()
            remap[source.id] = copied_message.id
            copied.append(copied_message)
            if source.id == branch_point_message_id:
                found = True
                break
        if not found:
            raise MessageNotInInteractionError(branch_point_message_id, parent_interaction_id)
        return copied

    async def merge_branch_messages(
        self,
        *,
        branch: ConversationBranch,
        merge_anchor_id: UUID | None,
    ) -> int:
        result = await self.session.execute(
            select(InteractionMessage)
            .where(
                InteractionMessage.interaction_id == branch.branch_interaction_id,
                InteractionMessage.created_at >= branch.created_at,
            )
            .order_by(InteractionMessage.created_at.asc(), InteractionMessage.id.asc())
        )
        branch_messages = list(result.scalars().all())
        remap: dict[UUID, UUID] = {}
        merged_count = 0
        for source in branch_messages:
            parent_message_id: UUID | None
            if source.parent_message_id is not None and source.parent_message_id in remap:
                parent_message_id = remap[source.parent_message_id]
            else:
                parent_message_id = merge_anchor_id
            merged = InteractionMessage(
                interaction_id=branch.parent_interaction_id,
                parent_message_id=parent_message_id,
                sender_identity=source.sender_identity,
                message_type=source.message_type,
                content=source.content,
                metadata_json=dict(source.metadata_json),
            )
            merged.created_at = source.created_at
            merged.updated_at = source.updated_at
            self.session.add(merged)
            await self.session.flush()
            remap[source.id] = merged.id
            merged_count += 1
        return merged_count

    async def check_prior_merges_from_same_point(self, branch: ConversationBranch) -> bool:
        total = await self.session.scalar(
            select(func.count())
            .select_from(BranchMergeRecord)
            .join(ConversationBranch, ConversationBranch.id == BranchMergeRecord.branch_id)
            .where(
                ConversationBranch.parent_interaction_id == branch.parent_interaction_id,
                ConversationBranch.branch_point_message_id == branch.branch_point_message_id,
                ConversationBranch.id != branch.id,
            )
        )
        return bool(total)

    async def create_merge_record(
        self,
        *,
        branch_id: UUID,
        merged_by: str,
        conflict_detected: bool,
        conflict_resolution: str | None,
        messages_merged_count: int,
    ) -> BranchMergeRecord:
        record = BranchMergeRecord(
            branch_id=branch_id,
            merged_by=merged_by,
            conflict_detected=conflict_detected,
            conflict_resolution=conflict_resolution,
            messages_merged_count=messages_merged_count,
        )
        self.session.add(record)
        await self.session.flush()
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
        request = AttentionRequest(
            workspace_id=workspace_id,
            source_agent_fqn=source_agent_fqn,
            target_identity=target_identity,
            urgency=urgency,
            context_summary=context_summary,
            related_execution_id=related_execution_id,
            related_interaction_id=related_interaction_id,
            related_goal_id=related_goal_id,
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_attention_request(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> AttentionRequest | None:
        result = await self.session.execute(
            select(AttentionRequest).where(
                AttentionRequest.id == request_id,
                AttentionRequest.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_attention_requests(
        self,
        *,
        workspace_id: UUID,
        target_identity: str,
        status: AttentionStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AttentionRequest], int]:
        filters = [
            AttentionRequest.workspace_id == workspace_id,
            AttentionRequest.target_identity == target_identity,
        ]
        if status is not None:
            filters.append(AttentionRequest.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(AttentionRequest).where(*filters)
        )
        result = await self.session.execute(
            select(AttentionRequest)
            .where(*filters)
            .order_by(AttentionRequest.created_at.desc(), AttentionRequest.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_attention_status(
        self,
        request: AttentionRequest,
        *,
        status: AttentionStatus,
        acknowledged_at: datetime | None,
        resolved_at: datetime | None,
    ) -> AttentionRequest:
        request.status = status
        if acknowledged_at is not None:
            request.acknowledged_at = acknowledged_at
        if resolved_at is not None:
            request.resolved_at = resolved_at
        await self.session.flush()
        return request

    async def get_initiator_identity(self, interaction_id: UUID) -> str | None:
        result = await self.session.execute(
            select(InteractionParticipant.identity)
            .where(
                InteractionParticipant.interaction_id == interaction_id,
                InteractionParticipant.role == ParticipantRole.initiator,
                InteractionParticipant.left_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
