# Implementation Plan: Analytics and Cost Intelligence Dashboard

**Branch**: `049-analytics-cost-dashboard` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/049-analytics-cost-dashboard/spec.md`

## Summary

Build a full-page analytics dashboard at `app/(main)/analytics/` that replaces the existing placeholder. The dashboard surfaces cost trends, token consumption, cost-vs-quality efficiency analysis, optimization recommendations, budget forecasting, and per-agent behavioral drift — all backed by the existing feature 020 analytics API and the context engineering drift alerts API. The implementation is frontend-only (Next.js 14+, shadcn/ui, Recharts, TanStack Query v5, Zustand).

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router  
**Primary Dependencies**: shadcn/ui, Tailwind CSS 3.4+, TanStack Query v5, Zustand 5.x, Recharts 2.x, date-fns 4.x  
**Storage**: N/A (frontend only — all data from backend REST APIs)  
**Testing**: Vitest + React Testing Library + MSW  
**Target Platform**: Web (desktop primary, mobile responsive)  
**Project Type**: Web application (single feature page within existing Next.js app)  
**Performance Goals**: All sections load independently; each section query resolves in ≤2s on typical connection  
**Constraints**: No new npm packages; use existing Recharts 2.x for all charts; Tailwind utility classes only  
**Scale/Scope**: Single analytics page with 5 sections and 14 components

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Function components only | ✅ PASS | All components use function syntax |
| shadcn/ui for ALL UI primitives | ✅ PASS | No alternative component library introduced |
| No custom CSS (Tailwind only) | ✅ PASS | No new CSS files |
| TanStack Query for server state | ✅ PASS | No useEffect+useState data fetching |
| Zustand for client-only state | ✅ PASS | Analytics store for breakdownMode and forecastHorizon |
| date-fns for date operations | ✅ PASS | Used for date formatting and arithmetic |
| No cross-boundary DB access | ✅ PASS | Frontend only; no DB access |

**Post-design re-check**: No violations introduced. The budget placeholder (using platform threshold instead of per-workspace budget) is a design compromise, not a constitution violation.

## Project Structure

### Documentation (this feature)

```text
specs/049-analytics-cost-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── ui-components.md # Phase 1 output — component + hook interfaces
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
apps/web/
├── app/(main)/analytics/
│   └── page.tsx                               # REPLACE placeholder
│
├── components/features/analytics/             # NEW directory (14 components)
│   ├── AnalyticsPageHeader.tsx                # Date range selector + export button
│   ├── CostOverviewSection.tsx                # Section: data-fetching + layout
│   ├── TokenConsumptionSection.tsx            # Section: data-fetching + layout
│   ├── CostEfficiencySection.tsx              # Section: data-fetching + layout
│   ├── BudgetForecastSection.tsx              # Section: data-fetching + layout
│   ├── DriftDashboardSection.tsx              # Section: data-fetching + layout
│   ├── CostOverviewChart.tsx                  # Recharts LineChart
│   ├── TokenConsumptionChart.tsx              # Recharts BarChart (stacked)
│   ├── CostEfficiencyScatter.tsx              # Recharts ScatterChart
│   ├── CostEfficiencyTable.tsx                # Mobile list fallback
│   ├── RecommendationCard.tsx                 # Optimization suggestion card
│   ├── BudgetUtilizationBar.tsx               # Progress bar (color-coded)
│   ├── ForecastChart.tsx                      # Recharts AreaChart (confidence band)
│   └── DriftChart.tsx                         # Recharts LineChart + anomaly markers
│
├── lib/hooks/
│   ├── use-analytics-usage.ts                 # NEW — /analytics/usage hook
│   ├── use-cost-intelligence.ts               # NEW — /analytics/cost-intelligence hook
│   ├── use-optimization-recommendations.ts    # NEW — /analytics/recommendations hook
│   ├── use-cost-forecast.ts                   # NEW — /analytics/cost-forecast hook
│   ├── use-analytics-kpi.ts                   # NEW — /analytics/kpi hook
│   ├── use-drift-alerts.ts                    # NEW — /context-engineering/drift-alerts hook
│   └── use-analytics-export.ts               # NEW — client-side CSV export hook
│
├── lib/stores/
│   └── use-analytics-store.ts                # NEW — Zustand: breakdownMode, forecastHorizon
│
└── types/
    └── analytics.ts                          # NEW — all TypeScript interfaces for this feature
