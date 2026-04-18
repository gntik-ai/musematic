# Tasks: Analytics and Cost Intelligence Dashboard

**Input**: Design documents from `specs/049-analytics-cost-dashboard/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ui-components.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- Exact file paths are in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: TypeScript types, Zustand store, and query key scaffolding that everything else depends on.

- [X] T001 Create `apps/web/types/analytics.ts` with all TypeScript types from data-model.md: `Granularity`, `RecommendationType`, `ConfidenceLevel`, `UsageRollupItem`, `UsageResponse`, `AgentCostQuality`, `CostIntelligenceResponse`, `OptimizationRecommendation`, `RecommendationsResponse`, `ForecastPoint`, `ResourcePrediction`, `KpiDataPoint`, `KpiSeries`, `DriftAlertResponse`, `DriftAlertListResponse`, `AnalyticsDateRange`, `DateRangePreset`, `BreakdownMode`, `ForecastHorizon`, `AnalyticsFilters`, `CostChartPoint`, `TokenBarPoint`, `ScatterPoint`, `ForecastChartPoint`, `DriftChartPoint`
- [X] T002 [P] Create `apps/web/lib/stores/use-analytics-store.ts` — Zustand store with `breakdownMode: BreakdownMode` (default `"workspace"`), `forecastHorizon: ForecastHorizon` (default `30`), `setBreakdownMode`, `setForecastHorizon` actions; no persist (session-only state)
- [X] T003 [P] Define and export `analyticsQueryKeys` object at the top of `apps/web/lib/hooks/use-analytics-usage.ts` covering all 6 query keys: `usage`, `costIntelligence`, `recommendations`, `forecast`, `kpi`, `driftAlerts` — following the shape documented in research.md Decision 11

**Checkpoint**: Types, store, and query keys are in place. No UI yet. TS compilation must pass.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Page shell and date range header — must be complete before any section can be rendered.

**⚠️ CRITICAL**: No user story sections can be built until this phase is complete.

- [X] T004 Replace placeholder in `apps/web/app/(main)/analytics/page.tsx` — remove `"Analytics dashboards land here."` string; add a client boundary import; read `searchParams` for `from`, `to`, `preset`; parse into `AnalyticsDateRange` (default to last-30-days when params absent or invalid); render `AnalyticsPageHeader` + five labelled section placeholder `<div>`s for CostOverview, TokenConsumption, CostEfficiency, BudgetForecast, DriftDashboard
- [X] T005 Create `apps/web/components/features/analytics/AnalyticsPageHeader.tsx` — renders page title ("Analytics"), date range selector (shadcn `Popover` + `Calendar`), preset buttons for "Last 7 days" / "Last 30 days" / "Last 90 days" / "Custom", and a disabled export Button (placeholder wired in US5); preset buttons call `onDateRangeChange` which calls `router.push` to update URL params; active preset is visually highlighted; props: `{ dateRange: AnalyticsDateRange, onDateRangeChange, onExport, isExporting }`

**Checkpoint**: Navigate to `/analytics`. Page renders with header and five empty section areas. Clicking presets updates URL. Custom date range opens calendar picker. No errors in console.

---

## Phase 3: User Story 1 — Cost and Usage Overview (Priority: P1) 🎯 MVP

**Goal**: Deliver the cost-over-time line chart and token consumption stacked bar chart, both controlled by the date range selector.

**Independent Test**: Open `/analytics`. Verify cost chart renders with data points. Click "By Agent" — chart shows one line per agent with distinct colors and legend. Change to "Last 7 days" — all charts update. Hover over a data point — tooltip shows date, cost, breakdown value. Token chart shows stacked bars per provider. Empty data shows empty state.

- [X] T006 [P] [US1] Create `apps/web/lib/hooks/use-analytics-usage.ts` — `useAnalyticsUsage(filters: AnalyticsFilters)` wrapping `GET /api/v1/analytics/usage` via `useAppQuery`; query key from `analyticsQueryKeys.usage(...)`; `staleTime: 60_000`; `enabled` when `workspaceId` is truthy
- [X] T007 [P] [US1] Create `apps/web/lib/hooks/use-analytics-kpi.ts` — `useAnalyticsKpi(filters: AnalyticsFilters)` wrapping `GET /api/v1/analytics/kpi` via `useAppQuery`; query key from `analyticsQueryKeys.kpi(...)`; `staleTime: 60_000`
- [X] T008 [US1] Create `apps/web/components/features/analytics/CostOverviewChart.tsx` — Recharts `LineChart` (responsive container); props `{ data: CostChartPoint[], seriesKeys: string[], breakdownMode: BreakdownMode, onBreakdownChange, height?: number }`; breakdown toggle buttons ("Workspace" / "Agent" / "Model") above the chart; one `<Line>` per `seriesKey` with distinct color from a fixed palette; custom `<Tooltip>` content showing date, cost formatted in USD, breakdown label; `<Legend>` below; empty state (`EmptyState` component) when `data.length === 0`
- [X] T009 [US1] Create `apps/web/components/features/analytics/CostOverviewSection.tsx` — owns `useAnalyticsUsage(filters)` and `useAnalyticsStore()`; transforms `UsageResponse.items` into `CostChartPoint[]` grouped by period, aggregating cost per breakdown key; renders `CostOverviewChart` when data ready; renders 4-row loading skeleton while `isPending`; renders `SectionError` with retry (`queryClient.invalidateQueries`) on error; wires `breakdownMode` from store to chart
- [X] T010 [P] [US1] Create `apps/web/components/features/analytics/TokenConsumptionChart.tsx` — Recharts `BarChart` (responsive container) with stacked bars; props `{ data: TokenBarPoint[], providers: string[], height?: number }`; one `<Bar>` per provider, `stackId="tokens"`; custom tooltip showing period, provider, token count; `<Legend>`; empty state when `data.length === 0`
- [X] T011 [US1] Create `apps/web/components/features/analytics/TokenConsumptionSection.tsx` — owns `useAnalyticsUsage(filters)`; groups `UsageResponse.items` by period and provider summing `total_tokens`; builds `TokenBarPoint[]` and `providers: string[]`; renders `TokenConsumptionChart`; loading skeleton; `SectionError` on error
- [X] T012 [US1] Wire `CostOverviewSection` and `TokenConsumptionSection` into `apps/web/app/(main)/analytics/page.tsx` — replace their placeholder `<div>`s with the real section components, passing `filters` derived from URL params

**Checkpoint**: US1 complete. Cost chart and token chart render independently. Each has its own error state. Changing date range URL params updates both.

---

## Phase 4: User Story 2 — Cost Efficiency Analysis (Priority: P1)

**Goal**: Scatter plot of agent cost vs. quality, with per-agent detail on click, and a list of optimization recommendation cards.

**Independent Test**: Scatter renders one dot per agent-model combination. Agent with no quality data shows dashed outline dot at y=0 with "No quality data" label. Clicking a dot opens a detail popover (agent name, model, cost, quality score, execution count, efficiency rank). Recommendation cards show title, savings, confidence badge. No-recommendations state shows "will appear after more usage data" empty message.

- [X] T013 [P] [US2] Create `apps/web/lib/hooks/use-cost-intelligence.ts` — `useCostIntelligence(filters: AnalyticsFilters)` wrapping `GET /api/v1/analytics/cost-intelligence` via `useAppQuery`; query key from `analyticsQueryKeys.costIntelligence(...)`
- [X] T014 [P] [US2] Create `apps/web/lib/hooks/use-optimization-recommendations.ts` — `useOptimizationRecommendations(workspaceId: string)` wrapping `GET /api/v1/analytics/recommendations` via `useAppQuery`; `staleTime: 300_000` (5 min); query key from `analyticsQueryKeys.recommendations(...)`
- [X] T015 [P] [US2] Create `apps/web/components/features/analytics/CostEfficiencyScatter.tsx` — Recharts `ScatterChart` (responsive container); props `{ agents: ScatterPoint[], onAgentClick?, height?: number }`; maps `ScatterPoint` to `{ x: costUsd, y: qualityScore ?? 0 }`; custom `shape` render prop: solid circle when `hasQualityData=true`, SVG circle with `strokeDasharray="4 2"` and `fillOpacity=0.3` when `false`; `onClick` on each dot calls `onAgentClick`; no-data agents get a small text annotation "No quality data" via a custom `<LabelList>`; axis labels "Cost (USD)" and "Quality Score"; responsive `XAxis`/`YAxis` with tick formatters
- [X] T016 [P] [US2] Create `apps/web/components/features/analytics/CostEfficiencyTable.tsx` — shadcn `Table` mobile fallback; props `{ agents: ScatterPoint[] }`; columns: Rank, Agent, Model, Cost (USD), Quality Score (shows "—" when null); rows sorted ascending by `efficiencyRank`; caption "Showing cost efficiency by agent"
- [X] T017 [P] [US2] Create `apps/web/components/features/analytics/RecommendationCard.tsx` — shadcn `Card`; props `{ recommendation: OptimizationRecommendation }`; renders title, description text, estimated savings ("Save ~$X/mo"), confidence `Badge` (green=high, amber=medium, gray=low); recommendation type icon (Lucide `RefreshCw`/`Sliders`/`Scissors`/`AlertCircle` per type)
- [X] T018 [US2] Create `apps/web/components/features/analytics/CostEfficiencySection.tsx` — owns `useCostIntelligence(filters)` + `useOptimizationRecommendations(workspaceId)`; maps `AgentCostQuality[]` to `ScatterPoint[]`; uses `useMediaQuery("(max-width: 767px)")` to render `CostEfficiencyTable` on mobile or `CostEfficiencyScatter` on desktop; selected agent state for popover (shadcn `Popover` positioned near click, showing all detail fields from US2 acceptance scenario 2); renders list of `RecommendationCard` components below chart; empty states for both scatter and recommendations; `SectionError` per query
- [X] T019 [US2] Wire `CostEfficiencySection` into `apps/web/app/(main)/analytics/page.tsx` — replace placeholder `<div>`

**Checkpoint**: US2 complete. Scatter (desktop) and table (mobile) render independently from US1. Recommendation cards appear below. Clicking a scatter dot shows popover detail.

---

## Phase 5: User Story 3 — Budget Forecasting (Priority: P2)

**Goal**: Budget utilization progress bars with color coding, and a forecast chart with three projection lines and a confidence band.

**Independent Test**: Budget progress bar fills to correct percentage and is green/amber/red per threshold. Forecast chart shows three lines with shaded band between low and high. Selecting "7 day" horizon refetches with `horizon_days=7`. Warning banner appears when `high_volatility: true`. Trend indicator arrow matches `trend_direction`.

- [X] T020 [P] [US3] Create `apps/web/lib/hooks/use-cost-forecast.ts` — `useCostForecast(workspaceId: string, horizonDays: ForecastHorizon)` wrapping `GET /api/v1/analytics/cost-forecast` via `useAppQuery`; query key from `analyticsQueryKeys.forecast(workspaceId, horizonDays)`
- [X] T021 [P] [US3] Create `apps/web/components/features/analytics/BudgetUtilizationBar.tsx` — props `{ workspaceName: string, currentSpendUsd: number, allocatedBudgetUsd: number | null }`; renders workspace name label + current spend formatted in USD; when `allocatedBudgetUsd` is not null: shadcn `Progress` with value clamped to 100, color via Tailwind class switched at 75% (green `bg-green-500`) / 90% (amber `bg-amber-500`) / above (red `bg-red-500`) using `cn()`, percentage text label; when null: spend-only row with "No budget configured" muted label
- [X] T022 [US3] Create `apps/web/components/features/analytics/ForecastChart.tsx` — Recharts `ComposedChart` (responsive container); props `{ data: ForecastChartPoint[], trendDirection: string, totalProjectedExpected: number, height?: number }`; two `<Area>` components (`low` with transparent stroke, `high` with `fillOpacity=0.15`) for the confidence band; `<Line>` for expected projection (solid, primary color); `<XAxis>` with date tick formatter; trend indicator above chart: Lucide `TrendingUp`/`TrendingDown`/`Minus` icon + "Projected: $X total" text
- [X] T023 [US3] Create `apps/web/components/features/analytics/BudgetForecastSection.tsx` — owns `useAnalyticsKpi(currentPeriodFilters)` for current spend + `useCostForecast(workspaceId, forecastHorizon)` for forecast; reads and writes `forecastHorizon` from analytics store; renders one `BudgetUtilizationBar` using KPI total cost as current spend (with `allocatedBudgetUsd=null` placeholder — see research.md Decision 8); horizon selector buttons (7/30/90 days) above forecast chart; warning banners (shadcn `Alert` with `AlertTriangle` icon): one for `high_volatility: true`, one for `data_points_used < 7`; renders `ForecastChart` below; loading skeletons; `SectionError` per query
- [X] T024 [US3] Wire `BudgetForecastSection` into `apps/web/app/(main)/analytics/page.tsx` — replace placeholder `<div>`

**Checkpoint**: US3 complete. Budget bar and forecast chart render independently. Horizon selector triggers refetch. Warning banners appear for low-data and high-volatility scenarios.

---

## Phase 6: User Story 4 — Behavioral Drift Dashboard (Priority: P2)

**Goal**: Per-agent time-series charts showing quality drift with baseline overlay and anomaly markers.

**Independent Test**: One `DriftChart` rendered per unique agent in drift alerts. Dashed baseline reference line visible at `historical_mean`. Anomaly marker (distinct color/shape) appears at alert `created_at` timestamp. Tooltip on anomaly shows date, actual value, baseline, deviation magnitude. Agent with no drift shows clean chart with "No drift detected" label.

- [X] T025 [P] [US4] Create `apps/web/lib/hooks/use-drift-alerts.ts` — `useDriftAlerts(workspaceId: string)` wrapping `GET /api/v1/context-engineering/drift-alerts` via `useAppQuery`; params: `workspace_id`, `limit=100`, `offset=0`; query key from `analyticsQueryKeys.driftAlerts(workspaceId)`
- [X] T026 [US4] Create `apps/web/components/features/analytics/DriftChart.tsx` — Recharts `LineChart` (responsive container); props `{ agentFqn: string, data: DriftChartPoint[], height?: number }`; `<Line>` for `value` (actual quality score, connect nulls with `connectNulls`); `<ReferenceLine>` (dashed `strokeDasharray="4 2"`) at first non-null `baseline` value with label "Baseline"; custom `<Dot>` render prop: normal dot when `!isAnomaly`, large filled circle (distinct color, `r=6`) when `isAnomaly=true`; custom `<Tooltip>` on anomaly marker showing date, actual value, baseline value, deviation (`value - baseline`); when no data point has `isAnomaly: true`, render a `<text>` annotation "No drift detected" centered in the chart SVG; agent FQN as section title above chart
- [X] T027 [US4] Create `apps/web/components/features/analytics/DriftDashboardSection.tsx` — owns `useDriftAlerts(workspaceId)` + `useAnalyticsUsage(filters)` (TanStack Query deduplicates the usage query with CostOverviewSection); groups drift alerts by `agent_fqn`; for each unique agent, builds `DriftChartPoint[]` by joining usage items (for actual value from KPI proxy) with alert `created_at` dates (for `isAnomaly` marker); renders a responsive grid of `DriftChart` cards (2-col on desktop, 1-col on mobile); empty state when `driftAlerts.items.length === 0`; `SectionError` on each query failure
- [X] T028 [US4] Wire `DriftDashboardSection` into `apps/web/app/(main)/analytics/page.tsx` — replace placeholder `<div>`

**Checkpoint**: US4 complete. Drift charts render for each agent. Baseline and anomaly markers visible. Empty state when no drift detected.

---

## Phase 7: User Story 5 — Data Export (Priority: P3)

**Goal**: Enable the export button to download a CSV of the currently visible analytics data filtered by active date range.

**Independent Test**: Click export button — `.csv` file downloads. CSV has correct header row. Rows match active date range filter. Empty data produces header-only CSV + toast notification. Button is disabled during export.

- [X] T029 [US5] Create `apps/web/lib/hooks/use-analytics-export.ts` — `useAnalyticsExport()` returning `{ exportToCsv(data: UsageResponse, filters: AnalyticsFilters): void, isExporting: boolean }`; builds CSV string from `data.items` with columns: `date,agent,model,provider,cost,input_tokens,output_tokens,total_tokens,execution_count,quality_score`; dates formatted ISO 8601; costs as decimal USD strings; when `data.items.length === 0` downloads header-only CSV and calls `toast({ title: "No data", description: "No data matched the active filters." })`; triggers download via `URL.createObjectURL(new Blob([csv], { type: "text/csv" }))` + temp `<a>` element; `isExporting` is true for the duration of the synchronous build
- [X] T030 [US5] Update `apps/web/components/features/analytics/AnalyticsPageHeader.tsx` — wire the export `Button` to `onExport` prop (passed from page); change `disabled` condition from static `true` to `isExporting`; add `aria-label="Export analytics data as CSV"` to the button; add Lucide `Download` icon inside button

**Checkpoint**: US5 complete. Full export flow works end-to-end. CSV is human-readable in a spreadsheet.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode verification, responsive layout, and outlier indicators across all sections.

- [X] T031 [P] Add `role="img"` and `aria-label` describing chart content to all Recharts `ResponsiveContainer` wrapper `<div>` elements in `CostOverviewChart.tsx`, `TokenConsumptionChart.tsx`, `CostEfficiencyScatter.tsx`, `ForecastChart.tsx`, `DriftChart.tsx`
- [X] T032 [P] Add keyboard navigation to breakdown toggle buttons in `CostOverviewSection.tsx` and horizon selector buttons in `BudgetForecastSection.tsx` — ensure `tabIndex`, `role="group"` with `aria-label`, `onKeyDown` handler for arrow keys cycling through options
- [X] T033 [P] Add outlier indicator to `CostOverviewChart.tsx` and `TokenConsumptionChart.tsx`: compute period median cost/tokens; if any value exceeds `3 × median`, add a Recharts `<ReferenceLine>` at `3 × median` with a dashed stroke and label "Outlier threshold"
- [X] T034 Verify dark mode token usage in all 14 components in `apps/web/components/features/analytics/` — ensure all text, border, and background values use Tailwind dark-mode variants (`dark:`) or shadcn CSS custom properties; no hardcoded hex colors
- [X] T035 Verify responsive layout in `apps/web/app/(main)/analytics/page.tsx` — all five sections stack in a single column on mobile; confirm section order top-to-bottom matches spec (cost overview → token consumption → cost efficiency → budget forecast → drift); confirm `BudgetForecastSection` budget bars are visible in the first viewport fold on desktop (no scroll required — SC-006)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)       → no deps; start immediately
Phase 2 (Foundation)  → needs Phase 1 (types + store)
Phase 3 (US1)         → needs Phase 2; T006/T007 parallel, T008/T009/T010 after types
Phase 4 (US2)         → needs Phase 2; parallel with Phase 3
Phase 5 (US3)         → needs Phase 2; parallel with Phase 3/4 (useAnalyticsKpi already defined in Phase 3)
Phase 6 (US4)         → needs Phase 2; reuses useAnalyticsUsage from Phase 3 (T006)
Phase 7 (US5)         → needs Phase 2; independent from all other stories
Phase 8 (Polish)      → needs all story phases complete
```

