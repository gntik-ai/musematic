# Data Model: Policy and Governance Engine

**Branch**: `028-policy-governance-engine` | **Date**: 2026-04-12 | **Phase**: 1

Backend Python service. Documents SQLAlchemy models, Pydantic schemas, service signatures, and Kafka event payloads.

---

## SQLAlchemy Models

```python
# apps/control-plane/src/platform/policies/models.py

from sqlalchemy import Column, String, Text, Integer, Boolean, Enum, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from platform.common.models.base import Base
from platform.common.models.mixins import UUIDMixin, TimestampMixin, AuditMixin
import enum


class PolicyScopeType(str, enum.Enum):
    GLOBAL = "global"
    DEPLOYMENT = "deployment"
    WORKSPACE = "workspace"
    AGENT = "agent"
    EXECUTION = "execution"


class PolicyStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AttachmentTargetType(str, enum.Enum):
    GLOBAL = "global"
    DEPLOYMENT = "deployment"
    WORKSPACE = "workspace"
    AGENT_REVISION = "agent_revision"
    FLEET = "fleet"
    EXECUTION = "execution"


class EnforcementComponent(str, enum.Enum):
    TOOL_GATEWAY = "tool_gateway"
    MEMORY_WRITE_GATE = "memory_write_gate"
    SANITIZER = "sanitizer"
    VISIBILITY_FILTER = "visibility_filter"


class PolicyPolicy(Base, UUIDMixin, TimestampMixin, AuditMixin):
    """Policy header — mutable pointer to current version."""
    __tablename__ = "policy_policies"

    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    scope_type = Column(Enum(PolicyScopeType), nullable=False, index=True)
    status = Column(Enum(PolicyStatus), nullable=False, default=PolicyStatus.ACTIVE, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # null = global
    current_version_id = Column(UUID(as_uuid=True), ForeignKey("policy_versions.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    updated_by = Column(UUID(as_uuid=True), nullable=False)

    versions = relationship("PolicyVersion", foreign_keys="PolicyVersion.policy_id", back_populates="policy")
    current_version = relationship("PolicyVersion", foreign_keys=[current_version_id])
    attachments = relationship("PolicyAttachment", back_populates="policy")


class PolicyVersion(Base, UUIDMixin, TimestampMixin):
    """Immutable snapshot of policy rules at a point in time."""
    __tablename__ = "policy_versions"

    policy_id = Column(UUID(as_uuid=True), ForeignKey("policy_policies.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    rules = Column(JSONB, nullable=False)
    # rules schema:
    # {
    #   "enforcement_rules": [{
    #     "id": str, "action": "allow|deny|warn|audit",
    #     "tool_patterns": ["calculator", "finance-ops:*"],
    #     "applicable_step_types": ["tool_invocation", "memory_write"],
    #     "log_allowed_invocations": bool
    #   }],
    #   "capability_constraints": [{
    #     "id": str, "capability": str, "condition": dict
    #   }],
    #   "maturity_gate_rules": [{
    #     "min_maturity_level": int, "capability_patterns": [str]
    #   }],
    #   "purpose_scopes": [{
    #     "id": str, "allowed_purposes": [str], "denied_purposes": [str]
    #   }],
    #   "budget_limits": {
    #     "max_tool_invocations_per_execution": int | null,
    #     "max_memory_writes_per_minute": int | null
    #   },
    #   "safety_rules": [{
    #     "id": str, "pattern": str, "action": "block"
    #   }]
    # }
    change_summary = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)

    policy = relationship("PolicyPolicy", foreign_keys=[policy_id], back_populates="versions")
    attachments = relationship("PolicyAttachment", back_populates="policy_version")


class PolicyAttachment(Base, UUIDMixin, TimestampMixin):
    """Binding between a policy version and a target entity."""
    __tablename__ = "policy_attachments"

    policy_id = Column(UUID(as_uuid=True), ForeignKey("policy_policies.id"), nullable=False, index=True)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("policy_versions.id"), nullable=False)
    target_type = Column(Enum(AttachmentTargetType), nullable=False, index=True)
    target_id = Column(String(255), nullable=True)  # null for global scope
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    deactivated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    policy = relationship("PolicyPolicy", back_populates="attachments")
    policy_version = relationship("PolicyVersion", back_populates="attachments")


class PolicyBlockedActionRecord(Base, UUIDMixin, TimestampMixin):
    """Audit record for every blocked or sanitized action."""
    __tablename__ = "policy_blocked_action_records"

    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_fqn = Column(String(512), nullable=False, index=True)
    enforcement_component = Column(Enum(EnforcementComponent), nullable=False, index=True)
    action_type = Column(String(64), nullable=False)  # "tool_invocation", "memory_write", "sanitizer_redaction"
    target = Column(String(512), nullable=False)  # tool_fqn or namespace or secret_type
    block_reason = Column(String(255), nullable=False)
    policy_rule_ref = Column(JSONB, nullable=True)  # {policy_id, version_id, rule_id}
    execution_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)


class PolicyBundleCache(Base, UUIDMixin, TimestampMixin):
    """PostgreSQL-level cache for compiled enforcement bundles (backup to Redis)."""
    __tablename__ = "policy_bundle_cache"

    fingerprint = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hex
    bundle_data = Column(JSONB, nullable=False)
    source_version_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
```

