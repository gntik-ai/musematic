from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin, WorkspaceScopedMixin
from platform.workflows.models import TriggerType
from typing import Any, cast
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
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ExecutionStatus(StrEnum):
    """Represent the execution status."""

    queued = "queued"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"
    compensating = "compensating"
    paused = "paused"
    rolled_back = "rolled_back"
    rollback_failed = "rollback_failed"


class ExecutionEventType(StrEnum):
    """Represent the execution event type."""

    created = "created"
    queued = "queued"
    dispatched = "dispatched"
    runtime_started = "runtime_started"
    sandbox_requested = "sandbox_requested"
    waiting_for_approval = "waiting_for_approval"
    approved = "approved"
    rejected = "rejected"
    approval_timed_out = "approval_timed_out"
    resumed = "resumed"
    retried = "retried"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"
    compensated = "compensated"
    compensation_failed = "compensation_failed"
    hot_changed = "hot_changed"
    reasoning_trace_emitted = "reasoning_trace_emitted"
    self_correction_started = "self_correction_started"
    self_correction_converged = "self_correction_converged"
    context_assembled = "context_assembled"
    reprioritized = "reprioritized"
    rolled_back = "rolled_back"


class ApprovalDecision(StrEnum):
    """Represent the approval decision."""

    approved = "approved"
    rejected = "rejected"
    timed_out = "timed_out"
    escalated = "escalated"


class CompensationOutcome(StrEnum):
    """Represent the compensation outcome."""

    completed = "completed"
    failed = "failed"
    not_available = "not_available"


class ApprovalTimeoutAction(StrEnum):
    """Represent the approval timeout action."""

    fail = "fail"
    skip = "skip"
    escalate = "escalate"


