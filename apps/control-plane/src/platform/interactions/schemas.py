from __future__ import annotations

from datetime import datetime
from platform.common.pagination import OffsetPage
from platform.interactions.models import (
    AttentionStatus,
    AttentionUrgency,
    BranchStatus,
    InteractionState,
    MessageType,
    ParticipantRole,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_text(value: str) -> str:
    return value.strip()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _normalize_text(value)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_mutation(self) -> ConversationUpdate:
        if self.title is None and self.metadata is None:
            raise ValueError("At least one conversation field must be provided")
        return self


class InteractionCreate(BaseModel):
    conversation_id: UUID
    goal_id: UUID | None = None


class InteractionTransition(BaseModel):
    trigger: str = Field(
        ...,
        pattern=r"^(ready|start|wait|resume|pause|complete|fail|cancel)$",
    )
    error_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_error_metadata_on_fail(self) -> InteractionTransition:
        if self.trigger == "fail" and not self.error_metadata:
            raise ValueError("error_metadata is required when trigger is 'fail'")
        return self


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    parent_message_id: UUID | None = None
    message_type: MessageType = MessageType.user
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalize_text(value)


class MessageInject(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalize_text(value)


class ParticipantAdd(BaseModel):
    identity: str = Field(..., min_length=1, max_length=255)
    role: ParticipantRole

    @field_validator("identity")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return _normalize_text(value)


class GoalMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    interaction_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalize_text(value)


class GoalStateTransitionRequest(BaseModel):
    target_state: Literal["complete"]
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class GoalStateTransitionResponse(BaseModel):
    goal_id: UUID
    previous_state: str
    new_state: str
    automatic: bool
    transitioned_at: datetime


class AgentDecisionConfigUpsert(BaseModel):
    response_decision_strategy: str = Field(min_length=1, max_length=64)
    response_decision_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("response_decision_strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return _normalize_text(value)


class AgentDecisionConfigResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    response_decision_strategy: str
    response_decision_config: dict[str, Any]
    subscribed_at: datetime
    created_at: datetime
    updated_at: datetime


class AgentDecisionConfigListResponse(BaseModel):
    items: list[AgentDecisionConfigResponse]
    total: int


class DecisionRationaleResponse(BaseModel):
    id: UUID
    goal_id: UUID
    message_id: UUID
    agent_fqn: str
    strategy_name: str
    decision: str
    score: float | None
    matched_terms: list[str]
    rationale: str
    error: str | None
    created_at: datetime


class DecisionRationaleMessageListResponse(BaseModel):
    items: list[DecisionRationaleResponse]
    total: int


class DecisionRationaleListResponse(OffsetPage[DecisionRationaleResponse]):
    has_next: bool
    has_prev: bool


class BranchCreate(BaseModel):
    parent_interaction_id: UUID
    branch_point_message_id: UUID


class BranchMerge(BaseModel):
    conflict_resolution: str | None = Field(default=None, max_length=5_000)

    @field_validator("conflict_resolution")
    @classmethod
    def normalize_conflict_resolution(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class AttentionRequestCreate(BaseModel):
    target_identity: str = Field(..., min_length=1, max_length=255)
    urgency: AttentionUrgency
    context_summary: str = Field(..., min_length=1, max_length=5_000)
    related_execution_id: UUID | None = None
    related_interaction_id: UUID | None = None
    related_goal_id: UUID | None = None

    @field_validator("target_identity", "context_summary")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return _normalize_text(value)


class AttentionResolve(BaseModel):
    action: Literal["acknowledge", "resolve", "dismiss"]


class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    created_by: str
    metadata: dict[str, Any]
    message_count: int
    created_at: datetime
    updated_at: datetime


class InteractionResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    goal_id: UUID | None
    state: InteractionState
    state_changed_at: datetime
    error_metadata: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    interaction_id: UUID
    parent_message_id: UUID | None
    sender_identity: str
    message_type: MessageType
    content: str
    metadata: dict[str, Any]
    created_at: datetime


class ParticipantResponse(BaseModel):
    id: UUID
    interaction_id: UUID
    identity: str
    role: ParticipantRole
    joined_at: datetime
    left_at: datetime | None


class GoalMessageResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    goal_id: UUID
    participant_identity: str
    content: str
    interaction_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime


class BranchResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    parent_interaction_id: UUID
    branch_interaction_id: UUID
    branch_point_message_id: UUID
    status: BranchStatus
    created_at: datetime


class MergeRecordResponse(BaseModel):
    id: UUID
    branch_id: UUID
    merged_by: str
    conflict_detected: bool
    conflict_resolution: str | None
    messages_merged_count: int
    created_at: datetime


class AttentionRequestResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_agent_fqn: str
    target_identity: str
    urgency: AttentionUrgency
    context_summary: str
    related_execution_id: UUID | None
    related_interaction_id: UUID | None
    related_goal_id: UUID | None
    status: AttentionStatus
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime


class ConversationListResponse(OffsetPage[ConversationResponse]):
    has_next: bool
    has_prev: bool


class InteractionListResponse(OffsetPage[InteractionResponse]):
    has_next: bool
    has_prev: bool


class MessageListResponse(OffsetPage[MessageResponse]):
    has_next: bool
    has_prev: bool


class GoalMessageListResponse(OffsetPage[GoalMessageResponse]):
    has_next: bool
    has_prev: bool


class AttentionRequestListResponse(OffsetPage[AttentionRequestResponse]):
    has_next: bool
    has_prev: bool
