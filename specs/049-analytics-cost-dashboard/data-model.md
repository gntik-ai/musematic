# Data Model: Analytics and Cost Intelligence Dashboard

**Feature**: 049-analytics-cost-dashboard  
**Phase**: 1 — Design  
**Date**: 2026-04-18  
**Source file**: `apps/web/types/analytics.ts` (to be created)

## Overview

This feature is frontend-only. All data comes from existing backend APIs (feature 020 — Analytics and Cost Intelligence, and feature 034/022 — context engineering drift alerts). No new database tables are introduced.

---

## API Response Types

These types mirror the backend Python schemas exactly (from `apps/control-plane/src/platform/analytics/schemas.py` and `apps/control-plane/src/platform/context_engineering/schemas.py`).

### Granularity

```typescript
type Granularity = "hourly" | "daily" | "monthly";
```

### RecommendationType / ConfidenceLevel

```typescript
type RecommendationType =
  | "model_switch"
  | "self_correction_tuning"
  | "context_optimization"
  | "underutilization";

type ConfidenceLevel = "high" | "medium" | "low";
```

### UsageRollupItem

Backend: `UsageRollupItem`

```typescript
interface UsageRollupItem {
  period: string;          // ISO 8601 datetime
  workspace_id: string;
  agent_fqn: string;
  model_id: string;
  provider: string;
  execution_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_duration_ms: number;
  self_correction_loops: number;
}
```

### UsageResponse

Backend: `UsageResponse`

```typescript
interface UsageResponse {
  items: UsageRollupItem[];
  total: number;
  workspace_id: string;
  granularity: Granularity;
  start_time: string;
  end_time: string;
}
```

### AgentCostQuality

Backend: `AgentCostQuality`

```typescript
interface AgentCostQuality {
  agent_fqn: string;
  model_id: string;
  provider: string;
  total_cost_usd: number;
  avg_quality_score: number | null;
  cost_per_quality: number | null;
  execution_count: number;
  efficiency_rank: number;
}
```

### CostIntelligenceResponse

Backend: `CostIntelligenceResponse`

```typescript
interface CostIntelligenceResponse {
  workspace_id: string;
  period_start: string;
  period_end: string;
  agents: AgentCostQuality[];
}
```

### OptimizationRecommendation

Backend: `OptimizationRecommendation`

```typescript
interface OptimizationRecommendation {
  recommendation_type: RecommendationType;
  agent_fqn: string;
  title: string;
  description: string;
  estimated_savings_usd_per_month: number;
  confidence: ConfidenceLevel;
  data_points: number;
  supporting_data: Record<string, number | string | null>;
}
```

### RecommendationsResponse

Backend: `RecommendationsResponse`

```typescript
interface RecommendationsResponse {
  workspace_id: string;
  recommendations: OptimizationRecommendation[];
  generated_at: string;
}
```

### ForecastPoint

Backend: `ForecastPoint`

```typescript
interface ForecastPoint {
  date: string;
  projected_cost_usd_low: number;
  projected_cost_usd_expected: number;
  projected_cost_usd_high: number;
}
```

### ResourcePrediction

Backend: `ResourcePrediction`

```typescript
interface ResourcePrediction {
  workspace_id: string;
  horizon_days: number;
  generated_at: string;
  trend_direction: string;      // "increasing" | "decreasing" | "stable"
  high_volatility: boolean;
  data_points_used: number;
  warning: string | null;
  daily_forecast: ForecastPoint[];
  total_projected_low: number;
  total_projected_expected: number;
  total_projected_high: number;
}
```

### KpiDataPoint / KpiSeries

Backend: `KpiDataPoint`, `KpiSeries`

```typescript
interface KpiDataPoint {
  period: string;
  total_cost_usd: number;
  execution_count: number;
  avg_duration_ms: number;
  avg_quality_score: number | null;
  cost_per_quality: number | null;
}

interface KpiSeries {
  workspace_id: string;
  granularity: Granularity;
  start_time: string;
  end_time: string;
  items: KpiDataPoint[];
}
```

