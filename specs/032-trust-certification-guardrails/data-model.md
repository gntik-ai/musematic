# Data Model: Trust, Certification, and Guardrails

**Feature**: 032-trust-certification-guardrails  
**Date**: 2026-04-12  
**Type**: Backend — Python/SQLAlchemy models, Pydantic schemas, service interfaces

---

## SQLAlchemy Models

All models inherit `Base` then behavior mixins from `common/models/mixins.py` in the declared order: `UUIDMixin`, `TimestampMixin`, then additional mixins as required. All models are in `apps/control-plane/src/platform/trust/models.py`.

```python
from platform.common.models.base import Base
from platform.common.models.mixins import (
    UUIDMixin, TimestampMixin, WorkspaceScopedMixin, AuditMixin
)
from sqlalchemy import (
    Column, String, Text, Numeric, Integer, Boolean,
    ForeignKey, DateTime, Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
import enum

class CertificationStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"

class EvidenceType(str, enum.Enum):
    PACKAGE_VALIDATION = "package_validation"
    TEST_RESULTS = "test_results"
    POLICY_CHECK = "policy_check"
    GUARDRAIL_OUTCOMES = "guardrail_outcomes"
    BEHAVIORAL_REGRESSION = "behavioral_regression"
    ATE_RESULTS = "ate_results"

class TrustTierName(str, enum.Enum):
    CERTIFIED = "certified"
    PROVISIONAL = "provisional"
    UNTRUSTED = "untrusted"

class RecertificationTriggerType(str, enum.Enum):
    REVISION_CHANGED = "revision_changed"
    POLICY_CHANGED = "policy_changed"
    EXPIRY_APPROACHING = "expiry_approaching"
    CONFORMANCE_FAILED = "conformance_failed"

class RecertificationTriggerStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    DEDUPLICATED = "deduplicated"

class GuardrailLayer(str, enum.Enum):
    INPUT_SANITIZATION = "input_sanitization"
    PROMPT_INJECTION = "prompt_injection"
    OUTPUT_MODERATION = "output_moderation"
    TOOL_CONTROL = "tool_control"
    MEMORY_WRITE = "memory_write"
    ACTION_COMMIT = "action_commit"

class OJEVerdictType(str, enum.Enum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


class TrustCertification(Base, UUIDMixin, TimestampMixin, AuditMixin):
    """Certification bound to a specific agent revision."""
    __tablename__ = "trust_certifications"

    agent_id = Column(String, nullable=False, index=True)
    agent_fqn = Column(String, nullable=False)
    agent_revision_id = Column(String, nullable=False)
    status = Column(Enum(CertificationStatus), nullable=False, default=CertificationStatus.PENDING)
    issued_by = Column(String, nullable=False)          # user_id of certifier
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    superseded_by_id = Column(String, ForeignKey("trust_certifications.id"), nullable=True)

    evidence_refs = relationship("TrustCertificationEvidenceRef", back_populates="certification")

    __table_args__ = (
        Index("ix_trust_certifications_agent_status", "agent_id", "status"),
        Index("ix_trust_certifications_revision", "agent_revision_id"),
    )


class TrustCertificationEvidenceRef(Base, UUIDMixin, TimestampMixin):
    """Link from a certification to a piece of evidence."""
    __tablename__ = "trust_certification_evidence_refs"

    certification_id = Column(String, ForeignKey("trust_certifications.id"), nullable=False, index=True)
    evidence_type = Column(Enum(EvidenceType), nullable=False)
    source_ref_type = Column(String, nullable=False)    # "ate_run", "test_result_id", "policy_check_id", etc.
    source_ref_id = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    storage_ref = Column(String, nullable=True)          # MinIO key for large payload

    certification = relationship("TrustCertification", back_populates="evidence_refs")


class TrustTier(Base, UUIDMixin, TimestampMixin):
    """Trust tier and computed score for an agent."""
    __tablename__ = "trust_tiers"

    agent_id = Column(String, nullable=False, unique=True, index=True)
    agent_fqn = Column(String, nullable=False)
    tier = Column(Enum(TrustTierName), nullable=False, default=TrustTierName.UNTRUSTED)
    trust_score = Column(Numeric(5, 4), nullable=False, default=0.0)   # 0.0000 to 1.0000
    certification_component = Column(Numeric(5, 4), nullable=False, default=0.0)
    guardrail_component = Column(Numeric(5, 4), nullable=False, default=0.0)
    behavioral_component = Column(Numeric(5, 4), nullable=False, default=0.0)
    last_computed_at = Column(DateTime(timezone=True), nullable=True)


class TrustSignal(Base, UUIDMixin, TimestampMixin):
    """Individual data point contributing to an agent's trust score."""
    __tablename__ = "trust_signals"

    agent_id = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False)        # "certification_activated", "guardrail_blocked", etc.
    score_contribution = Column(Numeric(5, 4), nullable=False)
    source_type = Column(String, nullable=False)        # "certification", "guardrail_block", "ate_run"
    source_id = Column(String, nullable=False)
    workspace_id = Column(String, nullable=True)

    proof_links = relationship("TrustProofLink", back_populates="signal")

    __table_args__ = (
        Index("ix_trust_signals_agent_type", "agent_id", "signal_type"),
    )


class TrustProofLink(Base, UUIDMixin, TimestampMixin):
    """Auditable link between a trust signal and its source event."""
    __tablename__ = "trust_proof_links"

    signal_id = Column(String, ForeignKey("trust_signals.id"), nullable=False, index=True)
    proof_type = Column(String, nullable=False)         # "certification", "guardrail_event", "ate_result"
    proof_reference_type = Column(String, nullable=False)
    proof_reference_id = Column(String, nullable=False)

    signal = relationship("TrustSignal", back_populates="proof_links")


class TrustRecertificationTrigger(Base, UUIDMixin, TimestampMixin):
    """Records conditions that require an agent to be recertified."""
    __tablename__ = "trust_recertification_triggers"

    agent_id = Column(String, nullable=False, index=True)
    agent_revision_id = Column(String, nullable=False)
    trigger_type = Column(Enum(RecertificationTriggerType), nullable=False)
    originating_event_type = Column(String, nullable=True)
    originating_event_id = Column(String, nullable=True)
    original_certification_id = Column(String, ForeignKey("trust_certifications.id"), nullable=True)
    status = Column(Enum(RecertificationTriggerStatus), nullable=False, default=RecertificationTriggerStatus.PENDING)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    new_certification_id = Column(String, ForeignKey("trust_certifications.id"), nullable=True)

    __table_args__ = (
        # Deduplication: one pending trigger per agent+revision+type
        UniqueConstraint("agent_id", "agent_revision_id", "trigger_type",
                         "status", name="uq_recert_trigger_pending",
                         postgresql_where="status = 'pending'"),
    )


class TrustBlockedActionRecord(Base, UUIDMixin, TimestampMixin):
    """Audit record for every action blocked by the guardrail pipeline."""
    __tablename__ = "trust_blocked_action_records"

    agent_id = Column(String, nullable=False, index=True)
    agent_fqn = Column(String, nullable=False)
    layer = Column(Enum(GuardrailLayer), nullable=False)
    policy_basis = Column(String, nullable=False)       # policy_id or rule name
    policy_basis_detail = Column(Text, nullable=True)
    input_context_hash = Column(String(64), nullable=False)    # SHA-256 hex
    input_context_preview = Column(String(500), nullable=True) # first 500 chars
    execution_id = Column(String, nullable=True, index=True)
    interaction_id = Column(String, nullable=True)
    workspace_id = Column(String, nullable=True, index=True)

    __table_args__ = (
        Index("ix_trust_blocked_agent_layer", "agent_id", "layer"),
    )


class TrustATEConfiguration(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Versioned ATE configuration for certification testing."""
    __tablename__ = "trust_ate_configurations"

    name = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    test_scenarios = Column(JSON, nullable=False)       # list of scenario definitions
    golden_dataset_ref = Column(String, nullable=True)  # MinIO key
    scoring_config = Column(JSON, nullable=False)
    timeout_seconds = Column(Integer, nullable=False, default=3600)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", "version", name="uq_ate_config_version"),
    )


class TrustGuardrailPipelineConfig(Base, UUIDMixin, TimestampMixin):
    """Per-workspace or per-fleet guardrail pipeline configuration."""
    __tablename__ = "trust_guardrail_pipeline_configs"

    workspace_id = Column(String, nullable=False, index=True)
    fleet_id = Column(String, nullable=True, index=True)   # null = workspace-wide
    config = Column(JSON, nullable=False)   # {layer_name: {enabled, params}}
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        # One active config per workspace+fleet combination
        UniqueConstraint("workspace_id", "fleet_id", "is_active",
                         name="uq_guardrail_config_active"),
    )


class TrustOJEPipelineConfig(Base, UUIDMixin, TimestampMixin):
    """Observer-Judge-Enforcer pipeline configuration per workspace or fleet."""
    __tablename__ = "trust_oje_pipeline_configs"

    workspace_id = Column(String, nullable=False, index=True)
    fleet_id = Column(String, nullable=True, index=True)
    observer_fqns = Column(JSON, nullable=False)    # list of agent FQNs
    judge_fqns = Column(JSON, nullable=False)
    enforcer_fqns = Column(JSON, nullable=False)
    policy_refs = Column(JSON, nullable=False)      # list of policy IDs to evaluate against
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "fleet_id", "is_active",
                         name="uq_oje_config_active"),
    )


class TrustCircuitBreakerConfig(Base, UUIDMixin, TimestampMixin):
    """Circuit breaker configuration per agent or fleet."""
    __tablename__ = "trust_circuit_breaker_configs"

    workspace_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=True)    # null = fleet-wide
    fleet_id = Column(String, nullable=True)    # null = agent-specific
    failure_threshold = Column(Integer, nullable=False, default=5)
    time_window_seconds = Column(Integer, nullable=False, default=600)
    enabled = Column(Boolean, nullable=False, default=True)


class TrustSafetyPreScreenerRuleSet(Base, UUIDMixin, TimestampMixin):
    """Versioned pre-screener rule set metadata."""
    __tablename__ = "trust_prescreener_rule_sets"

    version = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    rules_ref = Column(String, nullable=False)          # MinIO key: trust-evidence/prescreener/{version}/rules.json
    rule_count = Column(Integer, nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_prescreener_active", "is_active"),
    )
```

