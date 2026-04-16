# Component Contracts: Operator Dashboard and Diagnostics

**Phase**: Phase 1 — Design  
**Feature**: [../spec.md](../spec.md)

---

## OperatorMetricsGrid

```typescript
// apps/web/components/features/operator/OperatorMetricsGrid.tsx
interface OperatorMetricsGridProps {
  metrics: OperatorMetrics | undefined
  isLoading: boolean
  isStale?: boolean                   // true if computedAt > 30s ago
}
```

**Behavior**: 2×3 or 3×2 responsive grid of 6 shared `MetricCard` components. Cards: Active Executions, Queued Steps, Pending Approvals, Recent Failures (1h), Avg Latency (p50), Fleet Health Score. Shows skeleton cards when loading. Shows amber stale badge on each card if `isStale`. Failures and pending approvals cards show red tint when > 0.

---

## ServiceHealthPanel

```typescript
// apps/web/components/features/operator/ServiceHealthPanel.tsx
interface ServiceHealthPanelProps {
  snapshot: ServiceHealthSnapshot | undefined
  isLoading: boolean
}
```

**Behavior**: Two-section layout: "Data Stores" (8 entries) and "Satellite Services" (4 entries). Each service rendered by `ServiceHealthIndicator`. Overall status shown as a header badge. Shows skeleton rows when loading.

---

## ServiceHealthIndicator

```typescript
// apps/web/components/features/operator/ServiceHealthIndicator.tsx
interface ServiceHealthIndicatorProps {
  entry: ServiceHealthEntry
}
```

**Behavior**: Color-coded dot + service display name + latency in ms. Dot colors: green (`healthy`), yellow (`degraded`), red (`unhealthy`), gray (`unknown`). shadcn Tooltip on hover shows: status label, latency, last checked time. Used in `ServiceHealthPanel`.

---

## ActiveExecutionsTable

```typescript
// apps/web/components/features/operator/ActiveExecutionsTable.tsx
interface ActiveExecutionsTableProps {
  executions: ActiveExecution[]
  totalCount: number
  isLoading: boolean
  filters: ActiveExecutionsFilters
  onFiltersChange: (filters: Partial<ActiveExecutionsFilters>) => void
  onRowClick: (executionId: string) => void
}
```

**Behavior**: TanStack Table + shadcn DataTable. Columns: execution ID (truncated 8 chars + copy icon), agent FQN, workflow name, current step, `ActiveExecutionStatusBadge`, start time, elapsed duration (live counter). Status filter dropdown (All/Running/Paused/Waiting Approval). Sort by start time or elapsed. Click row → `onRowClick(executionId)`. Live elapsed counter via `useInterval` that increments display without refetching.

---

## ActiveExecutionStatusBadge

```typescript
// apps/web/components/features/operator/ActiveExecutionStatusBadge.tsx
interface ActiveExecutionStatusBadgeProps {
  status: ActiveExecutionStatus
}
```

**Behavior**: shadcn/ui `Badge`. Color mapping: `running` → green, `paused` → yellow, `waiting_for_approval` → blue, `compensating` → orange/warning.

---

## AlertFeed

```typescript
// apps/web/components/features/operator/AlertFeed.tsx
interface AlertFeedProps {
  maxHeight?: string              // default: '400px'
}
```

**Behavior**: Reads from `useAlertFeedStore`. Renders a scrollable list of `AlertFeedItem`. Auto-scrolls to newest (bottom) when `isScrolledToBottom` is true. Detects when user scrolls up → sets `isScrolledToBottom = false` → shows "New alerts ↓" sticky button at bottom. Clicking button or scrolling back to bottom resumes auto-scroll. Severity filter tabs: All/Info/Warning/Error/Critical. Empty state: "No alerts received yet."

---

## AlertFeedItem

```typescript
// apps/web/components/features/operator/AlertFeedItem.tsx
interface AlertFeedItemProps {
  alert: OperatorAlert
}
```

**Behavior**: shadcn/ui Collapsible. Collapsed: severity badge (color-coded), source service label, timestamp (`date-fns formatDistanceToNow`), message summary. Expanded: full description text + suggestedAction if present. Severity badge colors: info → blue, warning → yellow, error → orange, critical → red/destructive.

---

## AttentionFeedPanel

```typescript
// apps/web/components/features/operator/AttentionFeedPanel.tsx
interface AttentionFeedPanelProps {
  className?: string
}
```

**Behavior**: Reads pending attention events from `useAttentionFeedStore`. Renders list of `AttentionFeedItem`, newest first. Unread badge count on panel header. Empty state: "No pending attention requests." Separate from `AlertFeed` — different data source, different visual treatment.

---

## AttentionFeedItem

```typescript
// apps/web/components/features/operator/AttentionFeedItem.tsx
interface AttentionFeedItemProps {
  event: AttentionEvent
  onClick: (event: AttentionEvent) => void
}
```