```

**Structure Decision**: Single `components/features/analytics/` directory following the established feature folder pattern (mirrors `components/features/marketplace/`, `components/features/fleet/`, etc.). Hooks in `lib/hooks/` with `use-analytics-*` naming prefix to group related hooks. Store in `lib/stores/use-analytics-store.ts`.

## Implementation Phases

### Phase 1: Foundation (no UI)

Goal: TypeScript types, Zustand store, query keys, and all 6 TanStack Query hooks. Tests for each hook with MSW.

**Files**:
- `apps/web/types/analytics.ts` — all TS types from data-model.md
- `apps/web/lib/stores/use-analytics-store.ts` — Zustand store for breakdownMode + forecastHorizon
- `apps/web/lib/hooks/use-analytics-usage.ts` + test
- `apps/web/lib/hooks/use-cost-intelligence.ts` + test
- `apps/web/lib/hooks/use-optimization-recommendations.ts` + test
- `apps/web/lib/hooks/use-cost-forecast.ts` + test
- `apps/web/lib/hooks/use-analytics-kpi.ts` + test
- `apps/web/lib/hooks/use-drift-alerts.ts` + test
- `apps/web/lib/hooks/use-analytics-export.ts` + test

**Independent test**: All hook tests pass in Vitest. Each hook returns data matching its API contract.

---

### Phase 2: Page Shell and Header (US1 foundation)

Goal: Replace placeholder analytics page with a working shell. Implement date range selector and URL param management.

**Files**:
- `apps/web/app/(main)/analytics/page.tsx` — replace placeholder; render shell + 5 section placeholders
- `apps/web/components/features/analytics/AnalyticsPageHeader.tsx` — date range selector (shadcn Popover + Calendar), preset buttons, export button (disabled until US5)

**Independent test**: Navigate to `/analytics`. Page renders without error. Changing preset updates URL. Custom date range opens calendar picker.

---

### Phase 3: Cost Overview (US1)

Goal: Implement cost-over-time line chart and token consumption stacked bar chart.

**Files**:
- `apps/web/components/features/analytics/CostOverviewChart.tsx` — Recharts LineChart with dynamic series keys per breakdown mode; interactive tooltip showing date + cost + breakdown value
- `apps/web/components/features/analytics/CostOverviewSection.tsx` — owns `useAnalyticsUsage`; transforms data to `CostChartPoint[]`; breakdown toggle buttons; loading skeleton; `SectionError` on failure
- `apps/web/components/features/analytics/TokenConsumptionChart.tsx` — Recharts BarChart stacked by provider
- `apps/web/components/features/analytics/TokenConsumptionSection.tsx` — owns `useAnalyticsUsage`; groups by provider + period; loading skeleton; `SectionError`

**Independent test**: Mock MSW handlers from quickstart.md. Cost chart shows correct line per agent when breakdown="agent". Changing date range refetches. Tooltip shows correct values. Token chart shows stacked bars by provider. Empty state renders when items=[].

---

### Phase 4: Cost Efficiency (US2)

Goal: Implement scatter plot and optimization recommendation cards.

**Files**:
- `apps/web/components/features/analytics/CostEfficiencyScatter.tsx` — Recharts ScatterChart; custom dot shape (dashed outline for `hasQualityData=false`); `Popover` on click with agent detail
- `apps/web/components/features/analytics/CostEfficiencyTable.tsx` — mobile fallback table (shadcn Table); sorted by efficiency rank
- `apps/web/components/features/analytics/RecommendationCard.tsx` — shadcn Card with title, description, savings in USD, confidence badge (shadcn Badge, color per level)
- `apps/web/components/features/analytics/CostEfficiencySection.tsx` — owns `useCostIntelligence` + `useOptimizationRecommendations`; `useMediaQuery` for scatter/table toggle; renders scatter + recommendation list; empty states for each

**Independent test**: Scatter renders one dot per agent. No-quality agent has dashed dot at y=0. Clicking dot shows popover. Mobile viewport (<768px) shows table instead. Recommendation card shows all required fields. No-recommendations state shows empty message.

---

### Phase 5: Budget Forecasting (US3)

Goal: Implement budget utilization bars and cost forecast chart with confidence bands.

**Files**:
- `apps/web/components/features/analytics/BudgetUtilizationBar.tsx` — shadcn Progress; color-coded (green/amber/red); handles null allocatedBudgetUsd with "No budget set"
- `apps/web/components/features/analytics/ForecastChart.tsx` — Recharts AreaChart; three series (low/expected/high); shaded confidence band; trend indicator
- `apps/web/components/features/analytics/BudgetForecastSection.tsx` — owns `useAnalyticsKpi` + `useCostForecast`; reads `forecastHorizon` from analytics store; forecast horizon selector (7/30/90 day buttons); warning banners for `high_volatility` and `data_points_used < 7`; trend indicator with directional arrow

**Independent test**: Budget bar shows correct fill and color. Forecast chart shows three lines with shaded band. Warning banner appears for `high_volatility: true`. Selecting "7 days" triggers refetch with correct param. Trend indicator shows up/down arrow.

---

### Phase 6: Behavioral Drift (US4)

Goal: Implement per-agent drift charts with baseline overlay and anomaly markers.

**Files**:
- `apps/web/components/features/analytics/DriftChart.tsx` — Recharts LineChart; dashed `ReferenceLine` for `historical_mean` baseline; custom `<Dot>` for anomaly points (distinct color/shape); tooltip on anomaly marker showing date/actual/baseline/deviation; "No drift detected" label when no anomaly
- `apps/web/components/features/analytics/DriftDashboardSection.tsx` — owns `useDriftAlerts` + `useAnalyticsUsage`; groups drift alerts by agent_fqn; builds `DriftChartPoint[]` per agent; renders grid of DriftChart; empty state if no agents have drift data

**Independent test**: One DriftChart per agent. Baseline reference line visible at historical_mean. Anomaly marker distinct from normal points. Tooltip on anomaly shows all required fields. Agent with no drift shows clean chart + "No drift detected" label.

---

### Phase 7: CSV Export (US5)

Goal: Enable the export button wired to client-side CSV generation.

**Files**:
- Update `apps/web/components/features/analytics/AnalyticsPageHeader.tsx` — wire export button to `useAnalyticsExport`
- `apps/web/lib/hooks/use-analytics-export.ts` — serialize `UsageResponse.items` to CSV; trigger download; handle empty data (header-only CSV + toast)

**Independent test**: Clicking export button downloads a `.csv` file. CSV has correct headers. Data matches active date range. Empty data produces header-only CSV and toast notification. Export button disabled during generation.

---

### Phase 8: Polish and Cross-Cutting

Goal: Accessibility, dark mode, responsive layout, outlier indicators.

**Files**:
- All section + chart components reviewed for:
  - `aria-label` on all interactive elements
  - Chart descriptions for screen readers (`role="img"` + `aria-label` on SVG containers)
  - Keyboard navigation for breakdown/horizon selectors
  - Dark mode color tokens (all colors via Tailwind CSS custom properties)
  - Mobile layout (single-column stack; scatter→table swap already in US2)
  - Outlier indicator: Y-axis max annotation when any value exceeds 3× period median
- `apps/web/app/(main)/analytics/page.tsx` — verify responsive layout, section order matches spec

---

## API Endpoints Used

| Endpoint | Feature | Used by |
|----------|---------|---------|
| `GET /api/v1/analytics/usage` | 020 | CostOverviewSection, TokenConsumptionSection, DriftDashboardSection |
| `GET /api/v1/analytics/cost-intelligence` | 020 | CostEfficiencySection |
| `GET /api/v1/analytics/recommendations` | 020 | CostEfficiencySection |
| `GET /api/v1/analytics/cost-forecast` | 020 | BudgetForecastSection |
| `GET /api/v1/analytics/kpi` | 020 | BudgetForecastSection |
| `GET /api/v1/context-engineering/drift-alerts` | 022 | DriftDashboardSection |

## Dependencies

- **FEAT-FE-001** (App scaffold, feature 015): Always required. Provides `useAppQuery`, `createApiClient`, `SectionError`, `MetricCard`, `useMediaQuery`, layout shell.
- **Feature 020** (Analytics and Cost Intelligence): Backend APIs must be deployed and serving data.
- **Feature 022** (Context Engineering): Drift alerts endpoint must be deployed for US4.

## Complexity Tracking

No constitution violations. No justification table needed.