---

## Pydantic Schemas

```python
# apps/control-plane/src/platform/trust/schemas.py

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

# --- Certification ---

class CertificationCreate(BaseModel):
    agent_id: str
    agent_fqn: str
    agent_revision_id: str
    expires_at: Optional[datetime] = None

class CertificationActivate(BaseModel):
    pass  # no body, action implied by endpoint

class CertificationRevoke(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

class EvidenceRefCreate(BaseModel):
    evidence_type: EvidenceType
    source_ref_type: str
    source_ref_id: str
    summary: Optional[str] = None

class CertificationResponse(BaseModel):
    id: UUID
    agent_id: str
    agent_fqn: str
    agent_revision_id: str
    status: CertificationStatus
    issued_by: str
    created_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    superseded_by_id: Optional[UUID]
    evidence_refs: List[EvidenceRefResponse]

    model_config = {"from_attributes": True}

class EvidenceRefResponse(BaseModel):
    id: UUID
    evidence_type: EvidenceType
    source_ref_type: str
    source_ref_id: str
    summary: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

# --- Trust Tier ---

class TrustTierResponse(BaseModel):
    agent_id: str
    agent_fqn: str
    tier: TrustTierName
    trust_score: float
    certification_component: float
    guardrail_component: float
    behavioral_component: float
    last_computed_at: Optional[datetime]

    model_config = {"from_attributes": True}

# --- Guardrail ---

class GuardrailEvaluationRequest(BaseModel):
    agent_id: str
    agent_fqn: str
    execution_id: Optional[str] = None
    interaction_id: Optional[str] = None
    workspace_id: str
    layer: GuardrailLayer
    payload: Dict[str, Any]         # layer-specific content

class GuardrailEvaluationResponse(BaseModel):
    allowed: bool
    layer: GuardrailLayer
    policy_basis: Optional[str] = None
    blocked_action_id: Optional[UUID] = None

class BlockedActionResponse(BaseModel):
    id: UUID
    agent_id: str
    layer: GuardrailLayer
    policy_basis: str
    blocked_at: datetime

    model_config = {"from_attributes": True}

class BlockedActionsListResponse(BaseModel):
    items: List[BlockedActionResponse]
    total: int

# --- Pre-Screener ---

class PreScreenRequest(BaseModel):
    content: str
    context_type: str = "input"    # "input" | "tool_output"

class PreScreenResponse(BaseModel):
    blocked: bool
    matched_rule: Optional[str] = None   # rule name if blocked
    passed_to_full_pipeline: bool

# --- Recertification ---

class RecertificationTriggerResponse(BaseModel):
    id: UUID
    agent_id: str
    trigger_type: RecertificationTriggerType
    status: RecertificationTriggerStatus
    originating_event_type: Optional[str]
    originating_event_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

# --- ATE ---

class ATEConfigCreate(BaseModel):
    name: str = Field(max_length=255)
    description: Optional[str] = None
    test_scenarios: List[Dict[str, Any]] = Field(min_length=1)
    golden_dataset_ref: Optional[str] = None
    scoring_config: Dict[str, Any]
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)

class ATERunRequest(BaseModel):
    ate_config_id: str
    certification_id: str

class ATERunResponse(BaseModel):
    simulation_id: str
    ate_config_id: str
    certification_id: str
    status: str    # "started" | "running" | "completed" | "timed_out"

# --- OJE Pipeline ---

class OJEPipelineConfigCreate(BaseModel):
    workspace_id: str
    fleet_id: Optional[str] = None
    observer_fqns: List[str] = Field(min_length=1)
    judge_fqns: List[str] = Field(min_length=1)
    enforcer_fqns: List[str] = Field(min_length=1)
    policy_refs: List[str]

class OJEPipelineConfigResponse(BaseModel):
    id: UUID
    workspace_id: str
    fleet_id: Optional[str]
    observer_fqns: List[str]
    judge_fqns: List[str]
    enforcer_fqns: List[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class JudgeVerdictEvent(BaseModel):
    pipeline_config_id: str
    observer_signal_id: str
    judge_fqn: str
    verdict: OJEVerdictType
    reasoning: str
    policy_basis: str
    enforcer_action_taken: Optional[str] = None

# --- Circuit Breaker ---

class CircuitBreakerConfigCreate(BaseModel):
    workspace_id: str
    agent_id: Optional[str] = None
    fleet_id: Optional[str] = None
    failure_threshold: int = Field(default=5, ge=0, le=1000)
    time_window_seconds: int = Field(default=600, ge=60, le=86400)

class CircuitBreakerStatusResponse(BaseModel):
    agent_id: str
    tripped: bool
    failure_count: int
    threshold: int
    time_window_seconds: int

# --- Pre-Screener Rule Set ---

class PreScreenerRuleSetCreate(BaseModel):
    name: str = Field(max_length=255)
    description: Optional[str] = None
    rules: List[Dict[str, Any]]     # list of {name, pattern, type, action}

class PreScreenerRuleSetResponse(BaseModel):
    id: UUID
    version: int
    name: str
    is_active: bool
    rule_count: int
    activated_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}

# --- Privacy Assessment ---

class PrivacyAssessmentRequest(BaseModel):
    context_assembly_id: str
    workspace_id: str
    agent_id: str

class PrivacyAssessmentResponse(BaseModel):
    compliant: bool
    violations: List[Dict[str, str]]   # [{rule, detail}]
    blocked: bool
```

