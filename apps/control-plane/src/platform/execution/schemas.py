from __future__ import annotations

from datetime import datetime
from platform.execution.models import (
    ApprovalDecision,
    ExecutionEventType,
    ExecutionStatus,
)
from platform.workflows.models import TriggerType
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionCreate(BaseModel):
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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionListResponse(BaseModel):
    items: list[ExecutionResponse]
    total: int


class ExecutionEventResponse(BaseModel):
    id: UUID
    sequence: int
    event_type: ExecutionEventType
    step_id: str | None
    agent_fqn: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionEventListResponse(BaseModel):
    items: list[ExecutionEventResponse]
    total: int


class ExecutionStateResponse(BaseModel):
    execution_id: UUID
    status: ExecutionStatus
    completed_step_ids: list[str] = Field(default_factory=list)
    active_step_ids: list[str] = Field(default_factory=list)
    pending_step_ids: list[str] = Field(default_factory=list)
    step_results: dict[str, Any] = Field(default_factory=dict)
    last_event_sequence: int = 0
    workflow_version_id: UUID | None = None


class CheckpointResponse(BaseModel):
    id: UUID
    last_event_sequence: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskPlanRecordResponse(BaseModel):
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
    considered_agents: list[dict[str, Any]] = Field(default_factory=list)
    considered_tools: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    comment: str | None = None


class ReprioritizationEvent(BaseModel):
    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]
    priority_changes: list[dict[str, Any]]


class HotChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_version_id: UUID


class HotChangeCompatibilityResult(BaseModel):
    compatible: bool
    issues: list[str] = Field(default_factory=list)
    active_step_ids: list[str] = Field(default_factory=list)


class ApprovalWaitResponse(BaseModel):
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
    items: list[ApprovalWaitResponse]
    total: int


class HotChangeApplyResponse(BaseModel):
    result: HotChangeCompatibilityResult
    execution: ExecutionResponse
