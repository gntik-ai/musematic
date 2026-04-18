from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from platform.policies.models import (
    AttachmentTargetType,
    EnforcementComponent,
    PolicyScopeType,
    PolicyStatus,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_string_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [item.strip() for item in values if item.strip()]


class EnforcementRuleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    action: Literal["allow", "deny", "warn", "audit"]
    tool_patterns: list[str] = Field(default_factory=list)
    applicable_step_types: list[str] = Field(default_factory=list)
    log_allowed_invocations: bool = False

    @field_validator("tool_patterns", "applicable_step_types")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class PurposeScopeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    allowed_purposes: list[str] = Field(default_factory=list)
    denied_purposes: list[str] = Field(default_factory=list)

    @field_validator("allowed_purposes", "denied_purposes")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class SafetyRuleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
    action: Literal["block"] = "block"


class MaturityGateRuleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_maturity_level: int = Field(ge=0, le=10)
    capability_patterns: list[str] = Field(default_factory=list)

    @field_validator("capability_patterns")
    @classmethod
    def normalize_patterns(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class BudgetLimitsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tool_invocations_per_execution: int | None = Field(default=None, ge=0)
    max_memory_writes_per_minute: int | None = Field(default=None, ge=0)


class PolicyRulesSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enforcement_rules: list[EnforcementRuleSchema] = Field(default_factory=list)
    maturity_gate_rules: list[MaturityGateRuleSchema] = Field(default_factory=list)
    purpose_scopes: list[PurposeScopeSchema] = Field(default_factory=list)
    budget_limits: BudgetLimitsSchema = Field(default_factory=BudgetLimitsSchema)
    safety_rules: list[SafetyRuleSchema] = Field(default_factory=list)
    allowed_namespaces: list[str] = Field(default_factory=list)
    allowed_classifications: list[str] = Field(default_factory=list)
    allowed_agent_fqns: list[str] = Field(default_factory=list)

    @field_validator("allowed_namespaces", "allowed_classifications", "allowed_agent_fqns")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scope_type: PolicyScopeType
    workspace_id: UUID | None = None
    rules: PolicyRulesSchema
    change_summary: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description", "change_summary")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    rules: PolicyRulesSchema | None = None
    change_summary: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("description", "change_summary")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class PolicyVersionResponse(BaseModel):
    id: UUID
    policy_id: UUID
    version_number: int
    rules: dict[str, Any]
    change_summary: str | None
    created_by: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyVersionListResponse(BaseModel):
    items: list[PolicyVersionResponse]
    total: int


class PolicyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    scope_type: PolicyScopeType
    status: PolicyStatus
    workspace_id: UUID | None
    current_version_id: UUID | None
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyWithVersionResponse(PolicyResponse):
    current_version: PolicyVersionResponse | None = None


class PolicyListResponse(BaseModel):
    items: list[PolicyResponse]
    total: int
    page: int
    page_size: int


class PolicyAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version_id: UUID | None = None
    target_type: AttachmentTargetType
    target_id: str | None = None

    @field_validator("target_id")
    @classmethod
    def normalize_target(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class PolicyAttachResponse(BaseModel):
    id: UUID
    policy_id: UUID
    policy_version_id: UUID
    target_type: AttachmentTargetType
    target_id: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyAttachmentListResponse(BaseModel):
    items: list[PolicyAttachResponse]
    total: int


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
    resolution: Literal["more_specific_scope_wins", "deny_wins"]


class EffectivePolicyResponse(BaseModel):
    agent_id: UUID
    resolved_rules: list[ResolvedRule]
    conflicts: list[PolicyConflict]
    source_policies: list[UUID]


class ValidationManifest(BaseModel):
    source_policy_ids: list[UUID]
    source_version_ids: list[UUID]
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fingerprint: str
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[PolicyConflict] = Field(default_factory=list)


class EnforcementBundle(BaseModel):
    fingerprint: str
    allowed_tool_patterns: list[str] = Field(default_factory=list)
    denied_tool_patterns: list[str] = Field(default_factory=list)
    maturity_gate_rules: list[MaturityGateRuleSchema] = Field(default_factory=list)
    allowed_purposes: list[str] = Field(default_factory=list)
    denied_purposes: list[str] = Field(default_factory=list)
    allowed_namespaces: list[str] = Field(default_factory=list)
    budget_limits: BudgetLimitsSchema = Field(default_factory=BudgetLimitsSchema)
    safety_rules: list[dict[str, Any]] = Field(default_factory=list)
    log_allowed_tools: list[str] = Field(default_factory=list)
    manifest: ValidationManifest

    _step_allowed_tool_patterns: dict[str, list[str]] = PrivateAttr(default_factory=dict)
    _step_denied_tool_patterns: dict[str, list[str]] = PrivateAttr(default_factory=dict)

    def set_step_maps(
        self,
        *,
        allowed: dict[str, list[str]],
        denied: dict[str, list[str]],
    ) -> None:
        self._step_allowed_tool_patterns = {key: list(value) for key, value in allowed.items()}
        self._step_denied_tool_patterns = {key: list(value) for key, value in denied.items()}

    @property
    def step_allowed_tool_patterns(self) -> dict[str, list[str]]:
        return {key: list(value) for key, value in self._step_allowed_tool_patterns.items()}

    @property
    def step_denied_tool_patterns(self) -> dict[str, list[str]]:
        return {key: list(value) for key, value in self._step_denied_tool_patterns.items()}

    def get_shard(self, step_type: str) -> EnforcementBundle:
        bundle = self.model_copy(deep=True)
        if self._step_allowed_tool_patterns or self._step_denied_tool_patterns:
            bundle.allowed_tool_patterns = list(self._step_allowed_tool_patterns.get(step_type, []))
            bundle.denied_tool_patterns = list(self._step_denied_tool_patterns.get(step_type, []))
        elif step_type != "tool_invocation":
            bundle.allowed_tool_patterns = []
            bundle.denied_tool_patterns = []
        if step_type != "memory_write":
            bundle.allowed_namespaces = []
        return bundle


class GateResult(BaseModel):
    allowed: bool
    block_reason: str | None = None
    policy_rule_ref: dict[str, Any] | None = None
    check_latency_ms: float | None = None


class SanitizeToolOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str
    agent_id: UUID
    agent_fqn: str = Field(min_length=1, max_length=512)
    tool_fqn: str = Field(min_length=1, max_length=512)
    execution_id: UUID | None = None
    workspace_id: UUID | None = None


class SanitizationResult(BaseModel):
    output: str
    redaction_count: int
    redacted_types: list[str]


class PolicyBlockedActionRecordResponse(BaseModel):
    id: UUID
    agent_id: UUID
    agent_fqn: str
    enforcement_component: EnforcementComponent
    action_type: str
    target: str
    block_reason: str
    policy_rule_ref: dict[str, Any] | None
    execution_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyBlockedActionListResponse(BaseModel):
    items: list[PolicyBlockedActionRecordResponse]
    total: int
    page: int
    page_size: int


class MaturityGateLevel(BaseModel):
    level: int
    capabilities: list[str]


class MaturityGateListResponse(BaseModel):
    levels: list[MaturityGateLevel]


def build_bundle_fingerprint(version_ids: list[UUID]) -> str:
    joined = "|".join(sorted(str(version_id) for version_id in version_ids))
    return sha256(joined.encode("utf-8")).hexdigest()