### DriftAlertResponse / DriftAlertListResponse

Backend: `DriftAlertResponse`, `DriftAlertListResponse` (context engineering schemas)

```typescript
interface DriftAlertResponse {
  id: string;
  agent_fqn: string;
  workspace_id: string;
  historical_mean: number;    // baseline value
  historical_stddev: number;
  recent_mean: number;
  degradation_delta: number;  // magnitude of drift
  analysis_window_days: number;
  suggested_actions: string[];
  resolved_at: string | null;
  created_at: string;         // timestamp of anomaly detection = anomaly marker date
}

interface DriftAlertListResponse {
  items: DriftAlertResponse[];
  total: number;
  limit: number;
  offset: number;
}
```

---

## UI State Types

### AnalyticsDateRange

Used in URL query params (`from` and `to` as ISO strings, `preset` as string).

```typescript
type DateRangePreset = "7d" | "30d" | "90d" | "custom";

interface AnalyticsDateRange {
  from: Date;
  to: Date;
  preset: DateRangePreset;
}
```

**URL param encoding**:
- `?from=2026-03-18&to=2026-04-17&preset=30d`
- Default: last 30 days, `preset=30d`

### BreakdownMode

Controls how the cost-over-time line chart segments data.

```typescript
type BreakdownMode = "workspace" | "agent" | "model";
```

Stored in `use-analytics-store.ts` (Zustand).

### ForecastHorizon

```typescript
type ForecastHorizon = 7 | 30 | 90;
```

Stored in `use-analytics-store.ts` (Zustand).

### AnalyticsFilters

Composite filter passed to hooks.

```typescript
interface AnalyticsFilters {
  workspaceId: string;
  from: string;        // ISO string from URL
  to: string;          // ISO string from URL
  granularity: Granularity;  // derived: "daily" for ≤90d ranges, "monthly" for longer
}
```

---

## Derived / Computed Types

These are not API types — they are computed from raw API data before being passed to chart components.

### CostChartPoint

Used by `CostOverviewChart`. One point per period per breakdown segment.

```typescript
interface CostChartPoint {
  period: string;        // formatted date label (e.g., "Apr 17")
  [key: string]: number | string;  // dynamic keys per breakdown mode
}
```

Example for breakdown="agent":
```json
{ "period": "Apr 17", "finance-ops:kyc-verifier": 1.23, "hr:onboarding-agent": 0.45 }
```

### TokenBarPoint

Used by `TokenConsumptionChart`.

```typescript
interface TokenBarPoint {
  period: string;
  [provider: string]: number | string;  // "anthropic": 1200, "openai": 800
}
```

### ScatterPoint

Used by `CostEfficiencyScatter`.

```typescript
interface ScatterPoint {
  agentFqn: string;
  modelId: string;
  provider: string;
  costUsd: number;
  qualityScore: number | null;
  executionCount: number;
  efficiencyRank: number;
  hasQualityData: boolean;
}
```

### ForecastChartPoint

Used by `ForecastChart`.

```typescript
interface ForecastChartPoint {
  date: string;
  low: number;
  expected: number;
  high: number;
}
```

### DriftChartPoint

Used by `DriftChart` (one per agent).

```typescript
interface DriftChartPoint {
  period: string;
  value: number | null;    // actual quality score from usage data
  baseline: number;        // historical_mean from drift alert
  isAnomaly: boolean;      // true if an unresolved drift alert covers this date
}
```

---

## Validation Rules

- `from` must be before `to` in URL params; malformed dates fall back to last-30-days default.
- `horizon_days` accepted values: `7`, `30`, `90` — other values are ignored and replaced with `30`.
- `granularity` for usage queries: always `"daily"` for date ranges up to 90 days; `"monthly"` beyond.
- Scatter plot: `qualityScore === null` → `hasQualityData: false` → render dashed circle at `y=0`.
- Budget progress bar color: `< 75%` green, `75–90%` amber, `> 90%` red.
