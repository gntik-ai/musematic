# Quickstart: Analytics and Cost Intelligence Dashboard

**Feature**: 049-analytics-cost-dashboard  
**Phase**: 1 — Design  
**Date**: 2026-04-18

## What This Feature Creates

```text
apps/web/
├── app/(main)/analytics/
│   └── page.tsx                          # REPLACE placeholder with full page
│
├── components/features/analytics/        # NEW directory
│   ├── AnalyticsPageHeader.tsx           # Date range selector + export button
│   ├── CostOverviewSection.tsx           # Line chart section (data-fetching)
│   ├── TokenConsumptionSection.tsx       # Stacked bar section (data-fetching)
│   ├── CostEfficiencySection.tsx         # Scatter + recommendations (data-fetching)
│   ├── BudgetForecastSection.tsx         # Budget bars + forecast (data-fetching)
│   ├── DriftDashboardSection.tsx         # Per-agent drift charts (data-fetching)
│   ├── CostOverviewChart.tsx             # Recharts LineChart (presentational)
│   ├── TokenConsumptionChart.tsx         # Recharts BarChart stacked (presentational)
│   ├── CostEfficiencyScatter.tsx         # Recharts ScatterChart (presentational)
│   ├── CostEfficiencyTable.tsx           # Mobile fallback table (presentational)
│   ├── RecommendationCard.tsx            # Optimization suggestion card
│   ├── BudgetUtilizationBar.tsx          # Progress bar with color coding
│   ├── ForecastChart.tsx                 # Recharts AreaChart confidence band
│   └── DriftChart.tsx                    # Per-agent time-series with anomaly markers
│
├── lib/hooks/
│   ├── use-analytics-usage.ts            # NEW — wraps /analytics/usage
│   ├── use-cost-intelligence.ts          # NEW — wraps /analytics/cost-intelligence
│   ├── use-optimization-recommendations.ts # NEW — wraps /analytics/recommendations
│   ├── use-cost-forecast.ts              # NEW — wraps /analytics/cost-forecast
│   ├── use-analytics-kpi.ts             # NEW — wraps /analytics/kpi
│   ├── use-drift-alerts.ts               # NEW — wraps /context-engineering/drift-alerts
│   └── use-analytics-export.ts           # NEW — client-side CSV export
│
├── lib/stores/
│   └── use-analytics-store.ts            # NEW — breakdownMode, forecastHorizon
│
└── types/
    └── analytics.ts                      # NEW — all TypeScript types for this feature
```

## Development Setup

No new dependencies to install. All required libraries are already present:
- `recharts` (charts)
- `@tanstack/react-query` (data fetching)
- `zustand` (client state)
- `date-fns` (date math)
- `shadcn/ui` (all UI primitives)

## Testing Per User Story

### US1 — Cost and Usage Overview

**Goal**: Verify cost-over-time chart renders and responds to filter changes.

**Setup (MSW handler)**:
```typescript
// In test: mock GET /api/v1/analytics/usage
http.get("*/api/v1/analytics/usage", () =>
  HttpResponse.json({
    items: [
      { period: "2026-03-18T00:00:00Z", agent_fqn: "finance:kyc", 
        model_id: "claude-3", provider: "anthropic", cost_usd: 1.23,
        input_tokens: 1000, output_tokens: 500, total_tokens: 1500,
        execution_count: 5, avg_duration_ms: 1200, self_correction_loops: 0 },
    ],
    total: 1, workspace_id: "ws-1", granularity: "daily",
    start_time: "2026-03-18T00:00:00Z", end_time: "2026-04-17T00:00:00Z",
  }),
)
```

**Test checks**:
1. Chart renders with correct data point
2. Changing breakdown from "workspace" to "agent" segments data by agent_fqn
3. Changing date range updates URL params and refetches
4. Tooltip shows date, cost, breakdown value on hover
5. Empty data shows empty state message

**Independent test** (manual): Navigate to `/analytics`. Verify cost chart renders. Click "By Agent" — chart shows one line per agent. Change to "Last 7 days" — all charts update.

---

### US2 — Cost Efficiency Analysis

**Goal**: Verify scatter plot renders per agent and recommendations appear.

**Setup (MSW handlers)**:
```typescript
// Cost intelligence
http.get("*/api/v1/analytics/cost-intelligence", () =>
  HttpResponse.json({
    workspace_id: "ws-1",
    period_start: "...", period_end: "...",
    agents: [
      { agent_fqn: "finance:kyc", model_id: "claude-3", provider: "anthropic",
        total_cost_usd: 12.5, avg_quality_score: 0.89, cost_per_quality: 14.04,
        execution_count: 50, efficiency_rank: 1 },
      { agent_fqn: "hr:onboarding", model_id: "gpt-4", provider: "openai",
        total_cost_usd: 45.0, avg_quality_score: null, cost_per_quality: null,
        execution_count: 20, efficiency_rank: 2 },
    ],
  }),
)
// Recommendations
http.get("*/api/v1/analytics/recommendations", () =>
  HttpResponse.json({
    workspace_id: "ws-1",
    recommendations: [
      { recommendation_type: "model_switch", agent_fqn: "hr:onboarding",
        title: "Switch to Haiku", description: "Lower cost model suitable for...",
        estimated_savings_usd_per_month: 32.0, confidence: "high", data_points: 150,
        supporting_data: {} },
    ],
    generated_at: "...",
  }),
)
```

