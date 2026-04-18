# UI Component Contracts: Analytics and Cost Intelligence Dashboard

**Feature**: 049-analytics-cost-dashboard  
**Phase**: 1 — Design  
**Date**: 2026-04-18

These contracts define the public interfaces (props and hook signatures) for the major components and hooks in this feature. They establish the boundary between data-fetching logic (hooks) and presentation logic (components).

---

## Hooks

### `useAnalyticsUsage`

**File**: `apps/web/lib/hooks/use-analytics-usage.ts`

```typescript
function useAnalyticsUsage(
  filters: AnalyticsFilters,
): UseQueryResult<UsageResponse, Error>
```

- Calls `GET /api/v1/analytics/usage`
- Params: `workspace_id`, `start_time`, `end_time`, `granularity`
- Query key: `analyticsQueryKeys.usage(...)`
- `staleTime`: 60_000ms (1 min)

### `useCostIntelligence`

**File**: `apps/web/lib/hooks/use-cost-intelligence.ts`

```typescript
function useCostIntelligence(
  filters: AnalyticsFilters,
): UseQueryResult<CostIntelligenceResponse, Error>
```

- Calls `GET /api/v1/analytics/cost-intelligence`
- Params: `workspace_id`, `start_time`, `end_time`
- Query key: `analyticsQueryKeys.costIntelligence(...)`

### `useOptimizationRecommendations`

**File**: `apps/web/lib/hooks/use-optimization-recommendations.ts`

```typescript
function useOptimizationRecommendations(
  workspaceId: string,
): UseQueryResult<RecommendationsResponse, Error>
```

- Calls `GET /api/v1/analytics/recommendations`
- Query key: `analyticsQueryKeys.recommendations(workspaceId)`
- `staleTime`: 300_000ms (5 min) — recommendations don't change frequently

### `useCostForecast`

**File**: `apps/web/lib/hooks/use-cost-forecast.ts`

```typescript
function useCostForecast(
  workspaceId: string,
  horizonDays: ForecastHorizon,
): UseQueryResult<ResourcePrediction, Error>
```

- Calls `GET /api/v1/analytics/cost-forecast`
- Params: `workspace_id`, `horizon_days`
- Query key: `analyticsQueryKeys.forecast(workspaceId, horizonDays)`

### `useAnalyticsKpi`

**File**: `apps/web/lib/hooks/use-analytics-kpi.ts`

```typescript
function useAnalyticsKpi(
  filters: AnalyticsFilters,
): UseQueryResult<KpiSeries, Error>
```

- Calls `GET /api/v1/analytics/kpi`
- Params: `workspace_id`, `start_time`, `end_time`, `granularity`
- Query key: `analyticsQueryKeys.kpi(...)`

### `useDriftAlerts`

**File**: `apps/web/lib/hooks/use-drift-alerts.ts`

```typescript
function useDriftAlerts(
  workspaceId: string,
): UseQueryResult<DriftAlertListResponse, Error>
```

- Calls `GET /api/v1/context-engineering/drift-alerts`
- Params: `workspace_id`, `limit=100`, `offset=0`
- Query key: `analyticsQueryKeys.driftAlerts(workspaceId)`

### `useAnalyticsStore`

**File**: `apps/web/lib/stores/use-analytics-store.ts`

```typescript
interface AnalyticsStore {
  breakdownMode: BreakdownMode;
  forecastHorizon: ForecastHorizon;
  setBreakdownMode: (mode: BreakdownMode) => void;
  setForecastHorizon: (days: ForecastHorizon) => void;
}

function useAnalyticsStore(): AnalyticsStore  // Zustand selector
```

### `useAnalyticsExport`

**File**: `apps/web/lib/hooks/use-analytics-export.ts`

```typescript
function useAnalyticsExport(): {
  exportToCsv: (data: UsageResponse, filters: AnalyticsFilters) => void;
  isExporting: boolean;
}
```

- Generates CSV string client-side from `UsageResponse.items`
- Triggers browser download via `Blob` + `<a>` click
- `isExporting` is `true` during the synchronous CSV build (for button feedback)

---

## Page Component

### `AnalyticsPage`

**File**: `apps/web/app/(main)/analytics/page.tsx`

```typescript
// Server component — reads searchParams for initial date range
export default function AnalyticsPage({
  searchParams,
}: {
  searchParams: { from?: string; to?: string; preset?: string };
}): JSX.Element
```

- Renders `AnalyticsPageHeader` at the top
- Renders five section components stacked vertically, each independent
- No data fetching at page level — sections own their queries

---

## Section Components

### `AnalyticsPageHeader`

**File**: `apps/web/components/features/analytics/AnalyticsPageHeader.tsx`

```typescript
interface AnalyticsPageHeaderProps {
  dateRange: AnalyticsDateRange;
  onDateRangeChange: (range: AnalyticsDateRange) => void;
  onExport: () => void;
  isExporting: boolean;
}
```

- Renders: page title, date range selector (shadcn `Popover` + `Calendar`), preset buttons, export button
- Export button is disabled and shows tooltip when `isExporting`

### `CostOverviewSection`

**File**: `apps/web/components/features/analytics/CostOverviewSection.tsx`

```typescript
interface CostOverviewSectionProps {
  filters: AnalyticsFilters;
}
```

- Owns `useAnalyticsUsage(filters)` and `useAnalyticsStore()` calls
- Renders `CostOverviewChart` when data available
- Renders `SectionError` on query error
- Renders loading skeleton while `isPending`

