from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.agentops.exceptions import WeightSumError
from platform.agentops.models import (
    AdaptationProposalStatus,
    BaselineStatus,
    CanaryDeploymentStatus,
    OutcomeClassification,
    ProficiencyLevel,
    RegressionAlertStatus,
    RetirementWorkflowStatus,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentHealthConfigPayload(_StrictModel):
    weight_uptime: Decimal = Field(default=Decimal("20.00"))
    weight_quality: Decimal = Field(default=Decimal("35.00"))
    weight_safety: Decimal = Field(default=Decimal("25.00"))
    weight_cost_efficiency: Decimal = Field(default=Decimal("10.00"))
    weight_satisfaction: Decimal = Field(default=Decimal("10.00"))
    warning_threshold: Decimal = Field(default=Decimal("60.00"))
    critical_threshold: Decimal = Field(default=Decimal("40.00"))
    scoring_interval_minutes: int = Field(default=15, ge=1)
    min_sample_size: int = Field(default=50, ge=1)
    rolling_window_days: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def validate_weight_sum(self) -> AgentHealthConfigPayload:
        total = (
            self.weight_uptime
            + self.weight_quality
            + self.weight_safety
            + self.weight_cost_efficiency
            + self.weight_satisfaction
        )
        if abs(float(total) - 100.0) > 1e-6:
            raise WeightSumError(float(total))
        return self


class AgentHealthConfigUpdateRequest(AgentHealthConfigPayload):
    pass


class AgentHealthConfigResponse(AgentHealthConfigPayload, _OrmModel):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentHealthScoreResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID
    composite_score: Decimal
    uptime_score: Decimal | None
    quality_score: Decimal | None
    safety_score: Decimal | None
    cost_efficiency_score: Decimal | None
    satisfaction_score: Decimal | None
    weights_snapshot: dict[str, float]
    missing_dimensions: list[str]
    sample_counts: dict[str, int]
    computed_at: datetime
    observation_window_start: datetime
    observation_window_end: datetime
    below_warning: bool
    below_critical: bool
    insufficient_data: bool
    created_at: datetime
    updated_at: datetime


class AgentHealthScoreHistoryResponse(BaseModel):
    items: list[AgentHealthScoreResponse]
    next_cursor: str | None = None


class BehavioralBaselineResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID
    quality_mean: float
    quality_stddev: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_stddev_ms: float
    error_rate_mean: float
    cost_per_execution_mean: float
    cost_per_execution_stddev: float
    safety_pass_rate: float
    sample_size: int
    baseline_window_start: datetime
    baseline_window_end: datetime
    status: BaselineStatus | str
    created_at: datetime
    updated_at: datetime


class RegressionAlertResolveRequest(_StrictModel):
    resolution: Literal["resolved", "dismissed"]
    reason: str = Field(min_length=1)


class RegressionAlertResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    new_revision_id: UUID
    baseline_revision_id: UUID
    status: RegressionAlertStatus | str
    regressed_dimensions: list[str]
    statistical_test: str
    p_value: float
    effect_size: float
    significance_threshold: float
    sample_sizes: dict[str, int]
    detected_at: datetime
    resolved_at: datetime | None
    resolved_by: UUID | None
    resolution_reason: str | None
    triggered_rollback: bool
    created_at: datetime
    updated_at: datetime


class RegressionAlertListResponse(BaseModel):
    items: list[RegressionAlertResponse]
    next_cursor: str | None = None


class GateCheckRequest(_StrictModel):
    revision_id: UUID
    workspace_id: UUID


class CiCdGateResultResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID
    requested_by: UUID
    overall_passed: bool
    policy_gate_passed: bool
    policy_gate_detail: dict[str, Any]
    policy_gate_remediation: str | None
    evaluation_gate_passed: bool
    evaluation_gate_detail: dict[str, Any]
    evaluation_gate_remediation: str | None
    certification_gate_passed: bool
    certification_gate_detail: dict[str, Any]
    certification_gate_remediation: str | None
    regression_gate_passed: bool
    regression_gate_detail: dict[str, Any]
    regression_gate_remediation: str | None
    trust_tier_gate_passed: bool
    trust_tier_gate_detail: dict[str, Any]
    trust_tier_gate_remediation: str | None
    evaluated_at: datetime
    evaluation_duration_ms: int
    created_at: datetime
    updated_at: datetime


class CiCdGateResultListResponse(BaseModel):
    items: list[CiCdGateResultResponse]
    next_cursor: str | None = None


class CanaryDeploymentCreateRequest(_StrictModel):
    workspace_id: UUID
    production_revision_id: UUID
    canary_revision_id: UUID
    traffic_percentage: int = Field(ge=1, le=50)
    observation_window_hours: float = Field(ge=1.0)
    quality_tolerance_pct: float = Field(default=5.0, ge=0.0)
    latency_tolerance_pct: float = Field(default=5.0, ge=0.0)
    error_rate_tolerance_pct: float = Field(default=5.0, ge=0.0)
    cost_tolerance_pct: float = Field(default=5.0, ge=0.0)


class CanaryDecisionRequest(_StrictModel):
    reason: str = Field(min_length=1)


class CanaryDeploymentResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    production_revision_id: UUID
    canary_revision_id: UUID
    initiated_by: UUID
    traffic_percentage: int
    observation_window_hours: float
    quality_tolerance_pct: float
    latency_tolerance_pct: float
    error_rate_tolerance_pct: float
    cost_tolerance_pct: float
    status: CanaryDeploymentStatus | str
    started_at: datetime
    observation_ends_at: datetime
    completed_at: datetime | None
    promoted_at: datetime | None
    rolled_back_at: datetime | None
    rollback_reason: str | None
    manual_override_by: UUID | None
    manual_override_reason: str | None
    latest_metrics_snapshot: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class CanaryDeploymentListResponse(BaseModel):
    items: list[CanaryDeploymentResponse]
    next_cursor: str | None = None


class RetirementInitiateRequest(_StrictModel):
    workspace_id: UUID
    revision_id: UUID
    reason: str = Field(min_length=1)
    operator_confirmed: bool = False


class RetirementHaltRequest(_StrictModel):
    reason: str = Field(min_length=1)


class RetirementConfirmRequest(_StrictModel):
    confirmed: Literal[True]
    reason: str = Field(min_length=1)


class RetirementWorkflowResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID
    trigger_reason: str
    trigger_detail: dict[str, Any]
    status: RetirementWorkflowStatus | str
    dependent_workflows: list[dict[str, Any]]
    high_impact_flag: bool
    operator_confirmed: bool
    notifications_sent_at: datetime | None
    grace_period_days: int
    grace_period_starts_at: datetime
    grace_period_ends_at: datetime
    retired_at: datetime | None
    halted_at: datetime | None
    halted_by: UUID | None
    halt_reason: str | None
    created_at: datetime
    updated_at: datetime


class RetirementWorkflowListResponse(BaseModel):
    items: list[RetirementWorkflowResponse]
    next_cursor: str | None = None


class GovernanceEventResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID | None
    event_type: str
    actor_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime


class GovernanceEventListResponse(BaseModel):
    items: list[GovernanceEventResponse]
    next_cursor: str | None = None


class GovernanceSummaryResponse(_StrictModel):
    agent_fqn: str
    workspace_id: UUID
    certification_status: str | None = None
    trust_tier: int | None = None
    pending_triggers: list[dict[str, Any]] = Field(default_factory=list)
    upcoming_expirations: list[dict[str, Any]] = Field(default_factory=list)
    active_alerts: list[RegressionAlertResponse] = Field(default_factory=list)
    active_retirement: RetirementWorkflowResponse | None = None


class AdaptationTriggerRequest(_StrictModel):
    workspace_id: UUID
    revision_id: UUID | None = None


class AdaptationReviewRequest(_StrictModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        return value


class AdaptationApplyRequest(_StrictModel):
    reason: str | None = None


class AdaptationRollbackRequest(_StrictModel):
    reason: str = Field(min_length=1)


class AdaptationRevokeRequest(_StrictModel):
    reason: str = Field(min_length=1)


class AdaptationOutcomeResponse(_OrmModel):
    id: UUID
    proposal_id: UUID
    observation_window_start: datetime
    observation_window_end: datetime
    expected_delta: dict[str, Any]
    observed_delta: dict[str, Any]
    classification: OutcomeClassification | str
    variance_annotation: dict[str, Any] | None
    measured_at: datetime
    created_at: datetime
    updated_at: datetime


class AdaptationLineageResponse(_StrictModel):
    proposal: AdaptationProposalResponse
    snapshot: dict[str, Any] | None = None
    outcome: AdaptationOutcomeResponse | None = None


class AdaptationApplyResponse(_StrictModel):
    proposal: AdaptationProposalResponse
    pre_apply_configuration_hash: str


class AdaptationRollbackResponse(_StrictModel):
    proposal: AdaptationProposalResponse
    byte_identical_to_pre_apply: bool


class AdaptationRevokeResponse(_StrictModel):
    proposal: AdaptationProposalResponse


class ProficiencyResponse(_StrictModel):
    agent_fqn: str
    workspace_id: UUID
    level: ProficiencyLevel | str
    dimension_values: dict[str, float] = Field(default_factory=dict)
    observation_count: int = 0
    trigger: str | None = None
    assessed_at: datetime | None = None
    missing_dimensions: list[str] = Field(default_factory=list)


class ProficiencyHistoryResponse(BaseModel):
    items: list[ProficiencyResponse]
    next_cursor: str | None = None


class ProficiencyFleetResponse(BaseModel):
    items: list[ProficiencyResponse]
    total: int


class AdaptationProposalResponse(_OrmModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    revision_id: UUID | None
    status: AdaptationProposalStatus | str
    proposal_details: dict[str, Any]
    signals: list[dict[str, Any]]
    expected_improvement: dict[str, Any] | None = None
    pre_apply_snapshot_key: str | None = None
    applied_at: datetime | None = None
    applied_by: UUID | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by: UUID | None = None
    rollback_reason: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None
    revoke_reason: str | None = None
    signal_source: str | None = None
    review_reason: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    candidate_revision_id: UUID | None
    evaluation_run_id: UUID | None
    completed_at: datetime | None
    completion_note: str | None
    created_at: datetime
    updated_at: datetime


class AdaptationProposalListResponse(BaseModel):
    items: list[AdaptationProposalResponse]
    next_cursor: str | None = None


class RegressionAlertSummary(_StrictModel):
    id: UUID
    status: RegressionAlertStatus | str
    regressed_dimensions: list[str]
    p_value: float
    effect_size: float
    detected_at: datetime


class AgentHealthScoreSummary(_StrictModel):
    id: UUID
    agent_fqn: str
    workspace_id: UUID
    composite_score: Decimal
    below_warning: bool
    below_critical: bool
    insufficient_data: bool
    computed_at: datetime


class CiCdGateSummary(_StrictModel):
    id: UUID | None = None
    agent_fqn: str
    revision_id: UUID
    workspace_id: UUID
    requested_by: UUID
    overall_passed: bool
    summary: dict[str, Any] = Field(default_factory=dict)


AdaptationLineageResponse.model_rebuild()