---

## Service Interfaces

```python
# apps/control-plane/src/platform/trust/service.py

class CertificationService:
    async def create(self, data: CertificationCreate, issuer_id: str) -> TrustCertification: ...
    async def get(self, cert_id: str) -> TrustCertification: ...
    async def list_for_agent(self, agent_id: str) -> list[TrustCertification]: ...
    async def activate(self, cert_id: str, actor_id: str) -> TrustCertification: ...
    async def revoke(self, cert_id: str, reason: str, actor_id: str) -> TrustCertification: ...
    async def add_evidence(self, cert_id: str, data: EvidenceRefCreate) -> TrustCertificationEvidenceRef: ...
    async def expire_stale(self) -> int: ...         # APScheduler job

class TrustTierService:
    async def get_tier(self, agent_id: str) -> TrustTier: ...
    async def recompute(self, agent_id: str) -> TrustTier: ...
    async def handle_trust_event(self, event: dict) -> None: ...  # Kafka consumer handler

class GuardrailPipelineService:
    async def evaluate_full_pipeline(self, request: GuardrailEvaluationRequest) -> GuardrailEvaluationResponse: ...
    async def evaluate_layer(self, layer: GuardrailLayer, payload: dict, context: dict) -> GuardrailEvaluationResponse: ...
    async def record_blocked_action(self, context: dict, layer: GuardrailLayer, policy_basis: str) -> TrustBlockedActionRecord: ...

class SafetyPreScreenerService:
    async def screen(self, content: str, context_type: str) -> PreScreenResponse: ...
    async def load_active_rules(self) -> None: ...    # called on startup + Kafka event
    async def activate_rule_set(self, rule_set_id: str) -> None: ...

class OJEPipelineService:
    async def configure_pipeline(self, data: OJEPipelineConfigCreate) -> TrustOJEPipelineConfig: ...
    async def get_pipeline_config(self, workspace_id: str, fleet_id: str | None) -> TrustOJEPipelineConfig: ...
    async def process_observation(self, signal: dict, pipeline_config_id: str) -> None: ...
    async def execute_enforcement(self, verdict: JudgeVerdictEvent) -> None: ...

class RecertificationService:
    async def create_trigger(self, agent_id: str, revision_id: str,
                              trigger_type: RecertificationTriggerType,
                              originating_event: dict) -> TrustRecertificationTrigger | None: ...
    async def process_pending_triggers(self) -> int: ...   # APScheduler / worker

class CircuitBreakerService:
    async def record_failure(self, agent_id: str, workspace_id: str) -> CircuitBreakerStatusResponse: ...
    async def is_tripped(self, agent_id: str) -> bool: ...
    async def reset(self, agent_id: str) -> None: ...

class ATEService:
    async def create_config(self, workspace_id: str, data: ATEConfigCreate) -> TrustATEConfiguration: ...
    async def run(self, request: ATERunRequest) -> ATERunResponse: ...
    async def handle_simulation_completed(self, event: dict) -> None: ...  # Kafka consumer

class PrivacyAssessmentService:
    async def assess(self, request: PrivacyAssessmentRequest) -> PrivacyAssessmentResponse: ...
```