---

## Pydantic Schemas

```python
# apps/control-plane/src/platform/policies/schemas.py

from pydantic import BaseModel, Field, field_validator
from typing import Any
from uuid import UUID
from datetime import datetime
from platform.policies.models import PolicyScopeType, PolicyStatus, AttachmentTargetType


# ── Rule Schemas (embedded in PolicyVersionCreate.rules) ──────────────────────

class EnforcementRuleSchema(BaseModel):
    id: str
    action: str  # "allow" | "deny" | "warn" | "audit"
    tool_patterns: list[str] = Field(default_factory=list)
    applicable_step_types: list[str] = Field(default_factory=list)
    log_allowed_invocations: bool = False


class MaturityGateRuleSchema(BaseModel):
    min_maturity_level: int = Field(ge=0, le=10)
    capability_patterns: list[str]


class BudgetLimitsSchema(BaseModel):
    max_tool_invocations_per_execution: int | None = None
    max_memory_writes_per_minute: int | None = Field(None, ge=0)


class PolicyRulesSchema(BaseModel):
    enforcement_rules: list[EnforcementRuleSchema] = Field(default_factory=list)
    maturity_gate_rules: list[MaturityGateRuleSchema] = Field(default_factory=list)
    purpose_scopes: list[dict[str, Any]] = Field(default_factory=list)
    budget_limits: BudgetLimitsSchema = Field(default_factory=BudgetLimitsSchema)
    safety_rules: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("budget_limits")
    @classmethod
    def validate_budget(cls, v: BudgetLimitsSchema) -> BudgetLimitsSchema:
        if v.max_tool_invocations_per_execution is not None and v.max_tool_invocations_per_execution < 0:
            raise ValueError("Budget limits cannot be negative")
        return v


# ── Policy CRUD Schemas ───────────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scope_type: PolicyScopeType
    workspace_id: UUID | None = None
    rules: PolicyRulesSchema
    change_summary: str | None = None


class PolicyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    rules: PolicyRulesSchema | None = None
    change_summary: str | None = None


class PolicyVersionResponse(BaseModel):
    id: UUID
    policy_id: UUID
    version_number: int
    rules: dict[str, Any]
    change_summary: str | None
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    scope_type: PolicyScopeType
    status: PolicyStatus
    workspace_id: UUID | None
    current_version_id: UUID | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PolicyWithVersionResponse(PolicyResponse):
    current_version: PolicyVersionResponse | None


class PolicyListResponse(BaseModel):
    items: list[PolicyResponse]
    total: int
    page: int
    page_size: int


# ── Attachment Schemas ────────────────────────────────────────────────────────

class PolicyAttachRequest(BaseModel):
    policy_version_id: UUID | None = None  # null = attach current version
    target_type: AttachmentTargetType
    target_id: str | None = None  # null for global scope


class PolicyAttachResponse(BaseModel):
    id: UUID
    policy_id: UUID
    policy_version_id: UUID
    target_type: AttachmentTargetType
    target_id: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Effective Policy / Enforcement Bundle Schemas ─────────────────────────────

class PolicyRuleProvenance(BaseModel):
    rule_id: str
    policy_id: UUID
    version_id: UUID
    scope_level: int
    scope_type: PolicyScopeType
    scope_target_id: str | None


class ResolvedRule(BaseModel):
    rule: dict[str, Any]
    provenance: PolicyRuleProvenance


class PolicyConflict(BaseModel):
    rule_id: str
    winner_scope: PolicyScopeType
    loser_scope: PolicyScopeType
    resolution: str  # "more_specific_scope_wins" | "deny_wins"


class EffectivePolicyResponse(BaseModel):
    agent_id: UUID
    resolved_rules: list[ResolvedRule]
    conflicts: list[PolicyConflict]
    source_policies: list[UUID]  # policy IDs contributing to effective policy


class ValidationManifest(BaseModel):
    source_policy_ids: list[UUID]
    source_version_ids: list[UUID]
    compiled_at: datetime
    fingerprint: str
    warnings: list[str]
    conflicts: list[PolicyConflict]


class EnforcementBundle(BaseModel):
    """Compiled, ready-for-runtime enforcement bundle."""
    fingerprint: str
    allowed_tool_patterns: list[str]
    denied_tool_patterns: list[str]
    maturity_gate_rules: list[MaturityGateRuleSchema]
    allowed_purposes: list[str]
    denied_purposes: list[str]
    allowed_namespaces: list[str]
    budget_limits: BudgetLimitsSchema
    safety_rules: list[dict[str, Any]]
    log_allowed_tools: list[str]  # tools requiring allowed event emission
    manifest: ValidationManifest

    def get_shard(self, step_type: str) -> "EnforcementBundle":
        """Return a task-scoped shard filtered to relevant rules for step_type."""
        ...


# ── Gate Result Schemas ───────────────────────────────────────────────────────

class GateResult(BaseModel):
    allowed: bool
    block_reason: str | None = None
    policy_rule_ref: dict[str, Any] | None = None
    check_latency_ms: float | None = None


class SanitizationResult(BaseModel):
    output: str
    redaction_count: int
    redacted_types: list[str]
```

