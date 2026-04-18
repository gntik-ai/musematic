# Research: Analytics and Cost Intelligence Dashboard

**Feature**: 049-analytics-cost-dashboard  
**Phase**: 0 — Research  
**Date**: 2026-04-18

## Decision 1: Date Range State Management

**Decision**: URL query params (`useSearchParams` + `useRouter`) for date range and breakdown mode; Zustand for ephemeral UI state (active section, popover open/close).

**Rationale**: Date range is a filter the user expects to be shareable and bookmarkable (same motivation as marketplace search). Changing the date range reloads all charts — `useSearchParams` triggers re-render cleanly. Non-URL UI state (which section is expanded, whether a scatter dot popover is open) does not need to survive a page refresh.

**Alternatives considered**:
- Zustand for everything: Breaks link-sharing and back-button behavior for date ranges.
- React context: Would work but Zustand is already the project standard for client state, and context does not persist URL state.

---

## Decision 2: Drift Time-Series Data Source

**Decision**: Combine two existing endpoints for the behavioral drift dashboard:
- `GET /api/v1/analytics/usage?agent_fqn=...&start_time=...&end_time=...` — provides the per-agent quality data series (via `avg_duration_ms`, `execution_count`; note: quality score is not yet in the usage endpoint but is in KPI).
- `GET /api/v1/analytics/kpi?workspace_id=...` — provides `avg_quality_score` at workspace level over time.
- `GET /api/v1/context-engineering/drift-alerts?workspace_id=...` — provides drift alerts with `historical_mean` (baseline), `recent_mean`, `degradation_delta`, and `created_at` timestamps (anomaly markers).

**Rationale**: No dedicated per-agent drift time-series endpoint exists. The drift alerts endpoint (`/api/v1/context-engineering/drift-alerts`) provides the anomaly events with their timestamps, historical mean (baseline), and deviation magnitude. The usage endpoint provides per-agent execution data points (quality via kpi). Combining these gives the full drift chart: usage data points form the time series; drift alert `created_at` + `historical_mean` provide the baseline overlay and anomaly markers.

**Alternatives considered**:
- Mock only: Defers actual drift visibility to a later sprint; not acceptable for a P2 feature.
- Dedicated drift time-series endpoint: Correct long-term solution, but not available in feature 034 yet — would block delivery. Plan uses the available endpoints and notes this as a refinement candidate.

---

## Decision 3: CSV Export Approach

**Decision**: Client-side CSV generation. After all data is fetched, serialize the active query result (usage items filtered by active date range and agent filter) into a CSV string using a utility function. Trigger download via `URL.createObjectURL(new Blob([csv], { type: "text/csv" }))` + a temporary `<a>` element click.

**Rationale**: The spec explicitly assumes CSV export is client-side from already-fetched data. No server endpoint is required or planned. This is the simplest approach and avoids an additional API call.

**Alternatives considered**:
- Server-side export endpoint: Would handle large datasets better but introduces backend work and a new endpoint not in scope for feature 020. Can be upgraded later.

---

## Decision 4: Recharts Forecast Confidence Band

**Decision**: Use Recharts `AreaChart` with three `Area` components. The confidence band is rendered by stacking: a transparent fill for the low-to-expected gap, and a shaded fill for the expected-to-high gap. The expected projection uses a `Line` component overlaid on the same `AreaChart`. The shaded area between low and high uses `fillOpacity: 0.15`.

**Rationale**: Recharts `Area` natively supports stacked fills with custom opacity. This avoids any custom SVG work and stays within the existing Recharts 2.x API.

**Alternatives considered**:
- Custom SVG path: More precise but significantly more complex and hard to maintain.
- D3 + Recharts composable: Overkill; Recharts Area handles this use case.

---

## Decision 5: Scatter Plot Interactivity

**Decision**: Use Recharts `ScatterChart` with a custom `onClick` on each `Scatter` dot. On click, open a shadcn `Popover` positioned at the click coordinates showing the agent detail (name, model, cost, quality score, efficiency rank). The scatter shape uses a custom `shape` render prop to support the "no quality data" visual treatment (dashed outline via SVG `strokeDasharray`).

**Rationale**: `ScatterChart` is the natural Recharts component for x/y scatter plots. Custom `shape` gives full control over the dot appearance. A `Popover` (not a native tooltip) is used because hover tooltips are not accessible on mobile (spec requires tap-to-reveal).

**Alternatives considered**:
- Built-in Recharts Tooltip: Lacks the full agent detail the spec requires; not mobile-friendly.
- @xyflow/react: Designed for node graphs, not scatter plots; wrong tool.

---

## Decision 6: Component Organization

**Decision**: All analytics components live under `apps/web/components/features/analytics/`. Hooks live under `apps/web/lib/hooks/` following the `use-analytics-*.ts` naming convention. Types live in `apps/web/types/analytics.ts`.

