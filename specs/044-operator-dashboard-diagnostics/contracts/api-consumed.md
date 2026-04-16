# API Contracts Consumed: Operator Dashboard and Diagnostics

**Phase**: Phase 1 — Design  
**Feature**: [../spec.md](../spec.md)

## Base URLs

- Analytics/Dashboard API: `/api/v1/...`
- Health: `/health`
- Executions: `/api/v1/executions/...`
- Interactions/Attention: `/api/v1/interactions/...`
- WebSocket: `ws://{host}/ws` (existing `lib/ws.ts` WebSocketClient)

---

## TanStack Query Hook Map

| Hook | Method | Endpoint | Used In |
|------|--------|----------|---------|
| `useOperatorMetrics()` | GET | `/api/v1/dashboard/metrics` | US1 metric cards |
| `useServiceHealth()` | GET | `/health` | US1 service health panel |
| `useActiveExecutions(workspaceId, filters)` | GET | `/api/v1/executions?status=running,...` | US2 executions table |
| `useAttentionFeedInit(userId)` | GET | `/api/v1/interactions/attention?status=pending` | US6 initial attention list |
| `useQueueLag()` | GET | `/api/v1/dashboard/queue-lag` | US5 queue bar chart |
| `useReasoningBudgetUtilization()` | GET | `/api/v1/dashboard/reasoning-budget-utilization` | US5 budget gauge |
| `useExecutionDetail(executionId)` | GET | `/api/v1/executions/{executionId}` | US4 drill-down header |
| `useReasoningTrace(executionId)` | GET | `/api/v1/executions/{executionId}/reasoning-trace` | US4 trace panel |
| `useBudgetStatus(executionId)` | GET | `/api/v1/executions/{executionId}/budget-status` | US4 budget bars |
| `useContextQuality(executionId)` | GET | `/api/v1/executions/{executionId}/context-quality` | US4 context panel |

## WebSocket Subscriptions

| Store/Hook | Channel | Source Topic | Used In |
|------------|---------|--------------|---------|
| `useAlertFeedStore` | `alerts` | `monitor.alerts` | US3 alert feed |
| `useAttentionFeedStore` | `attention:{userId}` | `interaction.attention` | US6 attention feed (auto-subscribed) |
| `useActiveExecutions` (invalidation) | `workspace:{workspaceId}` | `workspaces.events` | US2 invalidate query |

---

## Endpoint Specifications

### GET /health

**Purpose**: Aggregated health status for all 12 backend dependencies.

**Polling interval**: 30 seconds.

**Response** (`200 OK`):

```typescript
{
  status: 'healthy' | 'degraded' | 'unhealthy'
  uptime_seconds: number
  profile: string
  dependencies: {
    postgresql: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    redis: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    kafka: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    qdrant: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    neo4j: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    clickhouse: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    opensearch: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    minio: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    runtime_controller: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    reasoning_engine: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    sandbox_manager: { status: 'healthy' | 'unhealthy'; latency_ms: number }
    simulation_controller: { status: 'healthy' | 'unhealthy'; latency_ms: number }
  }
}
```

**Frontend transform**: Maps `dependencies` dict to `ServiceHealthEntry[]` using `SERVICE_DISPLAY_NAMES`. Missing service keys default to `status: 'unknown'`.

---

### GET /api/v1/dashboard/metrics

**Purpose**: Real-time operational metrics snapshot for metric cards.

**Polling interval**: 15 seconds.

**Notes**: Assumed endpoint. Falls back to showing "—" in metric cards with a stale data badge if unavailable.

**Response** (`200 OK`):

```typescript
{
  activeExecutions: number
  queuedSteps: number
  pendingApprovals: number
  recentFailures: number        // failures in last 1 hour
  avgLatencyMs: number          // p50 across active executions
  fleetHealthScore: number      // 0–100 composite
  computedAt: string            // ISO 8601
}
```

---

### GET /api/v1/executions

**Purpose**: List active executions for the real-time table.

**Polling interval**: 5 seconds (low latency for near-real-time table updates). Plus WebSocket invalidation on workspace events.