---

## Service Signatures

```python
# apps/control-plane/src/platform/policies/service.py

class PolicyService:
    async def create_policy(
        self,
        data: PolicyCreate,
        created_by: UUID,
        session: AsyncSession,
    ) -> PolicyPolicy: ...

    async def update_policy(
        self,
        policy_id: UUID,
        data: PolicyUpdate,
        updated_by: UUID,
        session: AsyncSession,
    ) -> PolicyPolicy: ...

    async def archive_policy(
        self,
        policy_id: UUID,
        archived_by: UUID,
        session: AsyncSession,
    ) -> PolicyPolicy: ...

    async def get_policy(
        self,
        policy_id: UUID,
        session: AsyncSession,
    ) -> PolicyPolicy: ...

    async def list_policies(
        self,
        scope_type: PolicyScopeType | None,
        status: PolicyStatus | None,
        workspace_id: UUID | None,
        page: int,
        page_size: int,
        session: AsyncSession,
    ) -> tuple[list[PolicyPolicy], int]: ...

    async def get_version_history(
        self,
        policy_id: UUID,
        session: AsyncSession,
    ) -> list[PolicyVersion]: ...

    async def attach_policy(
        self,
        policy_id: UUID,
        request: PolicyAttachRequest,
        created_by: UUID,
        session: AsyncSession,
    ) -> PolicyAttachment: ...

    async def get_effective_policy(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        session: AsyncSession,
    ) -> EffectivePolicyResponse: ...

    async def get_enforcement_bundle(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        session: AsyncSession,
    ) -> EnforcementBundle:
        """Returns compiled bundle from Redis cache or freshly compiled."""
        ...


# apps/control-plane/src/platform/policies/gateway.py

class ToolGatewayService:
    async def validate_tool_invocation(
        self,
        agent_id: UUID,
        agent_fqn: str,
        tool_fqn: str,
        declared_purpose: str,
        execution_id: UUID | None,
        workspace_id: UUID,
        session: AsyncSession,
    ) -> GateResult: ...

    async def sanitize_tool_output(
        self,
        output: str,
        agent_id: UUID,
        agent_fqn: str,
        tool_fqn: str,
        execution_id: UUID | None,
        session: AsyncSession,
    ) -> SanitizationResult: ...


class MemoryWriteGateService:
    async def validate_memory_write(
        self,
        agent_id: UUID,
        agent_fqn: str,
        target_namespace: str,
        content_hash: str,
        workspace_id: UUID,
        session: AsyncSession,
    ) -> GateResult: ...


# apps/control-plane/src/platform/policies/compiler.py

class GovernanceCompiler:
    def compile_bundle(
        self,
        policy_versions: list[PolicyVersion],
        agent_id: UUID,
        workspace_id: UUID,
    ) -> EnforcementBundle:
        """Synchronous compilation. Raises PolicyCompilationError on invalid input."""
        ...
```

