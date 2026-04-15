from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MaturityValue = Literal["experimental", "developing", "production_ready"]
TopologyValue = Literal["sequential", "hierarchical", "peer", "hybrid"]
RequestTypeValue = Literal["agent", "fleet"]
RequestStatusValue = Literal["pending", "completed", "failed"]


class ModelConfigPayload(BaseModel):
    """Model configuration proposed for an agent blueprint."""

    model_id: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    reasoning_mode: str = "standard"


class ToolSelectionPayload(BaseModel):
    """Tool selection proposed for an agent blueprint."""

    tool_name: str
    tool_id: UUID | str | None = None
    relevance_justification: str = ""
    status: str = "available"


class ConnectorSuggestionPayload(BaseModel):
    """Connector suggestion proposed for a blueprint."""

    connector_type: str
    connector_name: str
    purpose: str = ""
    status: str = "configured"


class PolicyRecommendationPayload(BaseModel):
    """Policy recommendation proposed for a blueprint."""

    policy_id: UUID | str | None = None
    policy_name: str
    attachment_reason: str = ""


class ContextProfilePayload(BaseModel):
    """Context engineering profile proposed for an agent blueprint."""

    assembly_strategy: str = "standard"
    memory_scope: str = "session"
    knowledge_sources: list[str] = Field(default_factory=list)


class FollowUpQuestionPayload(BaseModel):
    """Follow-up question suggested when confidence is low."""

    question: str
    context: str = ""


class AlternativePayload(BaseModel):
    """Alternative considered by the LLM."""

    field: str
    alternatives: list[str] = Field(default_factory=list)
    reason_rejected: str = ""


class DelegationRulePayload(BaseModel):
    """Fleet delegation rule."""

    from_role: str
    to_role: str
    trigger_condition: str = ""


class EscalationRulePayload(DelegationRulePayload):
    """Fleet escalation rule."""

    urgency: Literal["low", "medium", "high"] = "medium"


class OrchestrationRulePayload(BaseModel):
    """Fleet orchestration rule."""

    rule_type: str
    trigger: str = ""
    action: str
    target_role: str = ""


class FleetMemberRolePayload(BaseModel):
    """Role proposal for a fleet member."""

    role_name: str
    purpose: str
    agent_blueprint_inline: dict[str, Any] = Field(default_factory=dict)


class AgentBlueprintGenerateRequest(BaseModel):
    """Request to generate an agent blueprint from natural language."""

    workspace_id: UUID
    description: str = Field(min_length=1, max_length=10000)


class FleetBlueprintGenerateRequest(AgentBlueprintGenerateRequest):
    """Request to generate a fleet blueprint from natural language."""


class BlueprintOverrideItem(BaseModel):
    """Single field-path override item."""

    field_path: str = Field(min_length=1)
    new_value: Any
    reason: str | None = None


class AgentBlueprintOverrideRequest(BaseModel):
    """Request to override an agent blueprint."""

    overrides: list[BlueprintOverrideItem] = Field(min_length=1)


class FleetBlueprintOverrideRequest(AgentBlueprintOverrideRequest):
    """Request to override a fleet blueprint."""


class AgentBlueprintRaw(BaseModel):
    """Raw structured response expected from the LLM for agent blueprints."""

    model_config = ConfigDict(extra="allow")

    model_config_payload: ModelConfigPayload = Field(alias="model_config")
    tool_selections: list[ToolSelectionPayload] = Field(default_factory=list)
    connector_suggestions: list[ConnectorSuggestionPayload] = Field(default_factory=list)
    policy_recommendations: list[PolicyRecommendationPayload] = Field(default_factory=list)
    context_profile: ContextProfilePayload = Field(default_factory=ContextProfilePayload)
    maturity_estimate: MaturityValue
    maturity_reasoning: str = ""
    confidence_score: float = Field(ge=0.0, le=1.0)
    follow_up_questions: list[FollowUpQuestionPayload] = Field(default_factory=list)
    llm_reasoning_summary: str = ""
    alternatives_considered: list[AlternativePayload] = Field(default_factory=list)

    @property
    def model_payload(self) -> dict[str, Any]:
        """Return model configuration as a plain dictionary."""
        return self.model_config_payload.model_dump(mode="json")