**Query Parameters**:

| Parameter | Value |
|-----------|-------|
| `workspace_id` | current workspace UUID (required) |
| `status` | `running,paused,waiting_for_approval,compensating` |
| `page_size` | `100` |
| `sort_by` | `started_at` (newest first) or `elapsed` |

**Response** (`200 OK`):

```typescript
{
  items: {
    id: string                  // UUID
    workflow_definition_id: string
    status: string              // 'running' | 'paused' | 'waiting_for_approval' | 'compensating'
    workspace_id: string
    started_at: string | null
    created_at: string
    updated_at: string
    // Note: workflow name and agent FQN require workflow definition lookup
    // or are included in an enriched operator endpoint
  }[]
  total: number
  page: number
  page_size: number
}
```

**Note**: The existing executions endpoint does not include `agentFqn` or `workflowName` directly on the response. These may require enrichment via the `dashboard/metrics` endpoint or a separate operator executions endpoint. Document this as an assumption.

---

### GET /api/v1/interactions/attention

**Purpose**: Initial load of pending attention requests for the attention feed.

**Query Parameters**:

| Parameter | Value |
|-----------|-------|
| `status` | `pending` |
| `page_size` | `50` |

**Response** (`200 OK`):

```typescript
{
  items: {
    id: string                  // UUID
    workspace_id: string
    source_agent_fqn: string
    target_identity: string
    urgency: 'low' | 'medium' | 'high' | 'critical'
    context_summary: string
    related_execution_id: string | null
    related_interaction_id: string | null
    related_goal_id: string | null
    status: 'pending' | 'acknowledged' | 'resolved' | 'dismissed'
    acknowledged_at: string | null
    resolved_at: string | null
    created_at: string
  }[]
  total: number
  page: number
  page_size: number
}
```

---

### GET /api/v1/dashboard/queue-lag

**Purpose**: Kafka consumer lag per topic for the queue backlog chart.

**Polling interval**: 15 seconds.

**Notes**: Assumed endpoint. Shows "Backlog data unavailable" on 404/500 with retry button.

**Response** (`200 OK`):

```typescript
{
  topics: {
    topic: string
    lag: number
    warning: boolean
  }[]
  computedAt: string
}
```

---

### GET /api/v1/dashboard/reasoning-budget-utilization

**Purpose**: Aggregate reasoning budget utilization gauge.

**Polling interval**: 10 seconds.

**Notes**: Assumed endpoint. Shows "Budget data unavailable" on error.

**Response** (`200 OK`):

```typescript
{
  totalCapacityTokens: number
  usedTokens: number
  utilizationPct: number        // 0–100
  activeExecutionCount: number
  criticalPressure: boolean
  computedAt: string
}
```

---

### GET /api/v1/executions/{executionId}

**Purpose**: Execution header for the drill-down page.

**Response** (`200 OK`): Standard `ExecutionResponse` (existing type from `apps/web/types/execution.ts`).

---

### GET /api/v1/executions/{executionId}/reasoning-trace

**Purpose**: Structured reasoning trace for execution drill-down.

**Notes**: Assumed endpoint. Fallback: parse journal events of type `REASONING_TRACE_EMITTED` and `SELF_CORRECTION_*`.

**Response** (`200 OK`):

```typescript
{
  executionId: string
  steps: {
    stepIndex: number
    stepId: string
    mode: ReasoningMode
    inputSummary: string        // max 500 chars
    outputSummary: string       // max 500 chars
    tokenCount: number
    durationMs: number
    selfCorrectionIterations: {
      iterationIndex: number
      originalOutputSummary: string
      correctionReason: string
      correctedOutputSummary: string
      tokenDelta: number
    }[]
    fullOutputRef: string | null
  }[]
  totalTokens: number
  totalDurationMs: number
}
```

---

### GET /api/v1/executions/{executionId}/budget-status

**Purpose**: Resource budget consumption vs. limits for the drill-down.

**Notes**: Assumed endpoint.

**Response** (`200 OK`):