### User Story Dependencies

- **US1 (P1)**: Start after Phase 2. Defines `useAnalyticsUsage` (T006) which US4 reuses.
- **US2 (P1)**: Start after Phase 2. Fully independent of US1.
- **US3 (P2)**: Start after Phase 2. Reuses `useAnalyticsKpi` from T007 (US1); can start T020/T021/T022 in parallel with US1 and US2.
- **US4 (P2)**: Start after T006 is complete (needs `useAnalyticsUsage`). Otherwise independent.
- **US5 (P3)**: Start after Phase 2. Fully independent.

### Parallel Opportunities Per Story

**Phase 3 (US1)**:
```
Parallel group A: T006 (use-analytics-usage.ts) + T007 (use-analytics-kpi.ts)
Then: T008 (CostOverviewChart), T010 (TokenConsumptionChart) — parallel
Then: T009 (CostOverviewSection), T011 (TokenConsumptionSection) — after charts
Then: T012 (wire page) — after both sections
```

**Phase 4 (US2)**:
```
Parallel group A: T013 (use-cost-intelligence) + T014 (use-optimization-recommendations)
Parallel group B: T015 (CostEfficiencyScatter) + T016 (CostEfficiencyTable) + T017 (RecommendationCard)
Then: T018 (CostEfficiencySection) — after hooks and components
Then: T019 (wire page)
```