---

## Repository Signatures

```python
# apps/control-plane/src/platform/policies/repository.py

class PolicyRepository:
    async def create(self, session, policy: PolicyPolicy) -> PolicyPolicy: ...
    async def get_by_id(self, session, policy_id: UUID) -> PolicyPolicy | None: ...
    async def list_with_filters(
        self, session, scope_type, status, workspace_id, offset, limit
    ) -> tuple[list[PolicyPolicy], int]: ...
    async def get_versions(self, session, policy_id: UUID) -> list[PolicyVersion]: ...
    async def get_active_attachments_for_target(
        self, session, target_type: AttachmentTargetType, target_id: str
    ) -> list[PolicyAttachment]: ...
    async def get_all_applicable_attachments(
        self, session, agent_id: UUID, workspace_id: UUID, deployment_id: str | None
    ) -> list[PolicyAttachment]:
        """Returns attachments for: agent, workspace, deployment, global — all scopes."""
        ...
    async def create_blocked_action_record(
        self, session, record: PolicyBlockedActionRecord
    ) -> PolicyBlockedActionRecord: ...
    async def get_bundle_cache(self, session, fingerprint: str) -> PolicyBundleCache | None: ...
    async def upsert_bundle_cache(self, session, cache: PolicyBundleCache) -> PolicyBundleCache: ...
```

---

## Kafka Event Payloads

```python
# apps/control-plane/src/platform/policies/events.py
# Topic: policy.events, Key: policy_id

class PolicyCreatedEvent(BaseModel):
    event_type: Literal["policy.created"] = "policy.created"
    policy_id: str
    policy_name: str
    scope_type: str
    version_id: str
    workspace_id: str | None
    created_by: str
    correlation: CorrelationContext


class PolicyUpdatedEvent(BaseModel):
    event_type: Literal["policy.updated"] = "policy.updated"
    policy_id: str
    new_version_id: str
    previous_version_id: str
    change_summary: str | None
    updated_by: str
    correlation: CorrelationContext


class PolicyArchivedEvent(BaseModel):
    event_type: Literal["policy.archived"] = "policy.archived"
    policy_id: str
    archived_by: str
    active_attachment_count: int  # Consumers can flag affected agents
    correlation: CorrelationContext


class PolicyAttachedEvent(BaseModel):
    event_type: Literal["policy.attached"] = "policy.attached"
    policy_id: str
    policy_version_id: str
    target_type: str
    target_id: str | None
    correlation: CorrelationContext


# Topic: policy.gate.blocked, Key: agent_id

class GateBlockedEvent(BaseModel):
    event_type: Literal["policy.gate.blocked"] = "policy.gate.blocked"
    agent_id: str
    agent_fqn: str
    enforcement_component: str
    action_type: str
    target: str
    block_reason: str
    policy_rule_ref: dict | None
    execution_id: str | None
    workspace_id: str
    blocked_action_record_id: str
    correlation: CorrelationContext


# Topic: policy.gate.allowed (opt-in per tool, Key: agent_id)

class GateAllowedEvent(BaseModel):
    event_type: Literal["policy.gate.allowed"] = "policy.gate.allowed"
    agent_id: str
    agent_fqn: str
    tool_fqn: str
    execution_id: str | None
    correlation: CorrelationContext
```

---

## Sanitizer Patterns Reference

```python
# apps/control-plane/src/platform/policies/sanitizer.py

SECRET_PATTERNS: dict[str, str] = {
    "bearer_token":      r"Bearer\s+[A-Za-z0-9._\-]{8,}",
    "api_key":           r"\b(sk-|key-)[A-Za-z0-9]{8,}",
    "jwt_token":         r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
    "connection_string": r"(postgres|mysql|mongodb|redis|amqp)://[^@]+@[^/\s]+(/[^\s]*)?",
    "password_literal":  r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+",
}
# Replacement format: [REDACTED:{type}]
# e.g.: "Bearer abc123" → "[REDACTED:bearer_token]"
```

---

## Redis Key Schema

```
policy:bundle:{fingerprint}        # EnforcementBundle JSON, TTL 300s
policy:write_rate:{agent_id}:{minute_bucket}   # Integer counter, TTL 120s
```