```
components/features/analytics/
  AnalyticsPageHeader.tsx        # Date range selector + export button
  CostOverviewSection.tsx        # Line chart + breakdown toggle
  TokenConsumptionSection.tsx    # Stacked bar chart
  CostEfficiencySection.tsx      # Scatter plot + recommendations
  BudgetForecastSection.tsx      # Budget progress bars + forecast chart
  DriftDashboardSection.tsx      # Per-agent drift charts grid
  CostOverviewChart.tsx          # Recharts LineChart
  TokenConsumptionChart.tsx      # Recharts BarChart (stacked)
  CostEfficiencyScatter.tsx      # Recharts ScatterChart
  RecommendationCard.tsx         # Optimization suggestion card
  BudgetUtilizationBar.tsx       # Progress bar per workspace
  ForecastChart.tsx              # Recharts AreaChart (confidence band)
  DriftChart.tsx                 # Recharts LineChart (baseline + anomaly markers)
```

**Rationale**: Consistent with existing feature folders (`components/features/marketplace/`, `components/features/fleet/`). Section components own the data-fetching concern (error/loading states). Chart components are presentational.

---

## Decision 7: Analytics Filter Zustand Store

**Decision**: Create `apps/web/lib/stores/use-analytics-store.ts` to hold:
- `breakdownMode: "workspace" | "agent" | "model"` (breakdown toggle state for cost chart)
- `forecastHorizon: 7 | 30 | 90` (selected forecast window)
- No date range (lives in URL params)

**Rationale**: Breakdown mode and forecast horizon are not shareable state — they are in-session UI preferences. URL params are reserved for the date range, which is the primary filter.

---

## Decision 8: Budget Data Source

**Decision**: Budget utilization progress bars use:
- **Current spend**: `GET /api/v1/analytics/kpi` total cost for the selected period.
- **Allocated budget**: Not available as a per-workspace field in the current backend (feature 018 does not expose per-workspace budget allocations). Initial implementation uses the platform-level `ANALYTICS_BUDGET_THRESHOLD_USD` setting surfaced via the workspace cost summary API. The component is designed to accept an optional `allocatedBudgetUsd` prop so the data source can be upgraded when per-workspace budgets are added.

**Rationale**: The spec assumes per-workspace budget data exists from feature 018, but the backend does not yet expose this. Shipping with the platform threshold as a placeholder is better than blocking delivery. The component contract is forward-compatible.

**Alternatives considered**:
- Block delivery until feature 018 adds budget fields: Adds blocking dependency on backend work not in scope.
- Hide budget section entirely: Loses P2 user value.

---

## Decision 9: Mobile Scatter Plot Fallback

**Decision**: Below `768px` viewport width (detected via `useMediaQuery("(max-width: 767px)")`), the scatter plot section is replaced with a shadcn `Table` listing agents sorted by efficiency rank (ascending), showing: rank, agent name, cost, quality score.

**Rationale**: Recharts ScatterChart requires a minimum width (~400px) to be readable. The spec requires a simplified list view on narrow viewports. The `useMediaQuery` hook already exists in `apps/web/lib/hooks/use-media-query.ts`.

---

## Decision 10: Independent Section Error Handling

**Decision**: Each chart section (`CostOverviewSection`, `TokenConsumptionSection`, etc.) wraps its data fetch in an independent TanStack Query call. The page is NOT wrapped in a single error boundary. Each section renders its own inline error state using the existing `SectionError` component from `components/features/home/SectionError.tsx`.

**Rationale**: FR-013 explicitly requires independent section failure handling. TanStack Query already isolates failed queries; using `SectionError` (already built and tested) avoids duplicating error UI code.

---

## Decision 11: Analytics Query Keys

**Decision**: Define a single `analyticsQueryKeys` object in `apps/web/lib/hooks/use-analytics-usage.ts` following the pattern from `workflowQueryKeys` in `use-workflow-list.ts`:

```typescript
export const analyticsQueryKeys = {
  usage: (workspaceId: string, from: string, to: string, granularity: string, agentFqn?: string) =>
    ["analytics", "usage", workspaceId, from, to, granularity, agentFqn] as const,
  costIntelligence: (workspaceId: string, from: string, to: string) =>
    ["analytics", "cost-intelligence", workspaceId, from, to] as const,
  recommendations: (workspaceId: string) =>
    ["analytics", "recommendations", workspaceId] as const,
  forecast: (workspaceId: string, horizonDays: number) =>
    ["analytics", "forecast", workspaceId, horizonDays] as const,
  kpi: (workspaceId: string, from: string, to: string, granularity: string) =>
    ["analytics", "kpi", workspaceId, from, to, granularity] as const,
  driftAlerts: (workspaceId: string) =>
    ["analytics", "drift-alerts", workspaceId] as const,
};
```

**Rationale**: Consistent with existing query key patterns. Enables targeted cache invalidation per section.
