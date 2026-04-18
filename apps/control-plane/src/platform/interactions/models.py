from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InteractionState(StrEnum):
    initializing = "initializing"
    ready = "ready"
    running = "running"
    waiting = "waiting"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class MessageType(StrEnum):
    user = "user"
    agent = "agent"
    system = "system"
    injection = "injection"


class ParticipantRole(StrEnum):
    initiator = "initiator"
    responder = "responder"
    observer = "observer"


class BranchStatus(StrEnum):
    active = "active"
    merged = "merged"
    abandoned = "abandoned"


class AttentionUrgency(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AttentionStatus(StrEnum):
    pending = "pending"
    acknowledged = "acknowledged"
    resolved = "resolved"
    dismissed = "dismissed"


class Conversation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(length=500), nullable=False)
    created_by: Mapped[str] = mapped_column(String(length=255), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    interactions: Mapped[list[Interaction]] = relationship(
        "platform.interactions.models.Interaction",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    branches: Mapped[list[ConversationBranch]] = relationship(
        "platform.interactions.models.ConversationBranch",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Interaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_conversation_state", "conversation_id", "state"),
        Index("ix_interactions_workspace_goal", "workspace_id", "goal_id"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces_goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    state: Mapped[InteractionState] = mapped_column(
        SAEnum(InteractionState, name="interactions_interaction_state"),
        nullable=False,
        default=InteractionState.initializing,
        index=True,
    )
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    error_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped[Conversation] = relationship(
        "platform.interactions.models.Conversation",
        back_populates="interactions",
    )
    messages: Mapped[list[InteractionMessage]] = relationship(
        "platform.interactions.models.InteractionMessage",
        back_populates="interaction",
        cascade="all, delete-orphan",
    )
    participants: Mapped[list[InteractionParticipant]] = relationship(
        "platform.interactions.models.InteractionParticipant",
        back_populates="interaction",
        cascade="all, delete-orphan",
    )


class InteractionMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interaction_messages"
    __table_args__ = (
        Index(
            "ix_interaction_messages_interaction_created",
            "interaction_id",
            "created_at",
        ),
        Index("ix_interaction_messages_parent", "parent_message_id"),
    )

    interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interaction_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    sender_identity: Mapped[str] = mapped_column(String(length=255), nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        SAEnum(MessageType, name="interactions_message_type"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )

    interaction: Mapped[Interaction] = relationship(
        "platform.interactions.models.Interaction",
        back_populates="messages",
    )
    parent: Mapped[InteractionMessage | None] = relationship(
        "platform.interactions.models.InteractionMessage",
        remote_side="platform.interactions.models.InteractionMessage.id",
    )


class InteractionParticipant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interaction_participants"
    __table_args__ = (
        UniqueConstraint("interaction_id", "identity", name="uq_interaction_participants_identity"),
    )

    interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity: Mapped[str] = mapped_column(String(length=255), nullable=False)
    role: Mapped[ParticipantRole] = mapped_column(
        SAEnum(ParticipantRole, name="interactions_participant_role"),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    interaction: Mapped[Interaction] = relationship(
        "platform.interactions.models.Interaction",
        back_populates="participants",
    )


class WorkspaceGoalMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_goal_messages"
    __table_args__ = (
        Index("ix_workspace_goal_messages_goal_created", "goal_id", "created_at"),
        Index(
            "ix_workspace_goal_messages_workspace_goal",
            "workspace_id",
            "goal_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_identity: Mapped[str] = mapped_column(String(length=255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    interaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )


class WorkspaceGoalDecisionRationale(Base, UUIDMixin):
    __tablename__ = "workspace_goal_decision_rationales"
    __table_args__ = (
        UniqueConstraint("message_id", "agent_fqn", name="uq_wgdr_message_agent"),
        Index("ix_wgdr_goal", "goal_id", "created_at"),
        Index("ix_wgdr_workspace", "workspace_id", "agent_fqn"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    goal_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_goals.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspace_goal_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(Text(), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    decision: Mapped[str] = mapped_column(String(length=8), nullable=False)
    score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    matched_terms: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)


class ConversationBranch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_branches"
    __table_args__ = (Index("ix_conversation_branches_parent", "parent_interaction_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("interactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("interactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    branch_point_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("interaction_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[BranchStatus] = mapped_column(
        SAEnum(BranchStatus, name="interactions_branch_status"),
        nullable=False,
        default=BranchStatus.active,
    )

    conversation: Mapped[Conversation] = relationship(
        "platform.interactions.models.Conversation",
        back_populates="branches",
    )


class BranchMergeRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "branch_merge_records"

    branch_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merged_by: Mapped[str] = mapped_column(String(length=255), nullable=False)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_merged_count: Mapped[int] = mapped_column(Integer, nullable=False)


class AttentionRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attention_requests"
    __table_args__ = (Index("ix_attention_requests_target_status", "target_identity", "status"),)

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)
    target_identity: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    urgency: Mapped[AttentionUrgency] = mapped_column(
        SAEnum(AttentionUrgency, name="interactions_attention_urgency"),
        nullable=False,
    )
    context_summary: Mapped[str] = mapped_column(Text, nullable=False)
    related_execution_id: Mapped[UUID | None] = mapped_column(nullable=True)
    related_interaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_goal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces_goals.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[AttentionStatus] = mapped_column(
        SAEnum(AttentionStatus, name="interactions_attention_status"),
        nullable=False,
        default=AttentionStatus.pending,
        index=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