class Execution(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Represent the execution."""

    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_workspace_status", "workspace_id", "status"),
        Index("ix_executions_workflow_definition_id", "workflow_definition_id"),
        Index("ix_executions_correlation_goal_id", "correlation_goal_id"),
    )

    workflow_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trigger_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_trigger_definitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        SAEnum(TriggerType, name="workflow_trigger_type"),
        nullable=False,
        default=TriggerType.manual,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(ExecutionStatus, name="execution_status"),
        nullable=False,
        default=ExecutionStatus.queued,
    )
    input_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    correlation_workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    correlation_conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    correlation_interaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    correlation_fleet_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    correlation_goal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    parent_execution_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    rerun_of_execution_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    contract_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    checkpoint_policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    events: Mapped[list[ExecutionEvent]] = relationship(
        "platform.execution.models.ExecutionEvent",
        back_populates="execution",
        order_by="platform.execution.models.ExecutionEvent.sequence.asc()",
        cascade="all, delete-orphan",
    )
    checkpoints: Mapped[list[ExecutionCheckpoint]] = relationship(
        "platform.execution.models.ExecutionCheckpoint",
        back_populates="execution",
        cascade="all, delete-orphan",
    )
    rollback_actions: Mapped[list[ExecutionRollbackAction]] = relationship(
        "platform.execution.models.ExecutionRollbackAction",
        back_populates="execution",
        cascade="all, delete-orphan",
    )
    reasoning_traces: Mapped[list[ExecutionReasoningTraceRecord]] = relationship(
        "platform.execution.models.ExecutionReasoningTraceRecord",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="platform.execution.models.ExecutionReasoningTraceRecord.created_at.asc()",
    )


cast(Any, Execution.__table__).append_constraint(
    Index(
        "ix_executions_contract_id",
        Execution.__table__.c.contract_id,
        postgresql_where=Execution.__table__.c.contract_id.is_not(None),
    )
)


class ExecutionEvent(Base, UUIDMixin):
    """Represent the execution event payload."""

    __tablename__ = "execution_events"
    __table_args__ = (
        Index("uq_execution_events_execution_sequence", "execution_id", "sequence", unique=True),
        Index("ix_execution_events_execution_type", "execution_id", "event_type"),
        Index("ix_execution_events_created_at", "created_at"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer(), nullable=False)
    event_type: Mapped[ExecutionEventType] = mapped_column(
        SAEnum(ExecutionEventType, name="execution_event_type"),
        nullable=False,
    )
    step_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    agent_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    correlation_workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    correlation_conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    correlation_interaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    correlation_goal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    correlation_fleet_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    correlation_execution_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    execution: Mapped[Execution] = relationship(
        "platform.execution.models.Execution",
        back_populates="events",
    )


class ExecutionCheckpoint(Base, UUIDMixin, TimestampMixin):
    """Represent the execution checkpoint."""

    __tablename__ = "execution_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "checkpoint_number",
            name="uq_execution_checkpoints_execution_checkpoint_number",
        ),
        Index(
            "ix_execution_checkpoints_execution_sequence",
            "execution_id",
            "last_event_sequence",
        ),
        Index(
            "ix_execution_checkpoints_execution_superseded",
            "execution_id",
            "superseded",
        ),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    checkpoint_number: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    last_event_sequence: Mapped[int] = mapped_column(Integer(), nullable=False)
    step_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    completed_step_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    pending_step_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    active_step_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    execution_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    current_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    accumulated_costs: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    superseded: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )

    execution: Mapped[Execution] = relationship(
        "platform.execution.models.Execution",
        back_populates="checkpoints",
    )


class ReprioritizationTrigger(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Represent a reprioritization trigger."""

    __tablename__ = "reprioritization_triggers"
    __table_args__ = (
        Index("ix_reprioritization_triggers_workspace_id", "workspace_id"),
        Index(
            "ix_reprioritization_triggers_workspace_enabled_priority",
            "workspace_id",
            "enabled",
            "priority_rank",
        ),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    condition_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    action: Mapped[str] = mapped_column(String(length=64), nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class RollbackActionStatus(StrEnum):
    """Represent the rollback action status."""

    completed = "completed"
    failed = "failed"


class ExecutionRollbackAction(Base, UUIDMixin, TimestampMixin):
    """Represent a rollback action performed against an execution."""

    __tablename__ = "execution_rollback_actions"
    __table_args__ = (Index("ix_execution_rollback_actions_execution_id", "execution_id"),)

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_checkpoint_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("execution_checkpoints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_checkpoint_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    initiated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    cost_delta_reversed: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    status: Mapped[RollbackActionStatus] = mapped_column(
        SAEnum(RollbackActionStatus, name="execution_rollback_action_status"),
        nullable=False,
        default=RollbackActionStatus.completed,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    execution: Mapped[Execution] = relationship(
        "platform.execution.models.Execution",
        back_populates="rollback_actions",
    )


class ExecutionDispatchLease(Base, UUIDMixin, TimestampMixin):
    """Represent the execution dispatch lease."""

    __tablename__ = "execution_dispatch_leases"
    __table_args__ = (
        Index("ix_execution_dispatch_leases_execution_step", "execution_id", "step_id"),
        Index("ix_execution_dispatch_leases_active", "execution_id", "released_at"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    scheduler_worker_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class ExecutionReasoningTraceRecord(Base, UUIDMixin, TimestampMixin):
    """Represent a persisted reasoning trace artifact for an execution step."""

    __tablename__ = "execution_reasoning_trace_records"
    __table_args__ = (
        Index("ix_execution_reasoning_trace_records_execution_id", "execution_id"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    technique: Mapped[str] = mapped_column(String(length=50), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    step_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(length=20), nullable=False, default="complete")
    compute_budget_used: Mapped[float | None] = mapped_column(Float(), nullable=True)
    consensus_reached: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    stabilized: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    degradation_detected: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    compute_budget_exhausted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    effective_budget_scope: Mapped[str | None] = mapped_column(String(length=16), nullable=True)

    execution: Mapped[Execution] = relationship(
        "platform.execution.models.Execution",
        back_populates="reasoning_traces",
    )


cast(Any, ExecutionReasoningTraceRecord.__table__).append_constraint(
    Index(
        "uq_execution_reasoning_trace_records_execution_step",
        ExecutionReasoningTraceRecord.__table__.c.execution_id,
        ExecutionReasoningTraceRecord.__table__.c.step_id,
        unique=True,
        postgresql_where=ExecutionReasoningTraceRecord.__table__.c.step_id.is_not(None),
    )
)


class ExecutionTaskPlanRecord(Base, UUIDMixin, TimestampMixin):
    """Represent the execution task plan record."""

    __tablename__ = "execution_task_plan_records"
    __table_args__ = (
        Index("ix_execution_task_plan_records_execution_id", "execution_id"),
        Index(
            "uq_execution_task_plan_records_execution_step",
            "execution_id",
            "step_id",
            unique=True,
        ),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    selected_agent_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    selected_tool_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    rationale_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    considered_agents_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    considered_tools_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    rejected_alternatives_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    parameter_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    storage_key: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    storage_size_bytes: Mapped[int | None] = mapped_column(Integer(), nullable=True)


class ExecutionApprovalWait(Base, UUIDMixin, TimestampMixin):
    """Represent the execution approval wait."""

    __tablename__ = "execution_approval_waits"
    __table_args__ = (
        Index("ix_execution_approval_waits_execution_step", "execution_id", "step_id"),
        Index("ix_execution_approval_waits_timeout_at", "timeout_at"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    required_approvers: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    timeout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeout_action: Mapped[ApprovalTimeoutAction] = mapped_column(
        SAEnum(ApprovalTimeoutAction, name="approval_timeout_action"),
        nullable=False,
        default=ApprovalTimeoutAction.fail,
    )
    decision: Mapped[ApprovalDecision | None] = mapped_column(
        SAEnum(ApprovalDecision, name="approval_decision"),
        nullable=True,
    )
    decided_by: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interaction_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )


class ExecutionCompensationRecord(Base, UUIDMixin, TimestampMixin):
    """Represent the execution compensation record."""

    __tablename__ = "execution_compensation_records"
    __table_args__ = (Index("ix_execution_compensation_records_execution_id", "execution_id"),)

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    compensation_handler: Mapped[str] = mapped_column(String(length=255), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(length=64), nullable=False)
    outcome: Mapped[CompensationOutcome] = mapped_column(
        SAEnum(CompensationOutcome, name="compensation_outcome"),
        nullable=False,
        default=CompensationOutcome.not_available,
    )
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
