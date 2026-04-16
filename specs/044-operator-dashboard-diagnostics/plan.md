# Implementation Plan: Operator Dashboard and Diagnostics

**Branch**: `044-operator-dashboard-diagnostics` | **Date**: 2026-04-16 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/044-operator-dashboard-diagnostics/spec.md`

## Summary

Real-time operator monitoring dashboard with two routes: `/operator` (main overview) and `/operator/executions/[executionId]` (drill-down). The overview aggregates 6 MetricCards, 12-service health panel, live active executions table, WebSocket alert feed (Zustand ring buffer, max 200), queue backlog bar chart, reasoning budget gauge (shared ScoreGauge), and attention feed. The drill-down shows reasoning trace (accordion), context quality provenance (ScoreGauge + table), and budget consumption (Progress bars per dimension). All real-time data via TanStack Query polling + WebSocket invalidation using the existing `lib/ws.ts` hub.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router  
**Primary Dependencies**: shadcn/ui, Tailwind CSS 3.4+, TanStack Query v5, Zustand 5.x, Recharts 2.x, date-fns 4.x, Lucide React, existing `lib/ws.ts` WebSocketClient  
**Storage**: N/A (frontend only — reads from backend APIs)  
**Testing**: Vitest + React Testing Library + Playwright + MSW  
**Target Platform**: Web (desktop-primary, responsive)  
**Project Type**: Next.js web application feature  
**Performance Goals**: Active executions table refresh ≤5s; alert feed real-time; dashboard metrics ≤15s stale  
**Constraints**: No new npm packages; reuse shared ScoreGauge, MetricCard, DataTable components; WebSocket fallback to polling on disconnect  
**Scale/Scope**: Up to 100 active executions in table; alert ring buffer capped at 200; 12 service health indicators

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| No new npm packages | PASS | All libraries in existing stack: Recharts (fleet dashboard), ScoreGauge (015), shadcn Progress/Accordion, existing WS client |
| shadcn/ui for all UI primitives | PASS | Badge, DataTable, Alert, Accordion, Collapsible, Progress, Tooltip, Tabs — all shadcn |
| Tailwind CSS only (no custom CSS) | PASS | All styling via utility classes |
| TanStack Query for server state | PASS | 10 hooks with defined polling intervals |
| Zustand for client state | PASS | Two stores: alert ring buffer + attention feed |
| Function components only | PASS | No class components |
| Shared components reused | PASS | MetricCard, DataTable, ScoreGauge, EmptyState, StatusBadge |
| TypeScript strict mode | PASS | All types in `lib/types/operator-dashboard.ts` |
| Route guard | PASS | `requiredRoles: ['platform_admin', 'superadmin']` in nav-config.ts |

## Project Structure

### Documentation (this feature)

```text
specs/044-operator-dashboard-diagnostics/
├── plan.md              # This file
├── spec.md
├── research.md          # 9 decisions
├── data-model.md        # TypeScript types for all entities
├── quickstart.md        # Setup, routes, test commands
├── contracts/
│   ├── api-consumed.md  # 10 TanStack Query hooks + 3 WS subscriptions
│   └── component-contracts.md  # 17 component interfaces
└── tasks.md             # Phase 2 output (speckit.tasks)
```

### Source Code

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
│   │   ├── use-active-executions.ts              # useActiveExecutions() polling 5s + WS
│   │   ├── use-alert-feed.ts                     # WS subscription + store sync
│   │   ├── use-attention-feed.ts                 # REST init + WS auto-sub sync
│   │   ├── use-queue-lag.ts                      # useQueueLag() polling 15s
│   │   ├── use-reasoning-budget.ts               # useReasoningBudget() polling 10s
│   │   └── use-execution-drill-down.ts           # useReasoningTrace, useBudgetStatus, useContextQuality
│   ├── stores/
│   │   ├── use-alert-feed-store.ts               # Zustand alert ring buffer (max 200)
│   │   └── use-attention-feed-store.ts           # Zustand attention events
│   └── types/
│       └── operator-dashboard.ts                 # All feature TypeScript types
│
└── __tests__/features/operator/
    ├── OperatorMetricsGrid.test.tsx
    ├── ServiceHealthPanel.test.tsx
    ├── ActiveExecutionsTable.test.tsx
    ├── AlertFeed.test.tsx
    ├── AttentionFeedPanel.test.tsx
    ├── QueueBacklogChart.test.tsx
    ├── ReasoningBudgetGauge.test.tsx
    ├── ReasoningTracePanel.test.tsx
    └── BudgetConsumptionPanel.test.tsx
```

