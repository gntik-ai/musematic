from __future__ import annotations

from datetime import UTC, datetime
from platform.fleet_learning.models import (
    AutonomyLevel,
    CommunicationStyle,
    DecisionSpeed,
    RiskTolerance,
    TransferRequestStatus,
)
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FleetPerformanceProfileQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime


class FleetPerformanceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    period_start: datetime
    period_end: datetime
    avg_completion_time_ms: float
    success_rate: float
    cost_per_task: float
    avg_quality_score: float
    throughput_per_hour: float
    member_metrics: dict[str, Any]
    flagged_member_fqns: list[str]
    created_at: datetime


class FleetPerformanceProfileListResponse(BaseModel):
    items: list[FleetPerformanceProfileResponse]
    total: int


class AdaptationCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: Literal[
        "avg_completion_time_ms",
        "success_rate",
        "cost_per_task",
        "avg_quality_score",
        "throughput_per_hour",
    ]
    operator: Literal["gt", "lt", "gte", "lte", "eq"]
    threshold: float


class AdaptationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "set_max_parallelism",
        "set_delegation_strategy",
        "set_escalation_timeout",
        "set_aggregation_strategy",
    ]
    value: Any


class FleetAdaptationRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    condition: AdaptationCondition
    action: AdaptationAction
    priority: int = 0

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class FleetAdaptationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    name: str
    condition: dict[str, Any]
    action: dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime


class FleetAdaptationRuleListResponse(BaseModel):
    items: list[FleetAdaptationRuleResponse]
    total: int


class FleetAdaptationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    adaptation_rule_id: UUID
    triggered_at: datetime
    before_rules_version: int
    after_rules_version: int
    performance_snapshot: dict[str, Any]
    is_reverted: bool
    reverted_at: datetime | None


class FleetAdaptationLogListResponse(BaseModel):
    items: list[FleetAdaptationLogResponse]
    total: int


class CrossFleetTransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_fleet_id: UUID
    pattern_definition: dict[str, Any]


class TransferApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransferRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CrossFleetTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_fleet_id: UUID
    target_fleet_id: UUID
    status: TransferRequestStatus
    pattern_definition: dict[str, Any] | None
    pattern_minio_key: str | None
    proposed_by: UUID
    approved_by: UUID | None
    rejected_reason: str | None
    applied_at: datetime | None
    reverted_at: datetime | None
    created_at: datetime


class CrossFleetTransferListResponse(BaseModel):
    items: list[CrossFleetTransferResponse]
    total: int


class FleetPersonalityProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    communication_style: CommunicationStyle
    decision_speed: DecisionSpeed
    risk_tolerance: RiskTolerance
    autonomy_level: AutonomyLevel


class FleetPersonalityProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    communication_style: CommunicationStyle
    decision_speed: DecisionSpeed
    risk_tolerance: RiskTolerance
    autonomy_level: AutonomyLevel
    version: int
    is_current: bool
    created_at: datetime


def default_personality_profile(fleet_id: UUID) -> FleetPersonalityProfileResponse:
    return FleetPersonalityProfileResponse(
        id=uuid4(),
        fleet_id=fleet_id,
        communication_style=CommunicationStyle.concise,
        decision_speed=DecisionSpeed.deliberate,
        risk_tolerance=RiskTolerance.moderate,
        autonomy_level=AutonomyLevel.semi_autonomous,
        version=1,
        is_current=True,
        created_at=datetime.now(UTC),
    )
