from __future__ import annotations

from datetime import datetime
from platform.execution.models import (
    ApprovalDecision,
    ExecutionEventType,
    ExecutionStatus,
)
from platform.workflows.models import TriggerType
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BeforeToolInvocationsCheckpointPolicy(BaseModel):
    """Represent the default pre-tool checkpoint policy."""

    type: Literal["before_tool_invocations"]


class BeforeEveryStepCheckpointPolicy(BaseModel):
    """Represent the every-step checkpoint policy."""

    type: Literal["before_every_step"]


class NamedStepsCheckpointPolicy(BaseModel):
    """Represent the named-steps checkpoint policy."""

    type: Literal["named_steps"]
    step_ids: list[str] = Field(default_factory=list, min_length=1)


class DisabledCheckpointPolicy(BaseModel):
    """Represent a disabled checkpoint policy."""

    type: Literal["disabled"]


CheckpointPolicySchema = Annotated[
    BeforeToolInvocationsCheckpointPolicy
    | BeforeEveryStepCheckpointPolicy
    | NamedStepsCheckpointPolicy
    | DisabledCheckpointPolicy,
    Field(discriminator="type"),
]

DEFAULT_CHECKPOINT_POLICY: dict[str, Any] = {"type": "before_tool_invocations"}


class ExecutionCreate(BaseModel):
    """Represent the execution create."""

    model_config = ConfigDict(extra="forbid")

    workflow_version_id: UUID | None = None
    workflow_definition_id: UUID
    trigger_type: TriggerType = TriggerType.manual
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    workspace_id: UUID
    correlation_conversation_id: UUID | None = None
    correlation_interaction_id: UUID | None = None
    correlation_fleet_id: UUID | None = None
    correlation_goal_id: UUID | None = None
    trigger_id: UUID | None = None
    sla_deadline: datetime | None = None


class ExecutionResponse(BaseModel):
    """Represent the execution response payload."""

    id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    trigger_id: UUID | None
    trigger_type: TriggerType
    status: ExecutionStatus
    input_parameters: dict[str, Any]
    workspace_id: UUID
    correlation_goal_id: UUID | None
    parent_execution_id: UUID | None
    rerun_of_execution_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    sla_deadline: datetime | None
    checkpoint_policy_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionListResponse(BaseModel):
    """Represent the execution list response payload."""

    items: list[ExecutionResponse]
    total: int


class ExecutionEventResponse(BaseModel):
    """Represent the execution event response payload."""

    id: UUID
    sequence: int
    event_type: ExecutionEventType
    step_id: str | None
    agent_fqn: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionEventListResponse(BaseModel):
    """Represent the execution event list response payload."""

    items: list[ExecutionEventResponse]
    total: int


class ExecutionStateResponse(BaseModel):
    """Represent the execution state response payload."""

    execution_id: UUID
    status: ExecutionStatus
    completed_step_ids: list[str] = Field(default_factory=list)
    active_step_ids: list[str] = Field(default_factory=list)
    pending_step_ids: list[str] = Field(default_factory=list)
    step_results: dict[str, Any] = Field(default_factory=dict)
    last_event_sequence: int = 0
    workflow_version_id: UUID | None = None


class CheckpointResponse(BaseModel):
    """Represent the checkpoint response payload."""

    id: UUID
    last_event_sequence: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReprioritizationTriggerCreate(BaseModel):
    """Represent a reprioritization trigger create payload."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    trigger_type: str = Field(default="sla_approach", min_length=1, max_length=32)
    condition_config: dict[str, Any] = Field(default_factory=dict)
    action: str = Field(default="promote_to_front", min_length=1, max_length=64)
    priority_rank: int = Field(default=100, ge=0)
    enabled: bool = True


class ReprioritizationTriggerUpdate(BaseModel):
    """Represent a reprioritization trigger patch payload."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    condition_config: dict[str, Any] | None = None
    action: str | None = Field(default=None, min_length=1, max_length=64)
    priority_rank: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class ReprioritizationTriggerResponse(BaseModel):
    """Represent a reprioritization trigger response payload."""

    id: UUID
    workspace_id: UUID
    name: str
    trigger_type: str
    condition_config: dict[str, Any]
    action: str
    priority_rank: int
    enabled: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReprioritizationTriggerListResponse(BaseModel):
    """Represent a reprioritization trigger list payload."""

    items: list[ReprioritizationTriggerResponse]
    total: int
    page: int
    page_size: int