```typescript
{
  executionId: string
  isActive: boolean
  computedAt: string
  dimensions: {
    dimension: 'tokens' | 'tool_invocations' | 'memory_writes' | 'elapsed_time'
    label: string
    used: number
    limit: number
    unit: string
    utilizationPct: number
    nearLimit: boolean          // utilizationPct > 90
  }[]
}
```

---

### GET /api/v1/executions/{executionId}/context-quality

**Purpose**: Context quality provenance for the drill-down.

**Notes**: Assumed endpoint. Fallback: show `contextQualityScore` from `StepDetail` as a single scalar.

**Response** (`200 OK`):

```typescript
{
  executionId: string
  assemblyRecordId: string
  overallQualityScore: number
  assembledAt: string
  sources: {
    sourceType: ContextSourceType
    displayLabel: string
    qualityScore: number        // 0–100
    contributionWeight: number  // 0–1
    provenanceRef: string | null
  }[]
}
```

---

## WebSocket Event Formats

### alerts channel

**Channel**: `alerts`  
**Subscribe**: `{ type: "subscribe", channel: "alerts", resource_id: userId }`

**Incoming event payload**:
```typescript
{
  id?: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  source_service: string
  timestamp: string
  message: string
  description?: string
  suggested_action?: string
}
```

**Handling in `useAlertFeedStore`**: Prepend to `alerts` ring buffer; if length > 200 drop the last entry.

---

### attention channel (auto-subscribed)

**Channel**: `attention:{userId}` (auto-subscribed by the WebSocket hub)  
**No manual subscribe needed.**

**Incoming event payload**:
```typescript
// Same shape as AttentionRequestResponse from REST endpoint
{
  id: string
  workspace_id: string
  source_agent_fqn: string
  urgency: 'low' | 'medium' | 'high' | 'critical'
  context_summary: string
  related_execution_id: string | null
  related_interaction_id: string | null
  related_goal_id: string | null
  status: 'pending' | 'acknowledged' | 'resolved' | 'dismissed'
  created_at: string
}
```

**Handling in `useAttentionFeedStore`**: Call `addEvent()` to prepend; deduplicate by `id`.

---

### workspace channel (for query invalidation)

**Channel**: `workspace:{workspaceId}`  
**Subscribe**: `{ type: "subscribe", channel: "workspace", resource_id: workspaceId }`

**Purpose**: When any workspace-level execution event arrives (new execution, execution completed), invalidate the `['activeExecutions', workspaceId]` TanStack Query cache key to trigger a fresh fetch.

---

## Query Key Conventions

```typescript
['operatorMetrics']                           // refetchInterval: 15_000
['serviceHealth']                             // refetchInterval: 30_000
['activeExecutions', workspaceId, filters]    // refetchInterval: 5_000
['attentionFeedInit', userId]                 // staleTime: Infinity (WS handles updates)
['queueLag']                                  // refetchInterval: 15_000
['reasoningBudget']                           // refetchInterval: 10_000
['executionDetail', executionId]              // staleTime: 30_000
['reasoningTrace', executionId]               // staleTime: 60_000 (completed execs don't change)
['budgetStatus', executionId]                 // refetchInterval: 5_000 (active exec) | staleTime: Infinity (completed)
['contextQuality', executionId]               // staleTime: 60_000
```

---

## Error Handling

| Status | Endpoint | Behavior |
|--------|----------|----------|
| `404` | `/dashboard/metrics` | Metric cards show "—" with amber badge "Unavailable" |
| `404` | `/dashboard/queue-lag` | BarChart shows "Backlog data unavailable" empty state + retry |
| `404` | `/dashboard/reasoning-budget-utilization` | Gauge shows "Budget data unavailable" |
| `404` | `/executions/{id}/reasoning-trace` | Trace panel falls back to journal event parsing |
| `404` | `/executions/{id}/budget-status` | Budget panel shows "Budget data unavailable" |
| `404` | `/executions/{id}/context-quality` | Context panel shows scalar `contextQualityScore` only |
| `503` | `/health` | Service health panel shows all indicators as gray "unknown" |
| WS disconnect | Any WS channel | `ConnectionStatusBanner` shown; polling fallback activates |