## Implementation Phases

### Phase 1: Types + Routes + Zustand Stores

**Goal**: Foundational types and empty routes.

- Create `lib/types/operator-dashboard.ts` — all enums and interfaces from `data-model.md`
- Create `app/(main)/operator/page.tsx` — placeholder page with layout
- Create `app/(main)/operator/executions/[executionId]/page.tsx` — placeholder drill-down page
- Create `lib/stores/use-alert-feed-store.ts` — Zustand ring buffer (max 200, newest first)
- Create `lib/stores/use-attention-feed-store.ts` — Zustand events store (setEvents, addEvent, acknowledgeEvent)
- Add sidebar entry in `apps/web/components/layout/sidebar/nav-config.ts` with `requiredRoles: ['platform_admin', 'superadmin']`

### Phase 2: TanStack Query Hooks + WebSocket Wiring

**Goal**: All data-fetching hooks and WebSocket subscriptions ready for components.

- `lib/hooks/use-operator-metrics.ts` — GET `/api/v1/dashboard/metrics`, refetchInterval 15s, `computedAt` staleness check
- `lib/hooks/use-service-health.ts` — GET `/health`, refetchInterval 30s, map `dependencies` dict → `ServiceHealthEntry[]` via `SERVICE_DISPLAY_NAMES`
- `lib/hooks/use-active-executions.ts` — GET `/api/v1/executions?status=running,...`, refetchInterval 5s, subscribe to `workspace:{workspaceId}` WS channel for invalidation
- `lib/hooks/use-alert-feed.ts` — subscribe to `alerts` WS channel; pipe events into `useAlertFeedStore.addAlert()`
- `lib/hooks/use-attention-feed.ts` — `useAttentionFeedInit` query (GET `/api/v1/interactions/attention?status=pending`) + listen to `attention:{userId}` auto-subscribed WS channel → `useAttentionFeedStore.addEvent()`
- `lib/hooks/use-queue-lag.ts` — GET `/api/v1/dashboard/queue-lag`, refetchInterval 15s
- `lib/hooks/use-reasoning-budget.ts` — GET `/api/v1/dashboard/reasoning-budget-utilization`, refetchInterval 10s
- `lib/hooks/use-execution-drill-down.ts` — exports `useExecutionDetail`, `useReasoningTrace`, `useBudgetStatus`, `useContextQuality` hooks

### Phase 3: Operator Overview — US1 (Metrics + Service Health)

**Goal**: Top-of-dashboard health snapshot.

- `components/features/operator/OperatorMetricsGrid.tsx` — 2×3 responsive grid of 6 MetricCards; skeleton on loading; amber stale badge when `isStale`; red tint on failures/pending approval cards
- `components/features/operator/ServiceHealthIndicator.tsx` — color-coded dot (green/yellow/red/gray) + display name + latency ms; shadcn Tooltip on hover (status, latency, last checked)
- `components/features/operator/ServiceHealthPanel.tsx` — two sections (Data Stores: 8 entries, Satellite Services: 4 entries); overall status badge; skeleton rows on loading
- `components/features/operator/ConnectionStatusBanner.tsx` — shadcn Alert (warning) shown when `isConnected === false`; spinner + "Live updates paused"; adds polling message when `isPollingFallback`
- Wire into `app/(main)/operator/page.tsx`

### Phase 4: Active Executions — US2

**Goal**: Real-time executions table.

- `components/features/operator/ActiveExecutionStatusBadge.tsx` — shadcn Badge; running=green, paused=yellow, waiting_for_approval=blue, compensating=orange
- `components/features/operator/ActiveExecutionsTable.tsx` — shadcn DataTable + TanStack Table; columns: ID (truncated 8+copy), agent FQN, workflow name, current step, status badge, start time, elapsed (live counter via `useInterval`); status filter dropdown; sort by start time/elapsed; `onRowClick` → navigate to drill-down

### Phase 5: Alert Feed — US3

**Goal**: Real-time scrollable alert log.