### `TokenConsumptionSection`

**File**: `apps/web/components/features/analytics/TokenConsumptionSection.tsx`

```typescript
interface TokenConsumptionSectionProps {
  filters: AnalyticsFilters;
}
```

- Owns `useAnalyticsUsage(filters)`
- Groups usage items by provider and period for stacked bar data
- Renders `TokenConsumptionChart`

### `CostEfficiencySection`

**File**: `apps/web/components/features/analytics/CostEfficiencySection.tsx`

```typescript
interface CostEfficiencySectionProps {
  filters: AnalyticsFilters;
}
```

- Owns `useCostIntelligence(filters)` and `useOptimizationRecommendations(workspaceId)`
- Renders `CostEfficiencyScatter` + list of `RecommendationCard`
- Uses `useMediaQuery` to switch scatter to table on mobile

### `BudgetForecastSection`

**File**: `apps/web/components/features/analytics/BudgetForecastSection.tsx`

```typescript
interface BudgetForecastSectionProps {
  workspaceId: string;
  currentPeriodFilters: AnalyticsFilters;
}
```

- Owns `useAnalyticsKpi(currentPeriodFilters)` for current spend
- Owns `useCostForecast(workspaceId, forecastHorizon)` for forecast chart
- Reads `forecastHorizon` from analytics store
- Renders `BudgetUtilizationBar` per workspace + `ForecastChart`
- Shows warning banner if `high_volatility` or `data_points_used < 7`

### `DriftDashboardSection`

**File**: `apps/web/components/features/analytics/DriftDashboardSection.tsx`

```typescript
interface DriftDashboardSectionProps {
  filters: AnalyticsFilters;
}
```

- Owns `useDriftAlerts(workspaceId)` for anomaly data
- Owns `useAnalyticsUsage(filters)` for time-series data (shared with CostOverviewSection — TanStack Query deduplicates)
- Groups drift alerts by `agent_fqn`; renders one `DriftChart` per unique agent

---

## Chart Components (Presentational)

### `CostOverviewChart`

**File**: `apps/web/components/features/analytics/CostOverviewChart.tsx`

```typescript
interface CostOverviewChartProps {
  data: CostChartPoint[];
  seriesKeys: string[];          // one key per breakdown segment
  breakdownMode: BreakdownMode;
  onBreakdownChange: (mode: BreakdownMode) => void;
  height?: number;               // default: 300
}
```

### `TokenConsumptionChart`

**File**: `apps/web/components/features/analytics/TokenConsumptionChart.tsx`

```typescript
interface TokenConsumptionChartProps {
  data: TokenBarPoint[];
  providers: string[];           // bar segment keys
  height?: number;               // default: 280
}
```

### `CostEfficiencyScatter`

**File**: `apps/web/components/features/analytics/CostEfficiencyScatter.tsx`

```typescript
interface CostEfficiencyScatterProps {
  agents: ScatterPoint[];
  onAgentClick?: (agent: ScatterPoint) => void;
  height?: number;               // default: 400
}
```

### `CostEfficiencyTable` (mobile fallback)

**File**: `apps/web/components/features/analytics/CostEfficiencyTable.tsx`

```typescript
interface CostEfficiencyTableProps {
  agents: ScatterPoint[];
}
```

### `RecommendationCard`

**File**: `apps/web/components/features/analytics/RecommendationCard.tsx`

```typescript
interface RecommendationCardProps {
  recommendation: OptimizationRecommendation;
}
```

### `BudgetUtilizationBar`

**File**: `apps/web/components/features/analytics/BudgetUtilizationBar.tsx`

```typescript
interface BudgetUtilizationBarProps {
  workspaceName: string;
  currentSpendUsd: number;
  allocatedBudgetUsd: number | null;  // null = no budget set, bar shows spend only
}
```

- Color coding: green `<75%`, amber `75–90%`, red `>90%`
- When `allocatedBudgetUsd` is null: renders spend-only state with "No budget set" label

### `ForecastChart`

**File**: `apps/web/components/features/analytics/ForecastChart.tsx`

```typescript
interface ForecastChartProps {
  data: ForecastChartPoint[];
  trendDirection: string;
  totalProjectedExpected: number;
  height?: number;               // default: 300
}
```

### `DriftChart`

**File**: `apps/web/components/features/analytics/DriftChart.tsx`

```typescript
interface DriftChartProps {
  agentFqn: string;
  data: DriftChartPoint[];
  height?: number;               // default: 200
}
```

- Renders baseline as a dashed horizontal reference line (`ReferenceLine` in Recharts)
- Renders anomaly markers as custom dot shapes (`<Dot>` with fill change)
- "No drift detected" label shown when no point has `isAnomaly: true`

---

## State Transitions

### Date Range Selection

```
User selects preset "30d"
  → onDateRangeChange({ from: subDays(today, 30), to: today, preset: "30d" })
  → router.push(?from=...&to=...&preset=30d)
  → URL changes
  → AnalyticsFilters recomputed from URL
  → All section queries invalidated (new query key)
  → Charts re-render with new data
```

### Section Error Recovery

```
Query fails (e.g., CostIntelligenceSection)
  → SectionError renders with retry button
  → Other sections unaffected (independent queries)
  → User clicks retry
  → queryClient.invalidateQueries(analyticsQueryKeys.costIntelligence(...))
  → Section re-fetches
```
