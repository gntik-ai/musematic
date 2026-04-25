from __future__ import annotations

from datetime import datetime
from platform.trust.models import (
    CertificationStatus,
    EvidenceType,
    GuardrailLayer,
    OJEVerdictType,
    RecertificationTriggerStatus,
    RecertificationTriggerType,
    TrustTierName,
)
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRefCreate(BaseModel):
    evidence_type: EvidenceType
    source_ref_type: str = Field(min_length=1, max_length=255)
    source_ref_id: str = Field(min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=4000)
    storage_ref: str | None = Field(default=None, max_length=1024)


class EvidenceRefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_type: EvidenceType
    source_ref_type: str
    source_ref_id: str
    summary: str | None
    storage_ref: str | None
    created_at: datetime


class CertificationCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=255)
    agent_fqn: str = Field(min_length=1, max_length=512)
    agent_revision_id: str = Field(min_length=1, max_length=255)
    data_categories: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class CertificationRevoke(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CertificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: str
    agent_fqn: str
    agent_revision_id: str
    status: CertificationStatus
    issued_by: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    superseded_by_id: UUID | None
    external_certifier_id: UUID | None = None
    reassessment_schedule: str | None = None
    evidence_refs: list[EvidenceRefResponse] = Field(default_factory=list)


class CertificationListResponse(BaseModel):
    items: list[CertificationResponse]
    total: int


class TrustTierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    agent_fqn: str
    tier: TrustTierName
    trust_score: float
    certification_component: float
    guardrail_component: float
    behavioral_component: float
    last_computed_at: datetime | None


class TrustSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: str
    signal_type: str
    score_contribution: float
    source_type: str
    source_id: str
    workspace_id: str | None
    created_at: datetime


class TrustSignalListResponse(BaseModel):
    items: list[TrustSignalResponse]
    total: int
    page: int
    page_size: int


class GuardrailEvaluationRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=255)
    agent_fqn: str = Field(min_length=1, max_length=512)
    execution_id: str | None = Field(default=None, max_length=255)
    interaction_id: str | None = Field(default=None, max_length=255)
    workspace_id: str = Field(min_length=1, max_length=255)
    layer: GuardrailLayer
    payload: dict[str, Any] = Field(default_factory=dict)


class GuardrailEvaluationResponse(BaseModel):
    allowed: bool
    layer: GuardrailLayer
    policy_basis: str | None = None
    blocked_action_id: UUID | None = None


class GuardrailPipelineConfigCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    fleet_id: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class GuardrailPipelineConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    fleet_id: str | None
    config: dict[str, Any]
    is_active: bool
    created_at: datetime


class BlockedActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: str
    agent_fqn: str
    layer: GuardrailLayer
    policy_basis: str
    policy_basis_detail: str | None
    input_context_preview: str | None
    execution_id: str | None
    interaction_id: str | None
    workspace_id: str | None
    created_at: datetime


class BlockedActionsListResponse(BaseModel):
    items: list[BlockedActionResponse]
    total: int
    page: int
    page_size: int


class PreScreenRequest(BaseModel):
    content: str
    context_type: str = Field(default="input", max_length=64)


class PreScreenResponse(BaseModel):
    blocked: bool
    matched_rule: str | None = None
    passed_to_full_pipeline: bool
    latency_ms: float | None = None
    rule_set_version: str | None = None


class RecertificationTriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: str
    agent_revision_id: str
    trigger_type: RecertificationTriggerType
    status: RecertificationTriggerStatus
    originating_event_type: str | None
    originating_event_id: str | None
    created_at: datetime
    processed_at: datetime | None
    new_certification_id: UUID | None


class RecertificationTriggerListResponse(BaseModel):
    items: list[RecertificationTriggerResponse]
    total: int


class ATEConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    test_scenarios: list[dict[str, Any]] = Field(min_length=1)
    golden_dataset_ref: str | None = Field(default=None, max_length=1024)
    scoring_config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class ATEConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    name: str
    version: int
    description: str | None
    is_active: bool
    test_scenarios: list[dict[str, Any]]
    golden_dataset_ref: str | None
    scoring_config: dict[str, Any]
    timeout_seconds: int
    created_at: datetime


class ATEConfigListResponse(BaseModel):
    items: list[ATEConfigResponse]
    total: int


class ATERunRequest(BaseModel):
    ate_config_id: UUID
    certification_id: UUID


class ATERunResponse(BaseModel):
    simulation_id: str
    ate_config_id: str
    certification_id: str
    status: str


class OJEPipelineConfigCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    fleet_id: str | None = Field(default=None, max_length=255)
    observer_fqns: list[str] = Field(min_length=1)
    judge_fqns: list[str] = Field(min_length=1)
    enforcer_fqns: list[str] = Field(min_length=1)
    policy_refs: list[str] = Field(default_factory=list)
    is_active: bool = True


class OJEPipelineConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    fleet_id: str | None
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_refs: list[str]
    is_active: bool
    created_at: datetime


class OJEPipelineConfigListResponse(BaseModel):
    items: list[OJEPipelineConfigResponse]
    total: int


class JudgeVerdictEvent(BaseModel):
    pipeline_config_id: str
    observer_signal_id: str
    judge_fqn: str
    verdict: OJEVerdictType
    reasoning: str
    policy_basis: str
    enforcer_action_taken: str | None = None


class CircuitBreakerConfigCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    agent_id: str | None = Field(default=None, max_length=255)
    fleet_id: str | None = Field(default=None, max_length=255)
    failure_threshold: int = Field(default=5, ge=0, le=1000)
    time_window_seconds: int = Field(default=600, ge=60, le=86400)
    tripped_ttl_seconds: int = Field(default=3600, ge=60, le=604800)
    enabled: bool = True


class CircuitBreakerConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    agent_id: str | None
    fleet_id: str | None
    failure_threshold: int
    time_window_seconds: int
    tripped_ttl_seconds: int
    enabled: bool
    created_at: datetime


class CircuitBreakerConfigListResponse(BaseModel):
    items: list[CircuitBreakerConfigResponse]
    total: int


class CircuitBreakerStatusResponse(BaseModel):
    agent_id: str
    tripped: bool
    failure_count: int
    threshold: int
    time_window_seconds: int


class PreScreenerRuleDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    pattern: str = Field(min_length=1)
    type: str = Field(default="regex", max_length=64)
    action: str = Field(default="block", max_length=64)


class PreScreenerRuleSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rules: list[PreScreenerRuleDefinition] = Field(min_length=1)


class PreScreenerRuleSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    name: str
    description: str | None
    is_active: bool
    rules_ref: str
    rule_count: int
    activated_at: datetime | None
    created_at: datetime


class PreScreenerRuleSetListResponse(BaseModel):
    items: list[PreScreenerRuleSetResponse]
    total: int


class PrivacyAssessmentRequest(BaseModel):
    context_assembly_id: str = Field(min_length=1, max_length=255)
    workspace_id: str = Field(min_length=1, max_length=255)
    agent_id: str = Field(min_length=1, max_length=255)


class PrivacyAssessmentResponse(BaseModel):
    compliant: bool
    violations: list[dict[str, str]] = Field(default_factory=list)
    blocked: bool
