# Data Model: Analytics and Cost Intelligence

**Feature**: 020-analytics-cost-intelligence  
**Date**: 2026-04-11  
**Phase**: Phase 1 — Design

## Overview

The analytics bounded context uses two storage backends:
- **ClickHouse**: All usage events, quality events, and materialized rollup views
- **PostgreSQL**: `analytics_cost_models` configuration table only (SQLAlchemy-managed)

---

## 1. PostgreSQL Model (SQLAlchemy)

### 1.1 CostModel

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, DateTime, Boolean
from decimal import Decimal
from datetime import datetime
from src.platform.common.models.base import Base
from src.platform.common.models.mixins import UUIDMixin, TimestampMixin, AuditMixin

class CostModel(Base, UUIDMixin, TimestampMixin, AuditMixin):
    """Pricing configuration for computing cost estimates per model."""
    
    __tablename__ = "analytics_cost_models"
    
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    input_token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    output_token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    per_second_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Composite unique: one active pricing config per model_id at any time
    # Enforced via service-layer validation + partial unique index in migration
```

**Alembic migration**: `apps/control-plane/migrations/versions/005_analytics_cost_models.py`

---

## 2. ClickHouse Schema (DDL via clickhouse_setup.py)

### 2.1 analytics_usage_events (Base Table)

```sql
CREATE TABLE IF NOT EXISTS analytics_usage_events
(
    event_id            UUID,
    execution_id        UUID,
    workspace_id        UUID,
    agent_fqn           String,         -- "namespace:local_name"
    model_id            String,
    provider            String,
    timestamp           DateTime64(3, 'UTC'),
    input_tokens        UInt64          DEFAULT 0,
    output_tokens       UInt64          DEFAULT 0,
    total_tokens        UInt64 MATERIALIZED input_tokens + output_tokens,
    execution_duration_ms UInt64        DEFAULT 0,
    self_correction_loops UInt32        DEFAULT 0,
    reasoning_tokens    UInt64          DEFAULT 0,
    cost_usd            Decimal(18, 10) DEFAULT 0,
    pipeline_version    String          DEFAULT '1',
    ingested_at         DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
ORDER BY (toYYYYMM(timestamp), workspace_id, agent_fqn)
PARTITION BY toYYYYMM(timestamp)
TTL timestamp + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;
```

### 2.2 analytics_quality_events (Base Table)

```sql
CREATE TABLE IF NOT EXISTS analytics_quality_events
(
    event_id            UUID,
    execution_id        UUID,
    workspace_id        UUID,
    agent_fqn           String,
    model_id            String,
    timestamp           DateTime64(3, 'UTC'),
    quality_score       Float64,
    eval_suite_id       UUID            DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),
    ingested_at         DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
ORDER BY (toYYYYMM(timestamp), workspace_id, agent_fqn)
PARTITION BY toYYYYMM(timestamp)
TTL timestamp + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;
```

### 2.3 analytics_usage_hourly (Materialized View)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_hourly
ENGINE = AggregatingMergeTree()
ORDER BY (hour, workspace_id, agent_fqn, model_id)
POPULATE
AS SELECT
    toStartOfHour(timestamp)          AS hour,
    workspace_id,
    agent_fqn,
    model_id,
    provider,
    countState()                       AS execution_count_state,
    sumState(input_tokens)             AS input_tokens_state,
    sumState(output_tokens)            AS output_tokens_state,
    sumState(cost_usd)                 AS cost_usd_state,
    avgState(execution_duration_ms)    AS avg_duration_ms_state,
    sumState(self_correction_loops)    AS self_correction_loops_state,
    sumState(reasoning_tokens)         AS reasoning_tokens_state
FROM analytics_usage_events
GROUP BY hour, workspace_id, agent_fqn, model_id, provider;
```

### 2.4 analytics_usage_daily (Materialized View)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_daily
ENGINE = AggregatingMergeTree()
ORDER BY (day, workspace_id, agent_fqn, model_id)
POPULATE
AS SELECT
    toStartOfDay(timestamp)           AS day,
    workspace_id,
    agent_fqn,
    model_id,
    provider,
    countState()                       AS execution_count_state,
    sumState(input_tokens)             AS input_tokens_state,
    sumState(output_tokens)            AS output_tokens_state,
    sumState(cost_usd)                 AS cost_usd_state,
    avgState(execution_duration_ms)    AS avg_duration_ms_state,
    sumState(self_correction_loops)    AS self_correction_loops_state
FROM analytics_usage_events
GROUP BY day, workspace_id, agent_fqn, model_id, provider;
```

### 2.5 analytics_usage_monthly (Materialized View)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_monthly
ENGINE = AggregatingMergeTree()
ORDER BY (month, workspace_id, agent_fqn, model_id)
POPULATE
AS SELECT
    toStartOfMonth(timestamp)         AS month,
    workspace_id,
    agent_fqn,
    model_id,
    provider,
    countState()                       AS execution_count_state,
    sumState(input_tokens)             AS input_tokens_state,
    sumState(output_tokens)            AS output_tokens_state,
    sumState(cost_usd)                 AS cost_usd_state,
    sumState(self_correction_loops)    AS self_correction_loops_state
FROM analytics_usage_events
GROUP BY month, workspace_id, agent_fqn, model_id, provider;
```

---

## 3. Pydantic Schemas (Python Service Layer)

### 3.1 Request Schemas

```python
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from enum import StrEnum

class Granularity(StrEnum):
    HOURLY  = "hourly"
    DAILY   = "daily"
    MONTHLY = "monthly"

class UsageQueryParams(BaseModel):
    workspace_id: UUID
    agent_fqn: str | None = None
    model_id: str | None = None
    start_time: datetime
    end_time: datetime
    granularity: Granularity = Granularity.DAILY
    limit: int = Field(default=100, le=1000)
    offset: int = 0

class CostIntelligenceParams(BaseModel):
    workspace_id: UUID
    start_time: datetime
    end_time: datetime

class ForecastParams(BaseModel):
    workspace_id: UUID
    horizon_days: int = Field(default=30, ge=7, le=90)

class RecommendationsParams(BaseModel):
    workspace_id: UUID
```

### 3.2 Response Schemas

```python
class UsageRollupItem(BaseModel):
    period: datetime          # start of hour/day/month
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
    avg_quality_score: float | None    # None if no quality data
    cost_per_quality: float | None     # None if no quality data
    execution_count: int
    efficiency_rank: int               # 1 = most efficient

class CostIntelligenceResponse(BaseModel):
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    agents: list[AgentCostQuality]     # sorted by cost_per_quality asc

class RecommendationType(StrEnum):
    MODEL_SWITCH           = "model_switch"
    SELF_CORRECTION_TUNING = "self_correction_tuning"
    CONTEXT_OPTIMIZATION   = "context_optimization"
    UNDERUTILIZATION       = "underutilization"

class ConfidenceLevel(StrEnum):
    HIGH   = "high"    # >= 100 data points
    MEDIUM = "medium"  # >= 30 data points
    LOW    = "low"     # < 30 data points

class OptimizationRecommendation(BaseModel):
    recommendation_type: RecommendationType
    agent_fqn: str
    title: str
    description: str
    estimated_savings_usd_per_month: float
    confidence: ConfidenceLevel
    data_points: int
    supporting_data: dict              # rule-specific context (current model, target model, cost delta, etc.)

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
    trend_direction: str              # "increasing" | "decreasing" | "stable"
    high_volatility: bool
    data_points_used: int
    warning: str | None               # e.g., "Insufficient data — estimate based on <7 days"
    daily_forecast: list[ForecastPoint]
    total_projected_low: float
    total_projected_expected: float
    total_projected_high: float
```

### 3.3 Cost Model Schemas

```python
class CostModelCreate(BaseModel):
    model_id: str
    provider: str
    display_name: str
    input_token_cost_usd: float       # cost per token (e.g., 0.0000030 for $3/1M)
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
```

---

## 4. Service Layer Classes

### 4.1 AnalyticsService

```python
class AnalyticsService:
    """
    Business logic for analytics queries and intelligence computations.
    
    Depends on:
    - AnalyticsRepository (ClickHouse queries)
    - CostModelRepository (PostgreSQL CRUD for pricing)
    - RecommendationEngine (rule-based heuristics)
    - ForecastEngine (linear trend extrapolation)
    - workspaces_service (workspace membership validation)
    """
    
    async def get_usage(self, params: UsageQueryParams, user_id: UUID) -> UsageResponse: ...
    async def get_cost_intelligence(self, params: CostIntelligenceParams, user_id: UUID) -> CostIntelligenceResponse: ...
    async def get_recommendations(self, params: RecommendationsParams, user_id: UUID) -> RecommendationsResponse: ...
    async def get_forecast(self, params: ForecastParams, user_id: UUID) -> ResourcePrediction: ...
```

### 4.2 AnalyticsRepository (ClickHouse)

```python
class AnalyticsRepository:
    """
    Direct ClickHouse query execution via clickhouse-connect client.
    No SQLAlchemy. Returns dicts or typed results from ClickHouse.
    """
    
    async def query_usage_rollups(self, workspace_id, granularity, start_time, end_time, ...) -> list[dict]: ...
    async def query_cost_quality_join(self, workspace_id, start_time, end_time) -> list[dict]: ...
    async def query_daily_cost_series(self, workspace_id, days_back: int) -> list[dict]: ...
    async def query_agent_metrics(self, workspace_id) -> list[dict]: ...  # for recommendations
    async def query_fleet_baselines(self, workspace_id) -> dict: ...       # avg loops, avg quality
    async def insert_usage_events_batch(self, events: list[dict]) -> None: ...
    async def insert_quality_events_batch(self, events: list[dict]) -> None: ...
```

### 4.3 RecommendationEngine

```python
class RecommendationEngine:
    """
    Rule-based heuristics for generating optimization recommendations.
    Pure computation — no I/O. Takes pre-fetched agent metrics as input.
    """
    
    def generate(self, agent_metrics: list[dict], fleet_baselines: dict) -> list[OptimizationRecommendation]: ...
    def _check_model_switch(self, agent: dict, ...) -> OptimizationRecommendation | None: ...
    def _check_self_correction_tuning(self, agent: dict, fleet_avg_loops: float) -> OptimizationRecommendation | None: ...
    def _check_context_optimization(self, agent: dict, fleet_p95_ratio: float, fleet_median_quality: float) -> OptimizationRecommendation | None: ...
    def _check_underutilization(self, agent: dict) -> OptimizationRecommendation | None: ...
    def _confidence(self, data_points: int) -> ConfidenceLevel: ...
```

### 4.4 ForecastEngine

```python
class ForecastEngine:
    """
    Linear trend extrapolation for budget forecasting.
    Pure computation — no I/O. Takes daily cost series as input.
    """
    
    def forecast(self, daily_costs: list[float], horizon_days: int) -> ResourcePrediction: ...
    def _linear_regression(self, xs: list[float], ys: list[float]) -> tuple[float, float]: ...
    def _confidence_interval(self, residuals: list[float], n_future: int, ...) -> tuple[float, float]: ...
    def _volatility_flag(self, residuals: list[float], mean_cost: float) -> bool: ...
```

### 4.5 AnalyticsPipelineConsumer

```python
class AnalyticsPipelineConsumer:
    """
    Kafka consumer that reads runtime and evaluation events, extracts usage data,
    and batch-inserts to ClickHouse.
    
    Topics consumed:
    - workflow.runtime (usage events)
    - runtime.lifecycle (agent provisioning events for underutilization tracking)
    - evaluation.events (quality scores)
    
    Batch trigger: 100 events OR 5 seconds, whichever first.
    """
    
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def _process_batch(self, events: list[EventEnvelope]) -> None: ...
    def _extract_usage_event(self, envelope: EventEnvelope) -> dict | None: ...
    def _extract_quality_event(self, envelope: EventEnvelope) -> dict | None: ...
    def _compute_cost(self, tokens_in: int, tokens_out: int, duration_ms: int, model_id: str) -> float: ...
```

---

## 5. Kafka Events Emitted

| Event Type | Topic | Trigger |
|-----------|-------|---------|
| `analytics.recommendation.generated` | `analytics.events` | New recommendations computed for workspace |
| `analytics.forecast.updated` | `analytics.events` | Forecast recomputed (daily background task) |
| `analytics.budget.threshold_crossed` | `analytics.events` | Cumulative spend crosses configured threshold |

All events use the canonical `EventEnvelope` from feature 013.

---

## 6. Module Structure

```text
apps/control-plane/
├── src/platform/
│   └── analytics/
│       ├── __init__.py
│       ├── models.py              # CostModel SQLAlchemy model
│       ├── schemas.py             # All Pydantic request/response schemas
│       ├── service.py             # AnalyticsService
│       ├── repository.py          # AnalyticsRepository (ClickHouse) + CostModelRepository (SQLAlchemy)
│       ├── router.py              # FastAPI router: /api/v1/analytics/*
│       ├── events.py              # Event payload types + publish_* helpers for analytics.events
│       ├── exceptions.py          # AnalyticsError, WorkspaceAuthorizationError
│       ├── dependencies.py        # get_analytics_service, get_analytics_repository
│       ├── consumer.py            # AnalyticsPipelineConsumer (Kafka → ClickHouse)
│       ├── clickhouse_setup.py    # Idempotent ClickHouse DDL (tables + materialized views)
│       ├── recommendation.py      # RecommendationEngine (pure computation)
│       └── forecast.py            # ForecastEngine (pure computation)
├── migrations/
│   └── versions/
│       └── 005_analytics_cost_models.py  # Alembic: analytics_cost_models table
└── tests/
    ├── unit/
    │   ├── test_analytics_recommendation.py   # RecommendationEngine rule tests
    │   ├── test_analytics_forecast.py         # ForecastEngine accuracy tests
    │   ├── test_analytics_schemas.py          # Pydantic schema validation tests
    │   └── test_analytics_cost_computation.py # Cost estimate computation tests
    └── integration/
        ├── test_analytics_pipeline.py         # Kafka → ClickHouse ingestion flow
        ├── test_analytics_usage_query.py      # Usage rollup query correctness
        ├── test_analytics_cost_intelligence.py# Cost-per-quality JOIN + ranking
        ├── test_analytics_recommendations.py  # End-to-end recommendation generation
        └── test_analytics_forecast.py         # Forecast with seeded trend data
```

---

## 7. Alembic Migration (PostgreSQL only)

`migrations/versions/005_analytics_cost_models.py`:
- Creates `analytics_cost_models` table
- Index on `(model_id, is_active)` for fast pricing lookup
- Partial unique index: `UNIQUE (model_id) WHERE is_active = true` (one active config per model)
- Inserts seed data for common models (gpt-4o, claude-3-5-sonnet, gemini-2.0-flash, etc.)