**Test checks**:
1. Scatter plot renders with one dot for "finance:kyc" at correct (cost, quality) coordinates
2. "hr:onboarding" renders with dashed outline and "No quality data" label at y=0
3. Clicking a dot opens popover showing agent details
4. Recommendation card shows title, savings, confidence badge
5. Empty recommendations show "No recommendations yet" empty state

---

### US3 — Budget Forecasting

**Goal**: Verify budget progress bars and forecast chart.

**Setup (MSW handlers)**:
```typescript
// KPI for current spend
http.get("*/api/v1/analytics/kpi", () =>
  HttpResponse.json({
    workspace_id: "ws-1", granularity: "daily",
    start_time: "...", end_time: "...",
    items: [
      { period: "2026-04-17T00:00:00Z", total_cost_usd: 87.5,
        execution_count: 120, avg_duration_ms: 800,
        avg_quality_score: 0.85, cost_per_quality: null },
    ],
  }),
)
// Cost forecast
http.get("*/api/v1/analytics/cost-forecast", ({ request }) => {
  const url = new URL(request.url);
  const horizonDays = url.searchParams.get("horizon_days") ?? "30";
  return HttpResponse.json({
    workspace_id: "ws-1", horizon_days: Number(horizonDays),
    generated_at: "...", trend_direction: "increasing",
    high_volatility: false, data_points_used: 30, warning: null,
    daily_forecast: [
      { date: "2026-04-18", projected_cost_usd_low: 2.1,
        projected_cost_usd_expected: 3.0, projected_cost_usd_high: 4.5 },
    ],
    total_projected_low: 63.0, total_projected_expected: 90.0, total_projected_high: 135.0,
  });
})
```

**Test checks**:
1. Budget progress bar shows current spend with correct fill and color
2. Forecast chart renders three lines (low, expected, high) with shaded band
3. Selecting "7 day" horizon triggers refetch with `horizon_days=7`
4. Warning banner appears when `high_volatility: true`
5. Warning banner appears when `data_points_used < 7`
6. Trend indicator shows upward arrow when `trend_direction: "increasing"`

---

### US4 — Behavioral Drift Dashboard

**Goal**: Verify per-agent drift charts with baseline and anomaly markers.

**Setup (MSW handler)**:
```typescript
http.get("*/api/v1/context-engineering/drift-alerts", () =>
  HttpResponse.json({
    items: [
      { id: "alert-1", agent_fqn: "finance:kyc", workspace_id: "ws-1",
        historical_mean: 0.87, historical_stddev: 0.04,
        recent_mean: 0.72, degradation_delta: -0.15,
        analysis_window_days: 7, suggested_actions: ["Retrain model"],
        resolved_at: null, created_at: "2026-04-15T00:00:00Z" },
    ],
    total: 1, limit: 100, offset: 0,
  }),
)
```

**Test checks**:
1. One drift chart rendered per unique agent in drift alerts
2. Baseline reference line at `historical_mean: 0.87`
3. Anomaly marker appears at the `created_at` date
4. Hovering over anomaly marker shows date, actual value, baseline, deviation magnitude
5. Agent with no drift alerts shows clean chart with "No drift detected" label

---

### US5 — Data Export

**Goal**: Verify CSV download triggers with correct content.

**Test checks**:
1. Clicking export button triggers download of a `.csv` file
2. CSV has header row: `date,agent,model,provider,cost,input_tokens,output_tokens,total_tokens,execution_count,quality_score`
3. CSV contains only data matching active date range filter
4. When no data, CSV contains only headers and a notification toast appears
5. Export button is disabled during export

---

## Edge Case Testing Scenarios

| Scenario | Expected Result |
|----------|----------------|
| Empty workspace (no usage data) | All charts show empty states; export button disabled |
| Partial quality data (some agents unscored) | Scatter shows unscored agents at y=0 with dashed outline |
| Backend unavailable (analytics) | Each section shows SectionError with retry; other sections load normally |
| Backend unavailable (drift alerts only) | DriftDashboardSection shows error; all other sections load |
| Single data point in date range | Charts render with single point/bar; no line interpolation gap |
| Value 3× the median | Y-axis auto-scales; outlier indicator marker shown |
| Date range with no data | Charts render empty with "No data for this period" label |
| Mobile viewport (<768px) | Scatter replaced by table; charts stack vertically |

---

## URL State Examples

| User Action | URL |
|------------|-----|
| Default page load | `/analytics?preset=30d` |
| Last 7 days selected | `/analytics?preset=7d` |
| Custom range | `/analytics?from=2026-03-01&to=2026-03-31&preset=custom` |