class CheckpointSummaryResponse(BaseModel):
    """Represent a checkpoint summary payload."""

    id: UUID
    execution_id: UUID
    checkpoint_number: int
    last_event_sequence: int
    created_at: datetime
    completed_step_count: int
    current_step_id: str | None = None
    accumulated_costs: dict[str, Any] = Field(default_factory=dict)
    superseded: bool
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)


class CheckpointListResponse(BaseModel):
    """Represent a paginated checkpoint list payload."""

    items: list[CheckpointSummaryResponse]
    total: int
    page: int
    page_size: int


class CheckpointDetailResponse(BaseModel):
    """Represent a checkpoint detail payload."""

    id: UUID
    execution_id: UUID
    checkpoint_number: int
    last_event_sequence: int
    created_at: datetime
    step_results: dict[str, Any]
    completed_step_ids: list[str]
    pending_step_ids: list[str]
    active_step_ids: list[str]
    current_context: dict[str, Any]
    accumulated_costs: dict[str, Any]
    execution_data: dict[str, Any]
    superseded: bool
    policy_snapshot: dict[str, Any]


class TaskPlanRecordResponse(BaseModel):
    """Represent the task plan record response payload."""

    id: UUID
    execution_id: UUID
    step_id: str
    selected_agent_fqn: str | None
    selected_tool_fqn: str | None
    rationale_summary: str | None
    considered_agents_count: int
    considered_tools_count: int
    rejected_alternatives_count: int
    parameter_sources: list[str]
    storage_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskPlanFullResponse(TaskPlanRecordResponse):
    """Represent the task plan full response payload."""

    considered_agents: list[dict[str, Any]] = Field(default_factory=list)
    considered_tools: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    """Represent the approval decision request payload."""

    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    comment: str | None = None


class ReprioritizationEvent(BaseModel):
    """Represent the reprioritization event payload."""

    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]
    priority_changes: list[dict[str, Any]]


class RollbackRequest(BaseModel):
    """Represent a rollback request payload."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class RollbackResponse(BaseModel):
    """Represent a rollback response payload."""

    rollback_action_id: UUID
    execution_id: UUID
    target_checkpoint_id: UUID
    target_checkpoint_number: int
    initiated_by: UUID | None
    cost_delta_reversed: dict[str, Any]
    status: str
    execution_status: ExecutionStatus
    warning: str | None = None
    created_at: datetime


class HotChangeRequest(BaseModel):
    """Represent the hot change request payload."""

    model_config = ConfigDict(extra="forbid")

    new_version_id: UUID


class HotChangeCompatibilityResult(BaseModel):
    """Represent the hot change compatibility result."""

    compatible: bool
    issues: list[str] = Field(default_factory=list)
    active_step_ids: list[str] = Field(default_factory=list)


class ApprovalWaitResponse(BaseModel):
    """Represent the approval wait response payload."""

    id: UUID
    execution_id: UUID
    step_id: str
    required_approvers: list[str]
    timeout_at: datetime
    decision: ApprovalDecision | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalWaitListResponse(BaseModel):
    """Represent the approval wait list response payload."""

    items: list[ApprovalWaitResponse]
    total: int


class HotChangeApplyResponse(BaseModel):
    """Represent the hot change apply response payload."""

    result: HotChangeCompatibilityResult
    execution: ExecutionResponse


class WarmPoolKeyStatus(BaseModel):
    """Represent the warm pool key status payload."""

    workspace_id: UUID
    agent_type: str
    target_size: int
    available_count: int
    dispatched_count: int
    warming_count: int
    last_dispatch_at: datetime | None = None


class WarmPoolStatusResponse(BaseModel):
    """Represent the warm pool status response payload."""

    keys: list[WarmPoolKeyStatus] = Field(default_factory=list)


class WarmPoolConfigRequest(BaseModel):
    """Represent the warm pool config request payload."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_type: str = Field(min_length=1, max_length=255)
    target_size: int = Field(ge=0)


class WarmPoolConfigResponse(BaseModel):
    """Represent the warm pool config response payload."""

    accepted: bool
    message: str = ""
