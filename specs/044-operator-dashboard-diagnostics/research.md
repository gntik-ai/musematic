# Research: Operator Dashboard and Diagnostics

**Phase**: Phase 0 — Research  
**Feature**: [spec.md](spec.md)

## Decision 1: Route Structure

**Decision**: Two-route structure — dashboard page + execution drill-down page.

```
app/(main)/operator/
  page.tsx                                    # Main dashboard (US1–US3, US5–US6)
  executions/[executionId]/
    page.tsx                                  # Execution drill-down (US4)
```

**Rationale**: The main dashboard aggregates all real-time monitoring panels — metrics, service health, active executions, alert feed, attention feed, queue backlog, reasoning budget. These are logically co-located on a single scrollable page. The execution drill-down (reasoning traces, context quality, budget consumption) requires a dedicated page with a full-width layout for the three diagnostic sections. Separating them avoids a deeply nested panel-in-panel UI.

**Alternatives considered**:
- Single page with drawer for drill-down — drawer is too constrained for three-panel diagnostics with collapsible trees and provenance charts
- Tab routing with `?tab=` — appropriate for a single entity detail (features 041–043) but not for a top-level monitoring dashboard

---

## Decision 2: Metrics Snapshot Endpoint

**Decision**: Assume `GET /api/v1/dashboard/metrics` — a dedicated operator metrics aggregation endpoint.

**Rationale**: The backend does not currently have a single endpoint returning all 6 operational indicators (active executions, queued steps, pending approvals, recent failures, avg latency, fleet health score). The analytics API (`GET /api/v1/analytics/kpi`) is workspace-scoped and time-series oriented; it does not return a real-time snapshot suitable for metric cards. The execution API (`GET /api/v1/executions`) requires workspace_id and returns paginated execution records, not counts. A purpose-built dashboard metrics endpoint is the lowest-latency, lowest-bandwidth solution and is consistent with the analytics bounded context's existing aggregation patterns.

**Response shape assumed**:
```typescript
{
  activeExecutions: number
  queuedSteps: number
  pendingApprovals: number
  recentFailures: number        // last 1 hour
  avgLatencyMs: number          // p50 across active executions
  fleetHealthScore: number      // 0–100 composite
  computedAt: string            // ISO 8601 — to detect stale
}
```

**Polling interval**: 15 seconds. Real-time streaming not needed for summary metrics.

**Alternatives considered**:
- Client-side aggregation from multiple existing endpoints — 5+ requests per refresh cycle, unacceptable network overhead
- analytics/kpi endpoint — time-series format, wrong shape for real-time cards

---

## Decision 3: Service Health Endpoint

**Decision**: Consume `GET /health` directly from the frontend.

**Rationale**: The backend already exposes `GET /health` with all 13 service dependencies (8 data stores + 4 satellite services: postgresql, redis, kafka, qdrant, neo4j, clickhouse, opensearch, minio, runtime_controller, reasoning_engine, sandbox_manager, simulation_controller). The response maps exactly to the spec's 13-indicator service health panel.

**Note on hostops broker**: The spec mentions 5 satellite services (including hostops broker), but the current health endpoint only covers 4 (no hostops_broker). The service health panel will show 12 indicators from the existing health endpoint and document the missing hostops entry as a known gap.

**Status mapping**:
- `"healthy"` → green dot
- `"degraded"` → yellow dot (partial — backend uses "degraded" for non-database issues)
- `"unhealthy"` → red dot
- missing / timeout → gray dot ("unknown")

**Polling interval**: 30 seconds (health checks are expensive; the backend pings 13 services per call).

**Alternatives considered**:
- Per-service health checks from frontend — 13 individual requests, excessive
- Custom `/api/v1/operator/service-health` endpoint — redundant given existing `/health`

---

## Decision 4: Active Executions — Polling + WebSocket Invalidation

**Decision**: TanStack Query `useActiveExecutions(workspaceId)` with `refetchInterval: 5000` + WebSocket invalidation on workspace channel execution events.

