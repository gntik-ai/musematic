from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Granularity(StrEnum):
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class RecommendationType(StrEnum):
    MODEL_SWITCH = "model_switch"
    SELF_CORRECTION_TUNING = "self_correction_tuning"
    CONTEXT_OPTIMIZATION = "context_optimization"
    UNDERUTILIZATION = "underutilization"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CostModelCreate(BaseModel):
    model_id: str
    provider: str
    display_name: str
    input_token_cost_usd: float
    output_token_cost_usd: float
    per_second_cost_usd: float | None = None
    valid_from: datetime


class CostModelResponse(BaseModel):
    id: UUID
    model_id: str
    provider: str
    display_name: str
    input_token_cost_usd: float
    output_token_cost_usd: float
    per_second_cost_usd: float | None
    is_active: bool
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


class UsageQueryParams(BaseModel):
    workspace_id: UUID
    agent_fqn: str | None = None
    model_id: str | None = None
    start_time: datetime
    end_time: datetime
    granularity: Granularity = Granularity.DAILY
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CostIntelligenceParams(BaseModel):
    workspace_id: UUID
    start_time: datetime
    end_time: datetime


class ForecastParams(BaseModel):
    workspace_id: UUID
    horizon_days: int = Field(default=30, ge=7, le=90)


class RecommendationsParams(BaseModel):
    workspace_id: UUID


class UsageRollupItem(BaseModel):
    period: datetime
    workspace_id: UUID
    agent_fqn: str
    model_id: str
    provider: str
    execution_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    avg_duration_ms: float
    self_correction_loops: int


class UsageResponse(BaseModel):
    items: list[UsageRollupItem]
    total: int
    workspace_id: UUID
    granularity: Granularity
    start_time: datetime
    end_time: datetime


class AgentCostQuality(BaseModel):
    agent_fqn: str
    model_id: str
    provider: str
    total_cost_usd: float
    avg_quality_score: float | None
    cost_per_quality: float | None
    execution_count: int
    efficiency_rank: int


class CostIntelligenceResponse(BaseModel):
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    agents: list[AgentCostQuality]


class OptimizationRecommendation(BaseModel):
    recommendation_type: RecommendationType
    agent_fqn: str
    title: str
    description: str
    estimated_savings_usd_per_month: float
    confidence: ConfidenceLevel
    data_points: int
    supporting_data: dict[str, float | int | str | None]


class RecommendationsResponse(BaseModel):
    workspace_id: UUID
    recommendations: list[OptimizationRecommendation]
    generated_at: datetime


class ForecastPoint(BaseModel):
    date: datetime
    projected_cost_usd_low: float
    projected_cost_usd_expected: float
    projected_cost_usd_high: float


class ResourcePrediction(BaseModel):
    workspace_id: UUID
    horizon_days: int
    generated_at: datetime
    trend_direction: str
    high_volatility: bool
    data_points_used: int
    warning: str | None
    daily_forecast: list[ForecastPoint]
    total_projected_low: float
    total_projected_expected: float
    total_projected_high: float


class KpiDataPoint(BaseModel):
    period: datetime
    total_cost_usd: float
    execution_count: int
    avg_duration_ms: float
    avg_quality_score: float | None
    cost_per_quality: float | None


class KpiSeries(BaseModel):
    workspace_id: UUID
    granularity: Granularity
    start_time: datetime
    end_time: datetime
    items: list[KpiDataPoint]
