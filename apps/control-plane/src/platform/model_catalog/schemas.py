from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ProviderName = Literal["openai", "anthropic", "google", "mistral"]
CatalogStatus = Literal["approved", "deprecated", "blocked"]
QualityTier = Literal["tier1", "tier2", "tier3"]
ScopeType = Literal["global", "workspace", "agent"]
BackoffStrategy = Literal["fixed", "linear", "exponential"]
QualityDegradation = Literal["tier_equal", "tier_plus_one", "tier_plus_two"]
PatternLayer = Literal["input_sanitizer", "output_validator"]
PatternAction = Literal["strip", "quote_as_data", "reject", "redact", "block"]
Severity = Literal["low", "medium", "high", "critical"]


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CatalogEntryCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=64, description="Model provider name.")
    model_id: str = Field(min_length=1, max_length=256, description="Provider model identifier.")
    display_name: str | None = Field(default=None, max_length=256, description="Human label.")
    approved_use_cases: list[str] = Field(default_factory=list, description="Allowed use cases.")
    prohibited_use_cases: list[str] = Field(
        default_factory=list, description="Explicitly prohibited use cases."
    )
    context_window: int = Field(gt=0, description="Maximum context window in tokens.")
    input_cost_per_1k_tokens: Decimal = Field(ge=0, description="Input cost per 1k tokens.")
    output_cost_per_1k_tokens: Decimal = Field(ge=0, description="Output cost per 1k tokens.")
    quality_tier: QualityTier = Field(description="Approved quality tier.")
    approval_expires_at: datetime = Field(description="Approval expiry timestamp.")

    @field_validator("provider", "model_id", "display_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class CatalogEntryPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=256, description="Human label.")
    approved_use_cases: list[str] | None = Field(default=None, description="Allowed use cases.")
    prohibited_use_cases: list[str] | None = Field(
        default=None, description="Explicitly prohibited use cases."
    )
    context_window: int | None = Field(default=None, gt=0, description="Context window.")
    input_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0, description="Input cost.")
    output_cost_per_1k_tokens: Decimal | None = Field(
        default=None, ge=0, description="Output cost."
    )
    quality_tier: QualityTier | None = Field(default=None, description="Quality tier.")
    approval_expires_at: datetime | None = Field(default=None, description="Approval expiry.")

    @field_validator("display_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class BlockRequest(BaseModel):
    justification: str = Field(min_length=3, description="Reason for blocking the model.")


class DeprecateRequest(BaseModel):
    justification: str | None = Field(default=None, description="Reason for deprecation.")


class ReapproveRequest(BaseModel):
    approval_expires_at: datetime = Field(description="Fresh approval expiry timestamp.")
    justification: str = Field(min_length=3, description="Reason for re-approval.")


class CatalogEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    provider: str
    model_id: str
    display_name: str | None
    context_window: int
    input_cost_per_1k_tokens: Decimal
    output_cost_per_1k_tokens: Decimal
    quality_tier: str
    status: str
    approval_expires_at: datetime


class CatalogEntryListResponse(BaseModel):
    items: list[CatalogEntryResponse]
    total: int


class ModelCardFields(BaseModel):
    capabilities: str | None = Field(default=None, description="Capabilities summary.")
    training_cutoff: date | None = Field(default=None, description="Training cutoff date.")
    known_limitations: str | None = Field(default=None, description="Known limitations.")
    safety_evaluations: dict[str, Any] | None = Field(
        default=None, description="Safety evaluation details."
    )
    bias_assessments: dict[str, Any] | None = Field(
        default=None, description="Bias assessment details."
    )
    card_url: str | None = Field(default=None, description="External card URL.")


class ModelCardResponse(ModelCardFields):
    model_config = {"from_attributes": True}

    id: UUID
    catalog_entry_id: UUID
    revision: int
    material: bool = False


class FallbackPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="Policy name.")
    scope_type: ScopeType = Field(description="Policy scope.")
    scope_id: UUID | None = Field(default=None, description="Workspace or agent ID.")
    primary_model_id: UUID = Field(description="Primary catalog entry ID.")
    fallback_chain: list[str] = Field(min_length=1, description="Ordered fallback chain.")
    retry_count: int = Field(default=3, ge=1, le=10, description="Primary retry count.")
    backoff_strategy: BackoffStrategy = Field(
        default="exponential", description="Primary backoff strategy."
    )
    acceptable_quality_degradation: QualityDegradation = Field(
        default="tier_plus_one", description="Allowed degradation from primary tier."
    )
    recovery_window_seconds: int = Field(default=300, ge=30, description="Sticky TTL.")


class FallbackPolicyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128, description="Policy name.")
    fallback_chain: list[str] | None = Field(default=None, min_length=1, description="Chain.")
    retry_count: int | None = Field(default=None, ge=1, le=10, description="Retries.")
    backoff_strategy: BackoffStrategy | None = Field(default=None, description="Backoff.")
    acceptable_quality_degradation: QualityDegradation | None = Field(
        default=None, description="Allowed tier degradation."
    )
    recovery_window_seconds: int | None = Field(default=None, ge=30, description="Sticky TTL.")


class FallbackPolicyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    scope_type: str
    scope_id: UUID | None
    primary_model_id: UUID
    fallback_chain: list[str] = Field(default_factory=list)
    retry_count: int = 3
    backoff_strategy: str = "exponential"
    acceptable_quality_degradation: str = "tier_plus_one"
    recovery_window_seconds: int = 300


class FallbackPolicyListResponse(BaseModel):
    items: list[FallbackPolicyResponse]
    total: int


class CredentialCreate(BaseModel):
    workspace_id: UUID = Field(description="Workspace ID.")
    provider: str = Field(min_length=1, max_length=64, description="Provider name.")
    vault_ref: str = Field(min_length=1, max_length=256, description="Vault reference.")


class CredentialVaultRefPatch(BaseModel):
    vault_ref: str = Field(min_length=1, max_length=256, description="New Vault reference.")


class CredentialRotateRequest(BaseModel):
    overlap_window_hours: int = Field(default=24, ge=0, le=168, description="Overlap window.")
    emergency: bool = Field(default=False, description="Emergency rotation flag.")
    justification: str | None = Field(default=None, description="Emergency justification.")
    approved_by: UUID | None = Field(default=None, description="Second approver ID.")


class CredentialResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    workspace_id: UUID
    provider: str
    vault_ref: str
    rotation_schedule_id: UUID | None = None


class CredentialListResponse(BaseModel):
    items: list[CredentialResponse]
    total: int


class CredentialRotateResponse(BaseModel):
    rotation_schedule_id: UUID
    rotation_state: str
    overlap_ends_at: datetime | None = None


class InjectionPatternCreate(BaseModel):
    pattern_name: str = Field(min_length=1, max_length=128, description="Pattern name.")
    pattern_regex: str = Field(min_length=1, description="Python regex.")
    severity: Severity = Field(description="Pattern severity.")
    layer: PatternLayer = Field(description="Defence layer.")
    action: PatternAction = Field(description="Action to take.")
    workspace_id: UUID | None = Field(default=None, description="Workspace override.")


class InjectionPatternPatch(BaseModel):
    pattern_regex: str | None = Field(default=None, min_length=1, description="Python regex.")
    severity: Severity | None = Field(default=None, description="Pattern severity.")
    action: PatternAction | None = Field(default=None, description="Action to take.")


class InjectionPatternResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    pattern_name: str
    pattern_regex: str
    severity: str
    layer: str
    action: str
    seeded: bool
    workspace_id: UUID | None = None


class InjectionPatternListResponse(BaseModel):
    items: list[InjectionPatternResponse]
    total: int


class InjectionFindingResponse(BaseModel):
    layer: str
    pattern_name: str
    severity: str
    action_taken: str
    workspace_id: UUID
    agent_id: UUID | None = None
    created_at: datetime