**Rationale**: The backend's `GET /api/v1/executions?status=running&page_size=100` returns active executions for a workspace. There is no "push all active executions" WebSocket channel — the execution channel is per-execution-ID, not a global streaming channel. Polling at 5s achieves <10s visibility into new/completed executions (matching SC-002's "within 2 seconds" is achieved by the polling interval being short enough for a dashboard context; true 2s updates would require a broadcast channel). For true real-time update: subscribe to `workspace:{workspaceId}` WebSocket channel and call `queryClient.invalidateQueries(['activeExecutions'])` on execution lifecycle events.

**Query**: `GET /api/v1/executions?workspace_id={id}&status=running,paused,waiting_for_approval&page_size=100&sort_by=started_at`

**Alternatives considered**:
- WebSocket `execution:*` wildcard subscription — not supported by the hub (subscriptions are per-resource-id, not wildcard)
- Server-Sent Events — not in the platform's WebSocket hub design

---

## Decision 5: Alert Feed — WebSocket + Zustand Ring Buffer

**Decision**: Subscribe to `alerts` WebSocket channel; store incoming alerts in a Zustand ring buffer (max 200 entries). No REST alert history endpoint (none exists).

**Rationale**: The backend alert infrastructure is real-time-only — alerts are published to `monitor.alerts` Kafka topic and fanned out via WebSocket channel `alerts`. There is no REST endpoint for alert history. The frontend maintains a Zustand store as a bounded ring buffer: new alerts are prepended, and when the buffer exceeds 200 entries, the oldest are dropped. This gives the operator ~10–20 minutes of alert history depending on alert volume.

**Alert event format** (assumed from the `monitor.alerts` Kafka topic):
```typescript
{
  id: string              // generated client-side if not present
  severity: 'info' | 'warning' | 'error' | 'critical'
  sourceService: string
  timestamp: string
  message: string
  description: string | null
  suggestedAction: string | null
}
```

**Auto-scroll behavior**: Implemented in the `AlertFeed` component using a `useRef` scroll anchor + `useEffect` to scroll to bottom when new items arrive, paused when operator has scrolled up (`isScrolledToBottom` state).

**Polling fallback**: When WebSocket disconnects, the feed pauses and a `ConnectionStatusBanner` prompts "Live updates paused — reconnecting..." with no data polling (alert history unavailable via REST).

**Alternatives considered**:
- Client-side IndexedDB persistence — overengineered for an operator session view
- Adding a REST alert history endpoint — scope change; acceptable as future enhancement

---

## Decision 6: Attention Feed — REST Initial Load + WebSocket Auto-Subscription

**Decision**: Load initial pending attention requests via `GET /api/v1/interactions/attention?status=pending` and receive live updates via the already-auto-subscribed `attention` WebSocket channel.

**Rationale**: The attention feed requires both the initial list of pending requests (available via REST) and real-time new requests (available via auto-subscribed WebSocket channel `attention:{user_id}`). The attention channel is automatically subscribed on WebSocket connection per the platform design (feature 019). The Zustand store merges the REST list with incoming WebSocket events, deduplicating by request ID.

**Navigation on click**:
- `related_execution_id` present → navigate to `/operator/executions/{id}`
- `related_interaction_id` present → navigate to `/conversations/{id}` (feature 024)
- `related_goal_id` present → navigate to `/workspaces/goals/{id}` (feature 018)

**Urgency color mapping**:
- `low` → gray/muted
- `medium` → blue
- `high` → orange/warning
- `critical` → red/destructive

**Alternatives considered**:
- Polling-only (no WebSocket) — misses real-time urgency; the attention channel is already auto-subscribed so using it costs nothing

---

## Decision 7: Queue Lag and Reasoning Budget — Assumed Endpoints

