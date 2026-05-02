from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityProfileSchema(_StrictModel):
    agent_id: UUID | None = None
    has_data: bool = False
    success_rate: float | None = None
    quality_score_avg: float | None = None
    self_correction_rate: float | None = None
    satisfaction_avg: float | None = None
    satisfaction_count: int = 0
    certification_compliance: str = "uncertified"
    last_updated_at: datetime | None = None
    source_unavailable: bool = False


class AggregateRatingSchema(_StrictModel):
    avg_score: float | None = None
    review_count: int = 0


class AgentListingProjection(_StrictModel):
    agent_id: UUID
    fqn: str
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    maturity_level: int = 0
    trust_tier: str = "unverified"
    certification_status: str = "uncertified"
    cost_tier: str = "free"
    status: str = "published"
    invocable: bool = True
    quality_profile: QualityProfileSchema | None = None
    aggregate_rating: AggregateRatingSchema | None = None
    relevance_score: float | None = None
    # UPD-049: marketplace scope dimension. The frontend uses this to render
    # the "From public marketplace" label on cross-tenant public rows when
    # the consuming tenant has the `consume_public_marketplace` feature flag
    # set. RLS performs the visibility cut at the database layer; this field
    # is purely informational for the UI.
    marketplace_scope: str = "workspace"


class MarketplaceSearchRequest(_StrictModel):
    query: str = ""
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    maturity_level_min: int | None = None
    maturity_level_max: int | None = None
    trust_tier: list[str] = Field(default_factory=list)
    certification_status: list[str] = Field(default_factory=list)
    cost_tier: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class MarketplaceSearchResponse(_StrictModel):
    results: list[AgentListingProjection]
    total: int
    page: int
    page_size: int
    query: str
    has_results: bool


class AgentComparisonRequest(_StrictModel):
    agent_ids: list[UUID] = Field(min_length=2, max_length=4)


class ComparisonAttribute(_StrictModel):
    value: Any
    differs: bool


class AgentComparisonRow(_StrictModel):
    agent_id: UUID
    fqn: str
    name: str
    capabilities: ComparisonAttribute
    maturity_level: ComparisonAttribute
    trust_tier: ComparisonAttribute
    certification_status: ComparisonAttribute
    quality_score_avg: ComparisonAttribute
    cost_tier: ComparisonAttribute
    success_rate: ComparisonAttribute
    user_rating_avg: ComparisonAttribute


class AgentComparisonResponse(_StrictModel):
    agents: list[AgentComparisonRow]
    compared_count: int


class RatingCreateRequest(_StrictModel):
    score: int = Field(ge=1, le=5)
    review_text: str | None = None

    @field_validator("review_text")
    @classmethod
    def normalize_review(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RatingResponse(_StrictModel):
    rating_id: UUID
    agent_id: UUID
    user_id: UUID
    score: int
    review_text: str | None
    created_at: datetime
    updated_at: datetime


class RatingsListResponse(_StrictModel):
    ratings: list[RatingResponse]
    total: int
    page: int
    page_size: int
    avg_score: float | None


class FailurePatternEntry(_StrictModel):
    error_type: str
    count: int
    percentage: float


class InvocationTrendPoint(_StrictModel):
    date: date
    count: int


class CreatorAnalyticsResponse(_StrictModel):
    agent_id: UUID
    agent_fqn: str
    invocation_count_total: int
    invocation_count_30d: int
    avg_satisfaction: float | None
    satisfaction_count: int
    common_failure_patterns: list[FailurePatternEntry]
    invocation_trend: list[InvocationTrendPoint]


class RecommendedAgentEntry(_StrictModel):
    agent: AgentListingProjection
    score: float
    reasoning: str | None = None
    recommendation_type: str


class RecommendationResponse(_StrictModel):
    recommendations: list[RecommendedAgentEntry]
    recommendation_type: str


class ContextualSuggestionRequest(_StrictModel):
    context_type: Literal["workflow_step", "conversation", "fleet_config"]
    context_text: str
    max_results: int = Field(default=5, ge=1, le=10)

    @field_validator("context_text")
    @classmethod
    def normalize_context(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("context_text must not be empty")
        return stripped


class ContextualSuggestionResponse(_StrictModel):
    suggestions: list[AgentListingProjection]
    has_results: bool
    context_type: str


class TrendingAgentEntry(_StrictModel):
    rank: int
    agent: AgentListingProjection
    trending_score: float
    growth_rate: float
    invocations_this_week: int
    invocations_last_week: int
    trending_reason: str
    satisfaction_delta: float | None = None


class TrendingAgentsResponse(_StrictModel):
    agents: list[TrendingAgentEntry]
    snapshot_date: date | None = None
    total: int