class FleetBlueprintRaw(BaseModel):
    """Raw structured response expected from the LLM for fleet blueprints."""

    topology_type: TopologyValue
    member_roles: list[FleetMemberRolePayload] = Field(default_factory=list)
    orchestration_rules: list[OrchestrationRulePayload] = Field(default_factory=list)
    delegation_rules: list[DelegationRulePayload] = Field(default_factory=list)
    escalation_rules: list[EscalationRulePayload] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    follow_up_questions: list[FollowUpQuestionPayload] = Field(default_factory=list)
    llm_reasoning_summary: str = ""
    alternatives_considered: list[AlternativePayload] = Field(default_factory=list)
    single_agent_suggestion: bool = False


class WorkspaceCompositionContext(BaseModel):
    """Non-sensitive workspace facts supplied to the LLM and validator."""

    available_tools: list[dict[str, Any]] = Field(default_factory=list)
    available_models: list[dict[str, Any]] = Field(default_factory=list)
    available_connectors: list[dict[str, Any]] = Field(default_factory=list)
    active_policies: list[dict[str, Any]] = Field(default_factory=list)
    context_engineering_strategies: list[str] = Field(
        default_factory=lambda: ["standard", "compressed", "hierarchical"]
    )


class AgentBlueprintResponse(BaseModel):
    """Response for an agent blueprint."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: UUID
    blueprint_id: UUID
    version: int = Field(ge=1)
    workspace_id: UUID
    description: str
    model_config_data: dict[str, Any] = Field(alias="model_config")
    tool_selections: list[dict[str, Any]]
    connector_suggestions: list[dict[str, Any]]
    policy_recommendations: list[dict[str, Any]]
    context_profile: dict[str, Any]
    maturity_estimate: MaturityValue
    maturity_reasoning: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    low_confidence: bool
    follow_up_questions: list[dict[str, Any]]
    llm_reasoning_summary: str
    alternatives_considered: list[dict[str, Any]]
    generation_time_ms: int | None
    created_at: datetime


class FleetBlueprintResponse(BaseModel):
    """Response for a fleet blueprint."""

    request_id: UUID
    blueprint_id: UUID
    version: int = Field(ge=1)
    workspace_id: UUID
    description: str
    topology_type: TopologyValue
    member_count: int = Field(ge=0)
    member_roles: list[dict[str, Any]]
    orchestration_rules: list[dict[str, Any]]
    delegation_rules: list[dict[str, Any]]
    escalation_rules: list[dict[str, Any]]
    single_agent_suggestion: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    low_confidence: bool
    follow_up_questions: list[dict[str, Any]]
    llm_reasoning_summary: str
    alternatives_considered: list[dict[str, Any]]
    generation_time_ms: int | None
    created_at: datetime


class CheckResult(BaseModel):
    """A single validation check result."""

    passed: bool | None
    details: dict[str, Any] | list[dict[str, Any]]
    remediation: str | None = None
    status: str = "ok"


class CompositionValidationResponse(BaseModel):
    """Response for blueprint validation."""

    validation_id: UUID
    blueprint_id: UUID
    overall_valid: bool
    tools_check: CheckResult
    model_check: CheckResult
    connectors_check: CheckResult
    policy_check: CheckResult
    cycle_check: CheckResult | None = None
    validated_at: datetime


class CompositionAuditEntryResponse(BaseModel):
    """Response for an audit entry."""

    entry_id: UUID
    request_id: UUID
    event_type: str
    actor_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime


class CompositionAuditListResponse(BaseModel):
    """Cursor-paginated audit entry response."""

    items: list[CompositionAuditEntryResponse]
    next_cursor: str | None


class CompositionRequestResponse(BaseModel):
    """Response for a composition request."""

    request_id: UUID
    workspace_id: UUID
    request_type: RequestTypeValue
    description: str
    requested_by: UUID
    status: RequestStatusValue
    llm_model_used: str | None
    generation_time_ms: int | None
    created_at: datetime
    updated_at: datetime


class CompositionRequestListResponse(BaseModel):
    """Cursor-paginated composition request response."""

    items: list[CompositionRequestResponse]
    next_cursor: str | None


class LLMChatChoice(BaseModel):
    """Minimal OpenAI-compatible chat choice."""

    message: dict[str, Any]


class LLMChatResponse(BaseModel):
    """Minimal OpenAI-compatible chat response."""

    choices: list[LLMChatChoice]

    @field_validator("choices")
    @classmethod
    def _choices_not_empty(cls, value: list[LLMChatChoice]) -> list[LLMChatChoice]:
        if not value:
            raise ValueError("LLM response did not include choices")
        return value
