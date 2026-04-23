from __future__ import annotations

from datetime import datetime
from platform.context_engineering.models import (
    AbTestStatus,
    CompactionStrategyType,
    ContextSourceType,
    CorrelationClassification,
    ProfileAssignmentLevel,
)
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_strings(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [item.strip() for item in values if item.strip()]


class ContextProvenanceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=1)
    timestamp: datetime
    authority_score: float = Field(ge=0.0, le=1.0)
    policy_justification: str = Field(min_length=1)
    action: Literal["included", "excluded"] = "included"
    exclusion_policy_id: UUID | None = None

    @field_validator("origin", "policy_justification")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class ContextElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source_type: ContextSourceType
    content: str = Field(min_length=1)
    token_count: int = Field(ge=0)
    priority: int = Field(default=50, ge=1, le=100)
    provenance: ContextProvenanceEntry
    data_classification: str = Field(default="public")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content", "data_classification")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.strip()


class ContextQualityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    authority: float = Field(ge=0.0, le=1.0)
    contradiction_density: float = Field(ge=0.0, le=1.0)
    token_efficiency: float = Field(ge=0.0, le=1.0)
    task_brief_coverage: float = Field(ge=0.0, le=1.0)
    aggregate: float = Field(ge=0.0, le=1.0)


class BudgetEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens_step: int = Field(default=8192, ge=1)
    max_tokens_execution: int | None = Field(default=None, ge=1)
    max_tokens_agent: int | None = Field(default=None, ge=1)
    max_cost_step: float | None = Field(default=None, ge=0.0)
    max_sources: int = Field(default=9, ge=1)


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ContextSourceType
    priority: int = Field(default=50, ge=1, le=100)
    enabled: bool = True
    max_elements: int = Field(default=10, ge=1, le=100)


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    source_config: list[SourceConfig] = Field(default_factory=list)
    budget_config: BudgetEnvelope = Field(default_factory=BudgetEnvelope)
    compaction_strategies: list[CompactionStrategyType] = Field(
        default_factory=lambda: [
            CompactionStrategyType.relevance_truncation,
            CompactionStrategyType.priority_eviction,
            CompactionStrategyType.semantic_deduplication,
        ]
    )
    quality_weights: dict[str, float] = Field(default_factory=dict)
    privacy_overrides: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ProfileResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_default: bool
    source_config: list[SourceConfig]
    budget_config: BudgetEnvelope
    compaction_strategies: list[CompactionStrategyType]
    quality_weights: dict[str, float]
    privacy_overrides: dict[str, Any]
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]
    total: int


class ProfileAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_level: ProfileAssignmentLevel
    agent_fqn: str | None = None
    role_type: str | None = None

    @field_validator("agent_fqn", "role_type")
    @classmethod
    def normalize_assignment_values(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_assignment(self) -> ProfileAssignmentCreate:
        if self.assignment_level is ProfileAssignmentLevel.agent and not self.agent_fqn:
            raise ValueError("agent_fqn is required for agent-level assignments")
        if self.assignment_level is ProfileAssignmentLevel.role_type and not self.role_type:
            raise ValueError("role_type is required for role-type assignments")
        if self.assignment_level is ProfileAssignmentLevel.workspace:
            self.agent_fqn = None
            self.role_type = None
        return self


class ProfileAssignmentResponse(BaseModel):
    id: UUID
    profile_id: UUID
    assignment_level: ProfileAssignmentLevel
    agent_fqn: str | None
    role_type: str | None
    workspace_id: UUID
    created_at: datetime


class ProfileAssignmentListResponse(BaseModel):
    items: list[ProfileAssignmentResponse]
    total: int


class ContextBundle(BaseModel):
    assembly_id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    elements: list[ContextElement]
    quality_score: float = Field(ge=0.0, le=1.0)
    quality_subscores: dict[str, float]
    token_count: int = Field(ge=0)
    compaction_applied: bool
    flags: list[str]
    profile_id: UUID | None = None
    ab_test_id: UUID | None = None
    ab_test_group: str | None = None


class AssemblyRecordResponse(BaseModel):
    id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    profile_id: UUID | None
    quality_score_pre: float
    quality_score_post: float
    token_count_pre: int
    token_count_post: int
    sources_queried: list[str]
    sources_available: list[str]
    compaction_applied: bool
    compaction_actions: list[dict[str, Any]]
    privacy_exclusions: list[dict[str, Any]]
    provenance_chain: list[dict[str, Any]]
    bundle_storage_key: str | None
    ab_test_id: UUID | None
    ab_test_group: str | None
    flags: list[str]
    workspace_id: UUID
    created_at: datetime


class AssemblyRecordListResponse(BaseModel):
    items: list[AssemblyRecordResponse]
    total: int
    limit: int
    offset: int


class DriftAlertResponse(BaseModel):
    id: UUID
    agent_fqn: str
    workspace_id: UUID
    historical_mean: float
    historical_stddev: float
    recent_mean: float
    degradation_delta: float
    analysis_window_days: int
    suggested_actions: list[str]
    resolved_at: datetime | None
    created_at: datetime


class DriftAlertListResponse(BaseModel):
    items: list[DriftAlertResponse]
    total: int
    limit: int
    offset: int


class AbTestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    control_profile_id: UUID
    variant_profile_id: UUID
    target_agent_fqn: str | None = None

    @field_validator("name", "target_agent_fqn")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AbTestResponse(BaseModel):
    id: UUID
    name: str
    status: AbTestStatus
    control_profile_id: UUID
    variant_profile_id: UUID
    target_agent_fqn: str | None
    control_assembly_count: int
    variant_assembly_count: int
    control_quality_mean: float | None
    variant_quality_mean: float | None
    control_token_mean: float | None
    variant_token_mean: float | None
    started_at: datetime
    ended_at: datetime | None
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime


class AbTestListResponse(BaseModel):
    items: list[AbTestResponse]
    total: int
    limit: int
    offset: int


class CorrelationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_fqn: str
    dimension: str
    performance_metric: str
    window_start: datetime
    window_end: datetime
    coefficient: float | None
    classification: CorrelationClassification | str
    data_point_count: int
    computed_at: datetime
    created_at: datetime
    updated_at: datetime


class CorrelationFleetResponse(BaseModel):
    items: list[CorrelationResultResponse]
    total: int


class CorrelationRecomputeRequest(BaseModel):
    agent_fqn: str | None = None
    window_days: int = Field(default=30, ge=1)