- `components/features/operator/AlertFeedItem.tsx` — shadcn Collapsible; collapsed: severity badge + source + timestamp (`formatDistanceToNow`) + message; expanded: description + suggestedAction
- `components/features/operator/AlertFeed.tsx` — reads `useAlertFeedStore`; auto-scroll to bottom (paused when user scrolls up); "New alerts ↓" sticky button; severity filter tabs (All/Info/Warning/Error/Critical); empty state

### Phase 6: Queue Backlog + Reasoning Budget — US5

**Goal**: Capacity pressure indicators.

- `components/features/operator/QueueBacklogChart.tsx` — Recharts BarChart + ResponsiveContainer; one bar per topic; amber fill when `warning: true` (lag > 10,000); Tooltip with topic + lag + "⚠ High lag"; "Backlog data unavailable" error state + retry; skeleton on loading
- `components/features/operator/ReasoningBudgetGauge.tsx` — shared ScoreGauge with `utilizationPct`; green <70%, yellow 70–89%, red ≥90%; center text `{pct}%`; active execution count below; "Capacity pressure" red label when `criticalPressure`

### Phase 7: Attention Feed — US6

**Goal**: Agent attention requests panel.

- `components/features/operator/AttentionFeedItem.tsx` — urgency badge (low=gray, medium=blue, high=orange, critical=red); red left border for critical; source agent FQN + timestamp + context summary; click → navigate to linked context URL
- `components/features/operator/AttentionFeedPanel.tsx` — reads `useAttentionFeedStore`; list newest first; unread badge on panel header; empty state "No pending attention requests"

### Phase 8: Execution Drill-Down — US4

**Goal**: Per-execution diagnostic panels.

- `components/features/operator/ReasoningTraceStep.tsx` — shadcn AccordionItem; collapsed: step #, mode label, tokens, duration, self-correction badge; expanded: input/output summaries with "Show full output" toggle; self-correction chain display
- `components/features/operator/ReasoningTracePanel.tsx` — renders `ReasoningTraceStep` list; summary bar (total tokens + duration + corrections); empty state
- `components/features/operator/ContextQualityPanel.tsx` — ScoreGauge for overall score; table of ContextSource entries (type, score, weight%, provenance link); assembly timestamp footer; scalar fallback
- `components/features/operator/BudgetConsumptionPanel.tsx` — 4 Progress bars (tokens/tool_invocations/memory_writes/elapsed_time); blue→yellow→red color by utilization; "X / Y unit" labels; warning icon if `nearLimit`; "Execution completed" notice when `isActive === false`
- `components/features/operator/ExecutionDrilldown.tsx` — execution header (ID, status, agent FQN, workflow, duration) + shadcn Tabs (Reasoning Trace | Context Quality | Budget Consumption); breadcrumb back to `/operator`
- Wire into `app/(main)/operator/executions/[executionId]/page.tsx`

### Phase 9: Tests + Polish

**Goal**: Test coverage ≥95% for new components; responsive layout; dark mode.

- Unit tests for all 9 component files (Vitest + RTL + MSW)
- Vitest + RTL for hooks (mock fetch + Zustand store)
- Playwright E2E: `e2e/operator.spec.ts` covering full dashboard flow and drill-down navigation
- Responsive layout verification (mobile sidebar, grid breakpoints)
- Dark mode token verification

## Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Route structure | `/operator` + `/operator/executions/[id]` | Drill-down needs full-width layout for 3 diagnostic panels |
| Metrics endpoint | Assumed `GET /api/v1/dashboard/metrics` | No single existing endpoint returns all 6 indicators |
| Service health | Reuse `GET /health` | Existing endpoint covers all 12 dependencies |
| Active executions | 5s polling + WS workspace invalidation | No global execution broadcast channel in WS hub |
| Alert feed | Zustand ring buffer (max 200), WS-only | No REST alert history endpoint |
| Attention feed | REST init + auto-subscribed WS `attention:{userId}` | Channel auto-subscribed by hub; no polling needed |
| Queue lag | Assumed `GET /api/v1/dashboard/queue-lag` | Cannot connect to Kafka AdminClient from browser |
| Reasoning budget | Assumed `GET /api/v1/dashboard/reasoning-budget-utilization` | N+1 query per execution is too slow |
| Reasoning trace | Assumed structured endpoint + journal fallback | Raw journal payloads are untyped |
| Budget gauge | Reuse shared ScoreGauge (feature 015) | Already used for fleet health and trust radar |
| New packages | None | All capabilities in existing stack |
