# Tasks: Operator Dashboard and Diagnostics

**Input**: Design documents from `specs/044-operator-dashboard-diagnostics/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in this phase)
- **[Story]**: Which user story this task belongs to (US1–US6 from spec.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: TypeScript types, route stubs, Zustand stores, and sidebar entry — foundational scaffolding consumed by every subsequent phase.

- [X] T001 Create `apps/web/lib/types/operator-dashboard.ts` with all enums and interfaces from data-model.md: `ServiceStatus`, `ServiceType`, `ActiveExecutionStatus`, `AlertSeverity`, `AttentionUrgency`, `AttentionTargetType`, `ReasoningMode`, `BudgetDimension`, `ContextSourceType`, `OperatorMetrics`, `ServiceHealthEntry`, `ServiceHealthSnapshot`, `SERVICE_DISPLAY_NAMES`, `ActiveExecution`, `ActiveExecutionsFilters`, `OperatorAlert`, `AlertFeedState`, `AttentionEvent`, `AttentionFeedState`, `QueueTopicLag`, `QueueLagSnapshot`, `ReasoningBudgetUtilization`, `SelfCorrectionIteration`, `ReasoningTraceStep`, `ReasoningTrace`, `ContextSource`, `ContextQualityView`, `BudgetDimensionUsage`, `BudgetStatus`, `ConnectionStatus`
- [X] T002 Create route stub `apps/web/app/(main)/operator/page.tsx` — placeholder with page title "Operator Dashboard" and section scaffolding comments for each US
- [X] T003 [P] Create route stub `apps/web/app/(main)/operator/executions/[executionId]/page.tsx` — placeholder with `params: { executionId: string }` and "Execution Drill-Down" title
- [X] T004 [P] Create `apps/web/lib/stores/use-alert-feed-store.ts` — Zustand store implementing `AlertFeedState`: `alerts` ring buffer (max 200, newest first), `isConnected`, `severityFilter`; `addAlert()` prepends + drops oldest if > 200; `setConnected()`, `setSeverityFilter()`, `clearAlerts()` actions; NOT persisted
- [X] T005 [P] Create `apps/web/lib/stores/use-attention-feed-store.ts` — Zustand store implementing `AttentionFeedState`: `events` array (newest first); `setEvents()` (initial load from REST), `addEvent()` (prepend, deduplicate by id), `acknowledgeEvent(id)` (set status to acknowledged); NOT persisted
- [X] T006 Add "Operator" sidebar entry in `apps/web/components/layout/sidebar/nav-config.ts` with path `/operator`, icon `Activity`, label "Operator", and `requiredRoles: ['platform_admin', 'superadmin']`

**Checkpoint**: Types, routes, stores, and sidebar ready — hook and component work can begin.

---

## Phase 2: Foundational (TanStack Query Hooks + WebSocket Wiring)

**Purpose**: All 8 data-fetching hooks — required by every user story phase. Must be complete before component implementation.

**⚠️ CRITICAL**: No US component work can begin until all hooks in this phase are complete.

- [X] T007 Create `apps/web/lib/hooks/use-operator-metrics.ts` — `useOperatorMetrics()` hook: `useQuery(['operatorMetrics'], GET /api/v1/dashboard/metrics, refetchInterval: 15_000)`; derive `isStale` as `Date.now() - new Date(metrics.computedAt).getTime() > 30_000`; return `{ metrics, isLoading, isStale }`
- [X] T008 [P] Create `apps/web/lib/hooks/use-service-health.ts` — `useServiceHealth()` hook: `useQuery(['serviceHealth'], GET /health, refetchInterval: 30_000)`; transform response `dependencies` dict to `ServiceHealthEntry[]` using `SERVICE_DISPLAY_NAMES` (missing keys default to `status: 'unknown'`); return `{ snapshot, isLoading }`
- [X] T009 [P] Create `apps/web/lib/hooks/use-active-executions.ts` — `useActiveExecutions(workspaceId, filters)` hook: `useQuery(['activeExecutions', workspaceId, filters], GET /api/v1/executions?workspace_id=…&status=running,paused,waiting_for_approval,compensating&page_size=100&sort_by=…, refetchInterval: 5_000)`; subscribe to `workspace:{workspaceId}` WS channel via `lib/ws.ts` and call `queryClient.invalidateQueries(['activeExecutions', workspaceId])` on any workspace execution event; return `{ executions, totalCount, isLoading }`
- [X] T010 [P] Create `apps/web/lib/hooks/use-alert-feed.ts` — `useAlertFeed()` hook: subscribe to `alerts` WS channel using `lib/ws.ts` (`{ type: 'subscribe', channel: 'alerts', resource_id: userId }`); on each incoming event call `useAlertFeedStore().addAlert()`; on WS connect set `setConnected(true)`, on disconnect set `setConnected(false)`; unsubscribe on unmount
- [X] T011 [P] Create `apps/web/lib/hooks/use-attention-feed.ts` — `useAttentionFeed(userId)` hook: `useQuery(['attentionFeedInit', userId], GET /api/v1/interactions/attention?status=pending&page_size=50, staleTime: Infinity)` with `onSuccess` calling `useAttentionFeedStore().setEvents()`; listen to auto-subscribed `attention:{userId}` WS channel; on each incoming event call `addEvent()` (deduplicates by id); return `{ isLoading }`
- [X] T012 [P] Create `apps/web/lib/hooks/use-queue-lag.ts` — `useQueueLag()` hook: `useQuery(['queueLag'], GET /api/v1/dashboard/queue-lag, refetchInterval: 15_000)`; return `{ data: QueueLagSnapshot | undefined, isLoading, isError }`
- [X] T013 [P] Create `apps/web/lib/hooks/use-reasoning-budget.ts` — `useReasoningBudget()` hook: `useQuery(['reasoningBudget'], GET /api/v1/dashboard/reasoning-budget-utilization, refetchInterval: 10_000)`; return `{ utilization: ReasoningBudgetUtilization | undefined, isLoading, isError }`
- [X] T014 [P] Create `apps/web/lib/hooks/use-execution-drill-down.ts` — exports 4 hooks: `useExecutionDetail(executionId)` (`staleTime: 30_000`), `useReasoningTrace(executionId)` (`staleTime: 60_000`), `useBudgetStatus(executionId, isActive)` (`refetchInterval: isActive ? 5_000 : undefined, staleTime: isActive ? 0 : Infinity`), `useContextQuality(executionId)` (`staleTime: 60_000`)

**Checkpoint**: All hooks ready — US component phases can begin in parallel.

---

## Phase 3: User Story 1 — Operator Overview (Priority: P1) 🎯 MVP

**Goal**: Metric card grid + service health panel visible on `/operator`.

**Independent Test**: Open `/operator`. Confirm 6 MetricCards render with current values. Confirm service health panel shows 12 service indicators with color-coded status dots. Confirm ConnectionStatusBanner appears when WS is disconnected.

- [X] T015 [P] [US1] Create `apps/web/components/features/operator/ServiceHealthIndicator.tsx` — single service entry: color-coded dot (green=healthy, yellow=degraded, red=unhealthy, gray=unknown), `displayName`, latency in ms; shadcn `Tooltip` on hover showing status label, latency ms, last checked time; accepts `ServiceHealthEntry` prop
- [X] T016 [P] [US1] Create `apps/web/components/features/operator/ConnectionStatusBanner.tsx` — shadcn `Alert` (destructive/warning variant) rendered only when `isConnected === false`; animated spinner + "Live updates paused — reconnecting..."; appends "(polling every 30 seconds)" to message when `isPollingFallback === true`; no dismiss button; accepts `{ isConnected: boolean; isPollingFallback: boolean }` props
- [X] T017 [US1] Create `apps/web/components/features/operator/ServiceHealthPanel.tsx` — two-section layout: "Data Stores" (8 entries: postgresql, redis, kafka, qdrant, neo4j, clickhouse, opensearch, minio) and "Satellite Services" (4 entries: runtime_controller, reasoning_engine, sandbox_manager, simulation_controller); each entry via `ServiceHealthIndicator`; header badge showing overall status; skeleton rows when loading; accepts `{ snapshot: ServiceHealthSnapshot | undefined; isLoading: boolean }` props
- [X] T018 [US1] Create `apps/web/components/features/operator/OperatorMetricsGrid.tsx` — 2×3 responsive grid of 6 shared `MetricCard` components; cards: Active Executions, Queued Steps, Pending Approvals, Recent Failures (1h), Avg Latency (p50), Fleet Health Score; skeleton cards when loading; amber "Stale" badge on each card when `isStale === true`; red tint on Failures and Pending Approvals cards when value > 0; accepts `{ metrics: OperatorMetrics | undefined; isLoading: boolean; isStale?: boolean }` props
- [X] T019 [US1] Wire US1 components into `apps/web/app/(main)/operator/page.tsx`: call `useOperatorMetrics()` and `useServiceHealth()`; render `ConnectionStatusBanner`, `OperatorMetricsGrid`, `ServiceHealthPanel` with correct props

---

## Phase 4: User Story 2 — Active Executions Table (Priority: P1)

**Goal**: Real-time executions DataTable with live elapsed counter and drill-down navigation.

**Independent Test**: Open `/operator`. Confirm executions DataTable renders with all 7 columns. Confirm elapsed counter ticks without polling. Confirm status filter dropdown narrows the table. Click a row — confirm navigation to `/operator/executions/{id}`.

- [X] T020 [P] [US2] Create `apps/web/components/features/operator/ActiveExecutionStatusBadge.tsx` — shadcn `Badge`; color mapping: `running` → green (variant `success` or Tailwind `bg-green-500`), `paused` → yellow (`bg-yellow-500`), `waiting_for_approval` → blue (`bg-blue-500`), `compensating` → orange (`bg-orange-500`); accepts `{ status: ActiveExecutionStatus }` prop
- [X] T021 [US2] Create `apps/web/components/features/operator/ActiveExecutionsTable.tsx` — shared `DataTable` + TanStack Table columns: execution ID (first 8 chars + copy icon via `navigator.clipboard`), agent FQN, workflow name, current step (dash if null), `ActiveExecutionStatusBadge`, start time (`date-fns format`), elapsed duration (live `useInterval` counter updates display every 1s without refetch); status filter dropdown (All / Running / Paused / Waiting Approval); sort by started_at or elapsed; `onRowClick(executionId)` callback; loading skeleton; empty state "No active executions"; accepts `ActiveExecutionsTableProps` interface from component-contracts.md
- [X] T022 [US2] Wire ActiveExecutionsTable into `apps/web/app/(main)/operator/page.tsx`: call `useActiveExecutions(workspaceId, filters)` with local filter state; pass `onRowClick` → `router.push('/operator/executions/${executionId}')`

---

## Phase 5: User Story 3 — Alert Feed (Priority: P1)

**Goal**: Real-time WebSocket alert log with auto-scroll control and severity filtering.

**Independent Test**: Open `/operator`. Confirm alert feed renders. Simulate incoming alert — confirm it prepends to the list. Filter by "error" — confirm only error alerts shown. Scroll up — confirm "New alerts ↓" button appears.

- [X] T023 [P] [US3] Create `apps/web/components/features/operator/AlertFeedItem.tsx` — shadcn `Collapsible`; collapsed: severity badge (info=blue, warning=yellow, error=orange, critical=red/destructive), `sourceService` label, `date-fns formatDistanceToNow(timestamp)`, `message` summary; expanded: `description` text + `suggestedAction` paragraph (both only when present); accepts `{ alert: OperatorAlert }` prop
- [X] T024 [US3] Create `apps/web/components/features/operator/AlertFeed.tsx` — calls `useAlertFeed()` on mount (starts WS subscription); reads alerts from `useAlertFeedStore()` filtered by `severityFilter`; scrollable container (max-height configurable, default `400px`); auto-scroll logic using `useRef` scroll anchor + `useEffect` — scrolls to bottom when new alerts arrive and `isScrolledToBottom === true`; `onScroll` handler sets `isScrolledToBottom = false` when user scrolls up; sticky "New alerts ↓" `Button` at bottom when `!isScrolledToBottom`; clicking button or reaching bottom resumes auto-scroll; severity filter tabs (All / Info / Warning / Error / Critical) wired to `setSeverityFilter`; empty state "No alerts received yet"; renders `AlertFeedItem` list
- [X] T025 [US3] Wire AlertFeed into `apps/web/app/(main)/operator/page.tsx`

---

## Phase 6: User Story 5 — Queue Backlog & Reasoning Budget (Priority: P2)

**Goal**: Kafka consumer lag bar chart + aggregate reasoning budget gauge.

**Independent Test**: Open `/operator`. Confirm bar chart renders one bar per topic. Topics with lag > 10,000 show amber bars. Reasoning budget gauge shows utilization %. At ≥90% utilization, gauge turns red with "Capacity pressure" label.

- [X] T026 [P] [US5] Create `apps/web/components/features/operator/QueueBacklogChart.tsx` — Recharts `BarChart` + `ResponsiveContainer`; maps `QueueTopicLag[]` to bar chart data; bar fill: `warning === true` → `fill-amber-500`, else primary chart color; abbreviated topic name on X-axis ticks; `Tooltip` showing topic name + lag count + "⚠ High lag" when warning; Y-axis auto-scaled; "Backlog data unavailable" empty state with retry `Button` when `error`; skeleton bar chart when loading; accepts `{ data: QueueTopicLag[]; isLoading: boolean; error?: boolean }` props
- [X] T027 [P] [US5] Create `apps/web/components/features/operator/ReasoningBudgetGauge.tsx` — shared `ScoreGauge` component with `utilizationPct` as score (0–100); gauge color: <70% → green, 70–89% → yellow, ≥90% → red; center label `{utilizationPct}%`; below gauge: `{activeExecutionCount} active executions`; when `criticalPressure === true`: red gauge + bold red label "Capacity pressure"; "Budget data unavailable" placeholder when `error`; accepts `{ utilization: ReasoningBudgetUtilization | undefined; isLoading: boolean; error?: boolean }` props
- [X] T028 [US5] Wire QueueBacklogChart and ReasoningBudgetGauge into `apps/web/app/(main)/operator/page.tsx`: call `useQueueLag()` and `useReasoningBudget()`; pass derived `data`, `isLoading`, `error` props

---

## Phase 7: User Story 6 — Attention Feed (Priority: P2)

**Goal**: Dedicated agent attention requests panel with urgency color coding and context navigation.

**Independent Test**: Open `/operator`. Confirm attention feed panel renders separately from alert feed. Critical attention events show red badge + bold border. Click an attention event targeting an execution — confirm navigation to `/operator/executions/{id}`.

- [X] T029 [P] [US6] Create `apps/web/components/features/operator/AttentionFeedItem.tsx` — urgency badge color mapping: low=gray (`bg-gray-400`), medium=blue (`bg-blue-500`), high=orange (`bg-orange-500`), critical=red destructive; critical events: `border-l-4 border-red-500 font-semibold` left-border accent; shows: urgency badge, `sourceAgentFqn`, `date-fns formatDistanceToNow(createdAt)`, `contextSummary`; click handler: navigate to `/operator/executions/{targetId}` when `targetType === 'execution'`, `/conversations/{targetId}` when `targetType === 'interaction'`, or `/workspaces/goals/{targetId}` when `targetType === 'goal'`; accepts `{ event: AttentionEvent; onClick: (event: AttentionEvent) => void }` props
- [X] T030 [US6] Create `apps/web/components/features/operator/AttentionFeedPanel.tsx` — calls `useAttentionFeed(userId)` on mount (starts WS sync + initial REST load); reads events from `useAttentionFeedStore()` (newest first, pending only); header with "Agent Attention" label + unread badge count (pending events where `status === 'pending'`); renders `AttentionFeedItem` list with `onClick` → `router.push(…)`; empty state "No pending attention requests"; accepts `{ className?: string }` prop
- [X] T031 [US6] Wire AttentionFeedPanel into `apps/web/app/(main)/operator/page.tsx`

---

## Phase 8: User Story 4 — Execution Drill-Down (Priority: P2)

**Goal**: Per-execution diagnostic view with reasoning traces, context quality, and budget bars.

**Independent Test**: Navigate to `/operator/executions/{id}`. Confirm reasoning trace renders collapsible steps with mode, tokens, duration. Expand a step — confirm self-correction chain visible. Confirm context quality ScoreGauge + provenance table. Confirm budget Progress bars with correct utilization colors. Confirm breadcrumb returns to `/operator`.

- [X] T032 [P] [US4] Create `apps/web/components/features/operator/ReasoningTraceStep.tsx` — shadcn `AccordionItem`; collapsed trigger: step number, reasoning mode label, token count, duration (`{ms}ms`), self-correction badge (`{n} corrections` when > 0); expanded content: `inputSummary` + `outputSummary` (each with "Show full output" `Button` when `fullOutputRef !== null` to fetch/expand full text); self-correction chain: each `SelfCorrectionIteration` renders `originalOutputSummary` → correction reason → `correctedOutputSummary`; accepts `{ step: ReasoningTraceStep; stepNumber: number }` props
- [X] T033 [P] [US4] Create `apps/web/components/features/operator/ContextQualityPanel.tsx` — shared `ScoreGauge` for `overallQualityScore`; table of `ContextSource[]`: source type display label, quality score badge (0–49=red, 50–74=yellow, 75–100=green), contribution weight as `{(weight * 100).toFixed(0)}%`, `provenanceRef` as `<a>` link when non-null; `assembledAt` footer timestamp via `date-fns format`; scalar-only fallback (gauge + "Full provenance unavailable") when `sources` array empty; accepts `{ quality: ContextQualityView | undefined; isLoading: boolean }` props
- [X] T034 [P] [US4] Create `apps/web/components/features/operator/BudgetConsumptionPanel.tsx` — 4 shadcn `Progress` bars for `BudgetDimensionUsage[]`; `indicatorClassName` color by `utilizationPct`: <70% → blue, 70–89% → yellow (`bg-yellow-500`), ≥90% → red (`bg-red-500`); label row: dimension `label` + `{used} / {limit} {unit}`; Lucide `AlertTriangle` icon next to label when `nearLimit === true`; "Execution completed — final values" `Alert` banner when `isActive === false`; 4 skeleton `Progress` bars when loading; accepts `{ budget: BudgetStatus | undefined; isLoading: boolean }` props
- [X] T035 [US4] Create `apps/web/components/features/operator/ReasoningTracePanel.tsx` — summary bar at top: `{totalTokens} tokens · {totalDurationMs}ms · {totalCorrectionIterations} corrections`; shadcn `Accordion` (type="multiple") wrapping `ReasoningTraceStep[]` in step order; empty state "No reasoning steps recorded" when `steps.length === 0`; loading skeleton (3 collapsed accordion items); accepts `{ trace: ReasoningTrace | undefined; isLoading: boolean }` props
- [X] T036 [US4] Create `apps/web/components/features/operator/ExecutionDrilldown.tsx` — calls `useExecutionDetail(executionId)`, `useReasoningTrace(executionId)`, `useBudgetStatus(executionId, isActive)`, `useContextQuality(executionId)` from `use-execution-drill-down.ts`; header: execution ID (monospace), `ActiveExecutionStatusBadge`, agent FQN, workflow name, duration; shadcn `Tabs` defaultValue="reasoning-trace" with 3 tabs: "Reasoning Trace" → `ReasoningTracePanel`, "Context Quality" → `ContextQualityPanel`, "Budget Consumption" → `BudgetConsumptionPanel`; breadcrumb `<Link href="/operator">← Operator</Link>`; loading skeleton while any data loads; accepts `{ executionId: string }` prop
- [X] T037 [US4] Wire ExecutionDrilldown into `apps/web/app/(main)/operator/executions/[executionId]/page.tsx`: extract `executionId` from `params`; render `<ExecutionDrilldown executionId={executionId} />`

---

## Phase 9: Tests & Polish

**Goal**: Unit test coverage ≥95% for new components; Playwright E2E for full dashboard and drill-down flows.

- [X] T038 Write unit tests for `OperatorMetricsGrid` and `ServiceHealthPanel` in `apps/web/__tests__/features/operator/OperatorMetricsGrid.test.tsx` and `apps/web/__tests__/features/operator/ServiceHealthPanel.test.tsx` — MSW handlers for `/api/v1/dashboard/metrics` and `/health`; test: renders 6 MetricCards, stale badge, red tint; test: renders 12 service indicators, correct color coding per status, skeleton on loading
- [X] T039 [P] Write unit tests for `ActiveExecutionsTable` in `apps/web/__tests__/features/operator/ActiveExecutionsTable.test.tsx` — MSW handler for `/api/v1/executions`; test: renders all 7 columns, status filter narrows rows, sort changes order, elapsed counter ticks, row click fires onRowClick callback
- [X] T040 [P] Write unit tests for `AlertFeed` and `AlertFeedItem` in `apps/web/__tests__/features/operator/AlertFeed.test.tsx` — mock `useAlertFeedStore`; test: renders alert list, severity filter tabs, auto-scroll pause on scroll-up, "New alerts ↓" button appears, collapsed/expanded Collapsible toggle
- [X] T041 [P] Write unit tests for `AttentionFeedPanel` in `apps/web/__tests__/features/operator/AttentionFeedPanel.test.tsx` — mock `useAttentionFeedStore`; test: renders events newest-first, unread badge count, critical event red border, click navigates to correct route per targetType
- [X] T042 [P] Write unit tests for `QueueBacklogChart` and `ReasoningBudgetGauge` in `apps/web/__tests__/features/operator/QueueBacklogChart.test.tsx` and `apps/web/__tests__/features/operator/ReasoningBudgetGauge.test.tsx` — test: amber bar rendered for warning topics; test: gauge color matches utilization thresholds, "Capacity pressure" label at criticalPressure
- [X] T043 [P] Write unit tests for `ReasoningTracePanel` and `BudgetConsumptionPanel` in `apps/web/__tests__/features/operator/ReasoningTracePanel.test.tsx` and `apps/web/__tests__/features/operator/BudgetConsumptionPanel.test.tsx` — test: accordion renders all steps, self-correction chain visible on expand; test: 4 Progress bars, correct color classes by utilization, warning icon on nearLimit, "Execution completed" banner when isActive false
- [X] T044 Write Playwright E2E test in `apps/web/e2e/operator.spec.ts` — full flow: navigate to `/operator`, assert 6 MetricCards + service health panel + alert feed + attention feed + queue chart + budget gauge; click executions table row → assert drill-down page loads with 3 tabs; expand reasoning step; assert breadcrumb navigates back to `/operator`

---

## Dependencies

```text
Phase 1 (Setup) → Phase 2 (Hooks) → Phases 3–8 (User Stories, all in parallel)
                                  ↓
                            Phase 9 (Tests)

