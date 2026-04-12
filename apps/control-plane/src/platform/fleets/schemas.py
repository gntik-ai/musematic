from __future__ import annotations

from datetime import UTC, datetime
from platform.common.pagination import OffsetPage
from platform.fleets.models import (
    FleetMemberAvailability,
    FleetMemberRole,
    FleetStatus,
    FleetTopologyType,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_text(value: str) -> str:
    return value.strip()


class FleetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    topology_type: FleetTopologyType
    quorum_min: int = Field(default=1, ge=1)
    topology_config: dict[str, Any] = Field(default_factory=dict)
    member_fqns: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _strip_text(value)

    @field_validator("member_fqns")
    @classmethod
    def normalize_member_fqns(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class FleetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quorum_min: int | None = Field(default=None, ge=1)


class FleetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    status: FleetStatus
    topology_type: FleetTopologyType
    quorum_min: int
    created_at: datetime
    updated_at: datetime


class FleetListResponse(OffsetPage[FleetResponse]):
    pass


class FleetMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_fqn: str = Field(min_length=1, max_length=512)
    role: FleetMemberRole = FleetMemberRole.worker

    @field_validator("agent_fqn")
    @classmethod
    def normalize_agent_fqn(cls, value: str) -> str:
        return _strip_text(value)


class FleetMemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: FleetMemberRole


class FleetMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    agent_fqn: str
    role: FleetMemberRole
    availability: FleetMemberAvailability
    joined_at: datetime


class FleetMemberListResponse(BaseModel):
    items: list[FleetMemberResponse]
    total: int


class FleetTopologyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topology_type: FleetTopologyType
    config: dict[str, Any] = Field(default_factory=dict)


class FleetTopologyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    topology_type: FleetTopologyType
    version: int
    config: dict[str, Any]
    is_current: bool
    created_at: datetime


class FleetTopologyVersionListResponse(BaseModel):
    items: list[FleetTopologyVersionResponse]
    total: int


class FleetPolicyBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: UUID


class FleetPolicyBindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    workspace_id: UUID
    policy_id: UUID
    bound_by: UUID
    created_at: datetime


class ObserverAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observer_fqn: str = Field(min_length=1, max_length=512)

    @field_validator("observer_fqn")
    @classmethod
    def normalize_observer_fqn(cls, value: str) -> str:
        return _strip_text(value)


class ObserverAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    workspace_id: UUID
    observer_fqn: str
    is_active: bool
    created_at: datetime


class ObserverAssignmentListResponse(BaseModel):
    items: list[ObserverAssignmentResponse]
    total: int


class FleetGovernanceChainUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID] = Field(default_factory=list)

    @field_validator("observer_fqns", "judge_fqns", "enforcer_fqns")
    @classmethod
    def normalize_fqn_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class FleetGovernanceChainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    version: int
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID]
    is_current: bool
    is_default: bool
    created_at: datetime


class FleetGovernanceChainListResponse(BaseModel):
    items: list[FleetGovernanceChainResponse]
    total: int


class DelegationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["capability_match", "round_robin", "priority"]
    config: dict[str, Any] = Field(default_factory=dict)


class AggregationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["merge", "vote", "first_wins"]
    config: dict[str, Any] = Field(default_factory=dict)


class EscalationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(default=300, ge=0)
    failure_count: int = Field(default=3, ge=0)
    escalate_to: Literal["lead", "human"] = "lead"


class ConflictResolutionRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["majority_vote", "lead_decision", "human_arbitration"]


class RetryRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=2, ge=0)
    then: Literal["reassign", "fail"] = "reassign"


class FleetOrchestrationRulesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delegation: DelegationRules
    aggregation: AggregationRules
    escalation: EscalationRules = Field(default_factory=EscalationRules)
    conflict_resolution: ConflictResolutionRules
    retry: RetryRules = Field(default_factory=RetryRules)
    max_parallelism: int = Field(default=1, ge=1)


class FleetOrchestrationRulesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fleet_id: UUID
    version: int
    delegation: dict[str, Any]
    aggregation: dict[str, Any]
    escalation: dict[str, Any]
    conflict_resolution: dict[str, Any]
    retry: dict[str, Any]
    max_parallelism: int
    is_current: bool
    created_at: datetime


class FleetOrchestrationRulesListResponse(BaseModel):
    items: list[FleetOrchestrationRulesResponse]
    total: int


class MemberHealthStatus(BaseModel):
    agent_fqn: str
    availability: FleetMemberAvailability
    role: FleetMemberRole


class FleetHealthProjectionResponse(BaseModel):
    fleet_id: UUID
    status: FleetStatus
    health_pct: float
    quorum_met: bool
    available_count: int
    total_count: int
    member_statuses: list[MemberHealthStatus]
    last_updated: datetime


class OrchestrationModifier(BaseModel):
    max_wait_ms: int | None = None
    require_quorum_for_decision: bool = False
    auto_approve: bool = False
    escalate_unverified: bool = False


def default_health_projection(fleet_id: UUID) -> FleetHealthProjectionResponse:
    return FleetHealthProjectionResponse(
        fleet_id=fleet_id,
        status=FleetStatus.active,
        health_pct=1.0,
        quorum_met=True,
        available_count=0,
        total_count=0,
        member_statuses=[],
        last_updated=datetime.now(UTC),
    )


def default_modifier() -> OrchestrationModifier:
    return OrchestrationModifier()