---

## Redis Key Patterns

| Key pattern | Type | TTL | Purpose |
|---|---|---|---|
| `trust:cb:{agent_id}` | Sorted Set | `time_window_seconds` | Circuit breaker sliding-window failure timestamps |
| `trust:cb:tripped:{agent_id}` | String | configurable (e.g., 3600s) | Circuit breaker tripped flag |
| `trust:prescreener:active_version` | String | none (permanent) | Active pre-screener rule set version number |
| `trust:prescreener:rules:{version}` | String (serialized) | none | Compiled rules cache for pre-screener |

---

## Kafka Events

All events use the canonical `EventEnvelope` Pydantic model from `common/events/envelope.py`.

**Produced on `trust.events`**:

```python
# event_type values
"certification.created"
"certification.activated"
"certification.revoked"
"certification.expired"
"certification.superseded"
"trust_tier.updated"       # payload: {agent_id, tier, trust_score}
"guardrail.blocked"        # payload: {agent_id, layer, policy_basis, blocked_action_id}
"circuit_breaker.activated" # payload: {agent_id, failure_count, threshold}
"recertification.triggered" # payload: {agent_id, trigger_type, new_certification_id}
"prescreener.rule_set.activated" # payload: {version, rule_count}
```

**Consumed from**:
- `registry.events` → event_type `agent_revision.published` → RecertificationService
- `policy.events` → event_type `policy.updated` → RecertificationService
- `workflow.runtime` → event_type `execution.guardrail_failed` → CircuitBreakerService
- `simulation.events` → event_type `simulation.completed` → ATEService