**Phase 5 (US3)**:
```
Parallel: T020 (use-cost-forecast) + T021 (BudgetUtilizationBar)
Then: T022 (ForecastChart) — after types verified
Then: T023 (BudgetForecastSection) — after all components
Then: T024 (wire page)
```

**Phase 6 (US4)**:
```
T025 (use-drift-alerts) first
Then: T026 (DriftChart) — parallel with T027 start
Then: T027 (DriftDashboardSection) — after T026
Then: T028 (wire page)
```

---

## Implementation Strategy

### MVP: User Story 1 Only

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundation)
3. Complete Phase 3 (US1: cost chart + token chart)
4. **Validate**: Open `/analytics`, verify both charts render, date range changes update both
5. Ship MVP — operators can see cost trends immediately

### Incremental Delivery

| Increment | Phases | Delivers |
|-----------|--------|---------|
| MVP | 1–3 | Cost trend + token consumption charts (US1) |
| +Efficiency | +4 | Scatter plot + optimization recommendations (US2) |
| +Forecasting | +5 | Budget bars + cost forecast chart (US3) |
| +Drift | +6 | Per-agent behavioral drift monitoring (US4) |
| +Export | +7 | CSV download of analytics data (US5) |
| Complete | +8 | Accessibility, dark mode, outlier indicators |

### Notes

- `useAnalyticsUsage` (T006) is shared by US1, US4, and CSV export — define it in Phase 3 and reuse
- TanStack Query deduplicates identical query keys — `CostOverviewSection` and `DriftDashboardSection` sharing the usage query incurs only one network request
- The analytics page has no top-level error boundary — each section has its own `SectionError` (FR-013)
- Budget progress bars use a `null` placeholder for `allocatedBudgetUsd` initially (research.md Decision 8)