**Behavior**: Clickable card. Shows urgency badge (low=gray, medium=blue, high=orange, critical=red), source agent FQN, timestamp, context summary. Critical events: red left-border accent + bold border. `onClick` navigates to the linked context URL (derived from targetType + targetId). Urgency badge uses shadcn/ui Badge with appropriate variant class.

---

## QueueBacklogChart

```typescript
// apps/web/components/features/operator/QueueBacklogChart.tsx
interface QueueBacklogChartProps {
  data: QueueTopicLag[]
  isLoading: boolean
  error?: boolean
}
```

**Behavior**: Recharts `BarChart` + `ResponsiveContainer`. One bar per topic, bar height = lag count. Y-axis auto-scale. Warning bars (lag > 10,000) rendered in amber/warning fill color (`fill-amber-500`), normal bars in the primary chart color. X-axis tick: topic name (abbreviated). Tooltip: topic name + lag count + "⚠ High lag" if warning. Empty/error state: "Backlog data unavailable" with retry button. Loading: skeleton bar chart.

---

## ReasoningBudgetGauge

```typescript
// apps/web/components/features/operator/ReasoningBudgetGauge.tsx
interface ReasoningBudgetGaugeProps {
  utilization: ReasoningBudgetUtilization | undefined
  isLoading: boolean
  error?: boolean
}
```

**Behavior**: Uses shared `ScoreGauge` component (feature 015) with `utilizationPct` as the score (0–100). Gauge color: green (<70%), yellow (70–89%), red (≥90%). Center text: `{utilizationPct}%`. Below gauge: "{activeExecutionCount} active executions". When `criticalPressure` is true: red gauge + red label "Capacity pressure". Error state: "Budget data unavailable" placeholder.

---

## ConnectionStatusBanner

```typescript
// apps/web/components/features/operator/ConnectionStatusBanner.tsx
interface ConnectionStatusBannerProps {
  isConnected: boolean
  isPollingFallback: boolean
}
```

**Behavior**: Renders as a shadcn `Alert` (warning variant) at the top of the dashboard when `isConnected === false`. Message: "Live updates paused — reconnecting..." with a spinner. When `isPollingFallback` is true: adds "(polling every 30 seconds)" to the message. Disappears immediately when `isConnected` becomes true. No dismiss button — auto-clears on reconnect.

---

## ExecutionDrilldown

```typescript
// apps/web/components/features/operator/ExecutionDrilldown.tsx
interface ExecutionDrilldownProps {
  executionId: string
}
```

**Behavior**: Loads execution detail + trace + budget + context quality from their respective hooks. Renders execution header (ID, status badge, agent FQN, workflow name, duration). Three panels below via shadcn/ui Tabs: "Reasoning Trace", "Context Quality", "Budget Consumption". Default tab: "Reasoning Trace". Shows loading skeleton while data loads. Breadcrumb back link → `/operator`.

---

## ReasoningTracePanel

```typescript
// apps/web/components/features/operator/ReasoningTracePanel.tsx
interface ReasoningTracePanelProps {
  trace: ReasoningTrace | undefined
  isLoading: boolean
}
```

**Behavior**: Renders `ReasoningTraceStep` components in order. Each step is a shadcn/ui Accordion item. Summary bar at top: total tokens + total duration + total correction iterations. Empty state when `trace.steps.length === 0`.

---

## ReasoningTraceStep

```typescript
// apps/web/components/features/operator/ReasoningTraceStep.tsx
interface ReasoningTraceStepProps {
  step: ReasoningTraceStep
  stepNumber: number
}
```

**Behavior**: shadcn/ui AccordionItem. Collapsed: step number, reasoning mode label, token count, duration, self-correction iteration count badge (if > 0). Expanded: input summary + output summary (each with "Show full output" toggle if truncated). Self-correction chain: each iteration shows original → correction reason → corrected output. Full output expandable from `fullOutputRef` via `CodeBlock` shared component.

---

## ContextQualityPanel

```typescript
// apps/web/components/features/operator/ContextQualityPanel.tsx
interface ContextQualityPanelProps {
  quality: ContextQualityView | undefined
  isLoading: boolean
}
```

**Behavior**: Overall quality score shown as `ScoreGauge`. List of `ContextSource` entries as a table: source type label, quality score (colored by score range), contribution weight (as %). Provenance ref shown as a link when available. Assembly timestamp in metadata footer. Shows fallback (scalar score only) when full provenance data unavailable.

---

## BudgetConsumptionPanel

```typescript
// apps/web/components/features/operator/BudgetConsumptionPanel.tsx
interface BudgetConsumptionPanelProps {
  budget: BudgetStatus | undefined
  isLoading: boolean
}
```

**Behavior**: For each of the 4 budget dimensions: label, shadcn `Progress` bar (0–100%), "X / Y unit" text label, warning icon if `nearLimit`. Progress bar color: normal → blue, 70–89% → yellow, ≥90% → red. Shows "Execution completed — final values" notice when `isActive === false`. Loading: 4 skeleton progress bars.
