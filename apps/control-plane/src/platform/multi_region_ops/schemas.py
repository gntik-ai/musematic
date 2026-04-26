from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.multi_region_ops.constants import (
    FAILOVER_PLAN_RUN_KINDS,
    FAILOVER_PLAN_RUN_OUTCOMES,
    FAILOVER_PLAN_STEP_KINDS,
    MAINTENANCE_STATUSES,
    REGION_ROLES,
    REPLICATION_COMPONENTS,
    REPLICATION_HEALTH,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RegionRole(StrEnum):
    primary = "primary"
    secondary = "secondary"


class ReplicationComponent(StrEnum):
    postgres = "postgres"
    kafka = "kafka"
    s3 = "s3"
    clickhouse = "clickhouse"
    qdrant = "qdrant"
    neo4j = "neo4j"
    opensearch = "opensearch"


class ReplicationHealth(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"
    paused = "paused"


class FailoverPlanStepKind(StrEnum):
    promote_postgres = "promote_postgres"
    flip_kafka_mirrormaker = "flip_kafka_mirrormaker"
    update_dns = "update_dns"
    verify_health = "verify_health"
    drain_workers = "drain_workers"
    resume_workers = "resume_workers"
    cutover_s3 = "cutover_s3"
    cutover_clickhouse = "cutover_clickhouse"
    cutover_qdrant = "cutover_qdrant"
    cutover_neo4j = "cutover_neo4j"
    cutover_opensearch = "cutover_opensearch"
    custom = "custom"


class FailoverPlanRunKind(StrEnum):
    rehearsal = "rehearsal"
    production = "production"


class FailoverPlanRunOutcome(StrEnum):
    succeeded = "succeeded"
    failed = "failed"
    aborted = "aborted"
    in_progress = "in_progress"


class MaintenanceWindowStatus(StrEnum):
    scheduled = "scheduled"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class CapacityConfidence(StrEnum):
    ok = "ok"
    low = "low"
    insufficient_history = "insufficient_history"


class RegionConfigCreateRequest(BaseModel):
    region_code: str = Field(min_length=1, max_length=32)
    region_role: RegionRole
    endpoint_urls: dict[str, Any] = Field(default_factory=dict)
    rpo_target_minutes: int = Field(default=15, ge=1)
    rto_target_minutes: int = Field(default=60, ge=1)
    enabled: bool = True


class RegionConfigUpdateRequest(BaseModel):
    region_code: str | None = Field(default=None, min_length=1, max_length=32)
    region_role: RegionRole | None = None
    endpoint_urls: dict[str, Any] | None = None
    rpo_target_minutes: int | None = Field(default=None, ge=1)
    rto_target_minutes: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


class RegionConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    region_code: str
    region_role: RegionRole
    endpoint_urls: dict[str, Any]
    rpo_target_minutes: int
    rto_target_minutes: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ReplicationStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    source_region: str
    target_region: str
    component: ReplicationComponent
    lag_seconds: int | None
    health: ReplicationHealth
    pause_reason: str | None = None
    error_detail: str | None = None
    measured_at: datetime | None = None
    threshold_seconds: int | None = None
    missing_probe: bool = False


class ReplicationOverviewResponse(BaseModel):
    items: list[ReplicationStatusResponse]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FailoverPlanStep(BaseModel):
    kind: FailoverPlanStepKind
    name: str = Field(min_length=1, max_length=256)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_kind(cls, value: Any) -> Any:
        if str(value) not in FAILOVER_PLAN_STEP_KINDS:
            raise ValueError(f"Unsupported failover step kind: {value}")
        return value


class FailoverPlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    from_region: str = Field(min_length=1, max_length=32)
    to_region: str = Field(min_length=1, max_length=32)
    steps: list[FailoverPlanStep] = Field(min_length=1)
    runbook_url: str | None = None


class FailoverPlanUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    from_region: str | None = Field(default=None, min_length=1, max_length=32)
    to_region: str | None = Field(default=None, min_length=1, max_length=32)
    steps: list[FailoverPlanStep] | None = Field(default=None, min_length=1)
    runbook_url: str | None = None


class FailoverPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    from_region: str
    to_region: str
    steps: list[FailoverPlanStep]
    runbook_url: str | None
    tested_at: datetime | None
    last_executed_at: datetime | None
    created_by: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False


class StepOutcomeRecord(BaseModel):
    step_index: int
    kind: FailoverPlanStepKind
    name: str
    outcome: FailoverPlanRunOutcome
    duration_ms: int = 0
    error_detail: str | None = None


class FailoverPlanRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    run_kind: FailoverPlanRunKind
    outcome: FailoverPlanRunOutcome
    started_at: datetime
    ended_at: datetime | None
    step_outcomes: list[StepOutcomeRecord]
    initiated_by: UUID | None
    reason: str | None
    lock_token: str


class FailoverPlanExecuteRequest(BaseModel):
    run_kind: FailoverPlanRunKind = FailoverPlanRunKind.rehearsal
    reason: str | None = None


class MaintenanceWindowCreateRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None
    blocks_writes: bool = True
    announcement_text: str | None = None

    @model_validator(mode="after")
    def _validate_times(self) -> MaintenanceWindowCreateRequest:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class MaintenanceWindowUpdateRequest(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str | None = None
    blocks_writes: bool | None = None
    announcement_text: str | None = None


class MaintenanceWindowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    starts_at: datetime
    ends_at: datetime
    reason: str | None
    blocks_writes: bool
    announcement_text: str | None
    status: MaintenanceWindowStatus
    scheduled_by: UUID | None
    enabled_at: datetime | None
    disabled_at: datetime | None
    disable_failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class MaintenanceWindowEnableRequest(BaseModel):
    reason: str | None = None


class MaintenanceWindowDisableRequest(BaseModel):
    disable_kind: Literal["manual", "scheduled", "failed"] = "manual"
    reason: str | None = None


class CapacityRecommendation(BaseModel):
    action: str
    link: str
    reason: str


class CapacitySignalResponse(BaseModel):
    resource_class: str
    historical_trend: list[dict[str, Any]] = Field(default_factory=list)
    projection: dict[str, Any] | None = None
    saturation_horizon: dict[str, Any] | None = None
    confidence: CapacityConfidence = CapacityConfidence.insufficient_history
    recommendation: CapacityRecommendation | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UpgradeRuntimeVersion(BaseModel):
    runtime_id: str
    version: str
    status: str
    coexistence_until: datetime | None = None


class UpgradeStatusResponse(BaseModel):
    runtime_versions: list[UpgradeRuntimeVersion] = Field(default_factory=list)
    documentation_links: dict[str, str] = Field(
        default_factory=lambda: {
            "failover": "/docs/runbooks/failover.md",
            "zero_downtime_upgrade": "/docs/runbooks/zero-downtime-upgrade.md",
            "active_active_considerations": "/docs/runbooks/active-active-considerations.md",
        }
    )


def validate_constant_sets() -> None:
    assert {item.value for item in RegionRole} == set(REGION_ROLES)
    assert {item.value for item in ReplicationComponent} == set(REPLICATION_COMPONENTS)
    assert {item.value for item in ReplicationHealth} == set(REPLICATION_HEALTH)
    assert {item.value for item in FailoverPlanRunKind} == set(FAILOVER_PLAN_RUN_KINDS)
    assert {item.value for item in FailoverPlanRunOutcome} == set(FAILOVER_PLAN_RUN_OUTCOMES)
    assert {item.value for item in MaintenanceWindowStatus} == set(MAINTENANCE_STATUSES)