---

## Migration

**File**: `apps/control-plane/migrations/versions/032_trust_certifications.py`

Creates all 12 tables in dependency order:
1. `trust_certifications`
2. `trust_certification_evidence_refs`
3. `trust_tiers`
4. `trust_signals`
5. `trust_proof_links`
6. `trust_recertification_triggers`
7. `trust_blocked_action_records`
8. `trust_ate_configurations`
9. `trust_guardrail_pipeline_configs`
10. `trust_oje_pipeline_configs`
11. `trust_circuit_breaker_configs`
12. `trust_prescreener_rule_sets`

---

## Source File Structure

```text
apps/control-plane/src/platform/trust/
├── __init__.py
├── models.py                    # 12 SQLAlchemy models + enums
├── schemas.py                   # All Pydantic schemas
├── repository.py                # Async SQLAlchemy queries
├── service.py                   # CertificationService, TrustTierService
├── guardrail_pipeline.py        # GuardrailPipelineService (6 layers)
├── prescreener.py               # SafetyPreScreenerService (rule-based, <10ms)
├── trust_tier.py                # TrustTierService score computation
├── recertification.py           # RecertificationService + Kafka handlers
├── circuit_breaker.py           # CircuitBreakerService (Redis sorted set)
├── oje_pipeline.py              # OJEPipelineService (Observer-Judge-Enforcer)
├── ate_service.py               # ATEService (SimulationController gRPC)
├── privacy_assessment.py        # PrivacyAssessmentService (delegates to policies/)
├── router.py                    # FastAPI router (all trust endpoints)
├── events.py                    # Kafka event types and publishers
├── exceptions.py                # TrustError hierarchy
└── dependencies.py              # FastAPI dependency injection

apps/control-plane/migrations/versions/
└── 032_trust_certifications.py  # All 12 tables
```
