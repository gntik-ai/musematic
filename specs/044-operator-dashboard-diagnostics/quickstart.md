# Quickstart: Operator Dashboard and Diagnostics

## Prerequisites

- Node.js 20+, pnpm 9+
- Backend APIs operational: analytics (020), execution engine (029), interactions (024), trust service (032 for fleet health)
- Development server for `apps/web` running

## New Dependencies

**None.** All required libraries are already installed:

- `shadcn/ui` — MetricCard (shared), DataTable, Tabs, Badge, Alert, Accordion, Collapsible, Progress, Tooltip
- `Recharts 2.x` — BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, RadialBarChart (via ScoreGauge shared component)
- `TanStack Query v5` — all server state (10 query hooks with polling)
- `Zustand 5.x` — alert ring buffer store + attention feed store
- `date-fns 4.x` — timestamp formatting, elapsed duration computation
- `Lucide React` — icons (AlertCircle, Activity, Server, Zap, etc.)

**No new npm packages** — all in the existing frontend stack. The `ScoreGauge` shared component (feature 015) is reused for the reasoning budget gauge.

## Running the Dev Server

```bash
cd apps/web
pnpm dev
```

Navigate to:
- `http://localhost:3000/operator` — Main operator dashboard
- `http://localhost:3000/operator/executions/{executionId}` — Execution drill-down

## Running Tests

```bash
cd apps/web
pnpm exec vitest run __tests__/features/operator
PLAYWRIGHT_BASE_URL=http://localhost:3000 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm exec playwright test e2e/operator.spec.ts --project=chromium
```

If Playwright-managed browsers are not installed in the environment, the runner also supports system browser fallbacks through:

- `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`
- `PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH`

## Project Structure

```text
apps/web/
├── app/(main)/operator/
│   ├── page.tsx                                  # Main dashboard (US1–US3, US5–US6)
│   └── executions/[executionId]/
│       └── page.tsx                              # Execution drill-down (US4)
│
├── components/features/operator/
│   ├── OperatorMetricsGrid.tsx                   # 6 MetricCards (US1)
│   ├── ServiceHealthPanel.tsx                    # 12 service indicators (US1)
│   ├── ServiceHealthIndicator.tsx                # Single service dot + label (US1)
│   ├── ActiveExecutionsTable.tsx                 # Real-time DataTable (US2)
│   ├── ActiveExecutionStatusBadge.tsx            # Status badge (US2)
│   ├── AlertFeed.tsx                             # Scrolling alert list (US3)
│   ├── AlertFeedItem.tsx                         # Single alert (US3)
│   ├── AttentionFeedPanel.tsx                    # Agent attention requests (US6)
│   ├── AttentionFeedItem.tsx                     # Single attention card (US6)
│   ├── QueueBacklogChart.tsx                     # Recharts BarChart (US5)
│   ├── ReasoningBudgetGauge.tsx                  # ScoreGauge + utilization (US5)
│   ├── ConnectionStatusBanner.tsx                # WS disconnect banner (all)
│   ├── ExecutionDrilldown.tsx                    # Drill-down container (US4)
│   ├── ReasoningTracePanel.tsx                   # Trace accordion (US4)
│   ├── ReasoningTraceStep.tsx                    # Single trace step (US4)
│   ├── ContextQualityPanel.tsx                   # Provenance + quality (US4)
│   └── BudgetConsumptionPanel.tsx                # Progress bars (US4)
│
├── lib/
│   ├── hooks/
│   │   ├── use-operator-metrics.ts               # useOperatorMetrics() polling 15s
│   │   ├── use-service-health.ts                 # useServiceHealth() polling 30s
│   │   ├── use-active-executions.ts              # useActiveExecutions() polling 5s + WS invalidation
│   │   ├── use-alert-feed.ts                     # WS subscription + store sync
│   │   ├── use-attention-feed.ts                 # REST init + WS auto-sub sync
│   │   ├── use-queue-lag.ts                      # useQueueLag() polling 15s
│   │   ├── use-reasoning-budget.ts               # useReasoningBudget() polling 10s
│   │   └── use-execution-drill-down.ts           # useReasoningTrace, useBudgetStatus, useContextQuality
│   ├── stores/
│   │   ├── use-alert-feed-store.ts               # Zustand alert ring buffer
│   │   └── use-attention-feed-store.ts           # Zustand attention events
│   └── types/
│       └── operator-dashboard.ts                 # All feature TypeScript types
│
├── __tests__/features/operator/
│   ├── OperatorMetricsGrid.test.tsx
│   ├── ServiceHealthPanel.test.tsx
│   ├── ActiveExecutionsTable.test.tsx
│   ├── AlertFeed.test.tsx
│   ├── AttentionFeedPanel.test.tsx
│   ├── QueueBacklogChart.test.tsx
│   ├── ReasoningBudgetGauge.test.tsx
│   ├── ReasoningTracePanel.test.tsx
│   ├── BudgetConsumptionPanel.test.tsx
│   └── test-helpers.tsx
│
└── e2e/
    ├── operator.spec.ts                          # Full dashboard E2E flow
    └── operator/
        └── helpers.ts                            # API + WebSocket fixtures for E2E
```

## Key Configuration

No new environment variables required.

**Sidebar entry**: Add "Operator" entry in `apps/web/components/layout/sidebar/nav-config.ts` with `requiredRoles: ['platform_admin', 'superadmin']`.

**WebSocket subscriptions**:
- `alerts` channel — manually subscribed when operator page mounts via `use-alert-feed.ts`
- `attention:{userId}` — auto-subscribed by the WebSocket hub (no manual subscribe needed)
- `workspace:{workspaceId}` — subscribed in `use-active-executions.ts` for query invalidation

## API Assumptions

These endpoints are assumed to exist (or be added to the dashboard bounded context):

1. `GET /api/v1/dashboard/metrics` — aggregate operational snapshot
2. `GET /api/v1/dashboard/queue-lag` — Kafka consumer lag by topic
3. `GET /api/v1/dashboard/reasoning-budget-utilization` — aggregate budget gauge
4. `GET /api/v1/executions/{id}/reasoning-trace` — structured trace (falls back to journal parsing)
5. `GET /api/v1/executions/{id}/budget-status` — resource usage vs. limits
6. `GET /api/v1/executions/{id}/context-quality` — context provenance

Existing endpoints used directly:
- `GET /health` — service health
- `GET /api/v1/executions` — active executions list
- `GET /api/v1/interactions/attention` — attention requests initial load