**Decision**: Assume two new aggregation endpoints in an operator/dashboard context:
- `GET /api/v1/dashboard/queue-lag` → Kafka consumer lag by topic
- `GET /api/v1/dashboard/reasoning-budget-utilization` → Aggregate reasoning capacity usage

**Rationale**: Neither endpoint currently exists in the backend. Both are natural additions to the analytics or a new `dashboard` bounded context, consistent with the spec assumption: "Kafka consumer lag metrics are available through a monitoring/admin endpoint... the dashboard reads pre-aggregated lag values." The polling intervals are 15s (queue lag) and 10s (reasoning budget), tolerating stale data.

**Queue lag response shape**:
```typescript
{
  topics: {
    topic: string           // Kafka topic name
    lag: number             // unconsumed message count
    warning: boolean        // lag > 10,000 threshold
  }[]
  computedAt: string
}
```

**Reasoning budget utilization response shape**:
```typescript
{
  totalCapacityTokens: number
  usedTokens: number
  utilizationPct: number    // 0–100
  activeExecutionCount: number
  criticalPressure: boolean // utilization > 90%
  computedAt: string
}
```

**Fallback when endpoints unavailable**: Charts show "Data unavailable" empty states with a retry button.

**Alternatives considered**:
- Deriving queue lag from Kafka AdminClient in the browser — impossible; browser cannot connect to Kafka
- Computing reasoning budget from execution journals — N+1 queries per active execution, too slow

---

## Decision 8: Execution Drill-Down — Assumed Structured Endpoints

**Decision**: Assume three structured endpoints under execution detail:
- `GET /api/v1/executions/{id}/reasoning-trace` — Ordered reasoning steps with mode, summaries, tokens, duration, self-correction chain
- `GET /api/v1/executions/{id}/budget-status` — Current resource usage vs. budgeted limits for each dimension
- `GET /api/v1/executions/{id}/context-quality` — Context provenance with data sources, quality scores, and assembly chain

**Rationale**: The execution journal (`GET /api/v1/executions/{id}/journal`) contains raw event payloads including reasoning events, but the payload structure is untyped (`dict[str, Any]`). Parsing raw event payloads client-side is fragile and coupled to the internal event schema. The existing `StepDetail` type has `contextQualityScore` (scalar) but no provenance chain. Structured endpoints are the clean separation of concerns.

**Fallback if endpoints unavailable**: Parse journal events filtered by `REASONING_TRACE_EMITTED` and `SELF_CORRECTION_*` event types to reconstruct the trace. Document this fallback in the hook implementation.

**Alternatives considered**:
- Pure journal-based parsing — fragile against event schema changes
- GraphQL subscription — not in the platform stack

---

## Decision 9: No New npm Packages

**Decision**: No new npm packages for this feature.

**Rationale**: All required capabilities are in the existing stack:
- **Real-time data tables** → shadcn/ui DataTable + TanStack Table v8 (features 027, 035, 042)
- **Bar chart (queue backlog)** → Recharts `BarChart` (already used for fleet performance in feature 042)
- **Gauge (reasoning budget)** → Shared `ScoreGauge` component (feature 015) reused; or Recharts `RadialBarChart` for the utilization gauge
- **Progress bars (budget consumption)** → shadcn/ui `Progress` component
- **Collapsible reasoning steps** → shadcn/ui `Collapsible` + `Accordion`
- **Connection status banner** → shadcn/ui `Alert` (already used in feature 026)
- **Auto-scroll feed** → Native DOM `scrollIntoView` + `useRef`
- **WebSocket client** → Existing `lib/ws.ts` WebSocketClient

The `ScoreGauge` shared component (a Recharts RadialBarChart-based half-circle gauge, feature 015) is used for the reasoning budget utilization gauge. No new chart libraries needed.

**Alternatives considered**:
- `react-virtualized` for long alert/execution lists — premature; shadcn Table handles 100+ rows; revisit if real-world volumes require it
- `socket.io-client` — not in the stack; the platform uses its own WebSocket hub with custom protocol