Story dependencies:
  US1 (T015–T019) — independent
  US2 (T020–T022) — independent; requires Phase 2 complete
  US3 (T023–T025) — independent; requires Phase 2 complete
  US5 (T026–T028) — independent; requires Phase 2 complete
  US6 (T029–T031) — independent; requires Phase 2 complete
  US4 (T032–T037) — requires US2 (ActiveExecutionStatusBadge reused in drill-down header)
```

## Parallel Execution Per Story

Within each user story phase, [P]-marked tasks can run concurrently:

**Phase 2 (Hooks)**: T008–T014 all parallel (independent files)  
**Phase 3 (US1)**: T015 + T016 in parallel, then T017, then T018, then T019  
**Phase 4 (US2)**: T020 in parallel with Phase 3, then T021, then T022  
**Phase 5 (US3)**: T023 in parallel with Phase 4, then T024, then T025  
**Phase 6 (US5)**: T026 + T027 in parallel, then T028  
**Phase 7 (US6)**: T029 in parallel with Phase 6, then T030, then T031  
**Phase 8 (US4)**: T032 + T033 + T034 in parallel, then T035, then T036, then T037  
**Phase 9 (Tests)**: T039–T043 all parallel, then T044  

## Implementation Strategy

**MVP (Phase 1 + Phase 2 + Phase 3)**: Types, hooks, and US1 overview panel — operator can see platform health.  
**Increment 2 (Phase 4 + Phase 5)**: Active executions table + alert feed — real-time monitoring fully operational.  
**Increment 3 (Phase 6 + Phase 7)**: Queue backlog + budget gauge + attention feed — capacity and agentic signals.  
**Increment 4 (Phase 8)**: Execution drill-down — diagnostic investigation capability.  
**Increment 5 (Phase 9)**: Tests + Polish.

## Task Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Phase 1 — Setup | T001–T006 | 6 |
| Phase 2 — Hooks | T007–T014 | 8 |
| Phase 3 — US1 | T015–T019 | 5 |
| Phase 4 — US2 | T020–T022 | 3 |
| Phase 5 — US3 | T023–T025 | 3 |
| Phase 6 — US5 | T026–T028 | 3 |
| Phase 7 — US6 | T029–T031 | 3 |
| Phase 8 — US4 | T032–T037 | 6 |
| Phase 9 — Tests | T038–T044 | 7 |
| **Total** | | **44** |
