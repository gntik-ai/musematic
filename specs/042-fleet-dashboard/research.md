# Research: Fleet Dashboard

**Feature**: 042-fleet-dashboard  
**Phase**: 0 (Research)  
**Date**: 2026-04-16

---

## Decision 1: Route Structure

**Decision**: Use Next.js 14+ App Router route groups under `app/(main)/fleet/` with dynamic `[fleetId]/` segment for fleet detail. Sub-tabs on the detail page via URL query param `?tab=topology|members|performance|controls|observers` (same pattern as features 027 and 041).

```
app/(main)/fleet/
├── page.tsx                    # Fleet list (US1)
└── [fleetId]/
    └── page.tsx                # Fleet detail (US2–US6, tabbed)
```

**Rationale**: Fleet detail has multiple dense sections (topology graph, member panel, performance charts, controls, observer findings) that share the same fleet context. Tabs on a single page allow seamless switching without losing the topology graph's viewport state. Upload/wizard routes (like feature 041) are unnecessary — all fleet operations happen from the detail page.

**Alternatives considered**:
- Separate routes per section (`[fleetId]/topology/`, `[fleetId]/performance/`) — rejected; would remount the topology graph on every navigation, losing zoom/pan state.
- Single scrollable page without tabs — rejected; too much content for a single scroll, especially with the topology graph needing a fixed viewport.

---

## Decision 2: Topology Graph Layout

**Decision**: Use `@xyflow/react` (already in stack, v12+) with `dagre` layout engine for computing node positions. One new dependency required: `dagre` (~15KB). Layout mapping:

| Backend topology_type | Layout algorithm | dagre config |
|----------------------|-----------------|--------------|
| `hierarchical` | Top-to-bottom tree | `rankDir: 'TB'`, `ranker: 'network-simplex'` |
| `peer_to_peer` | Left-to-right force | `rankDir: 'LR'`, `ranksep: 100` |
| `hybrid` | Top-to-bottom with clustering | `rankDir: 'TB'`, `compound: true` |

Custom `FleetMemberNode` component renders: agent name, role badge, health color border (green/yellow/red). Custom `CommunicationEdge` renders animated dashes for active communication.

**Rationale**: dagre is the standard layout companion for @xyflow/react — it's listed in the official @xyflow/react documentation as the recommended layout engine. At ~15KB, it adds negligible bundle weight. Manual positioning would require re-implementing graph layout algorithms from scratch, which is impractical.

**Alternatives considered**:
- elkjs (~300KB) — rejected; 20x heavier than dagre, and dagre covers all three topology types adequately.
- Manual circular/grid positioning — rejected; works for simple topologies but breaks for mixed hierarchical+mesh hybrids.
- d3-force — rejected; only handles force-directed layouts, not hierarchical trees.

---

## Decision 3: Real-Time Updates

**Decision**: Use the existing WebSocket infrastructure (feature 019) with the `fleet` channel type for real-time fleet health, member status, and performance updates. Subscribe to `fleet:{fleet_id}` topic on detail page mount. Use the existing `ConnectionStatusBanner` component (from feature 026) for connection loss indication with 30-second polling fallback.

**Rationale**: The WebSocket hub (feature 019) already defines a `fleet` channel type in its 11 supported channels. The `fleet.health` Kafka topic (from the topics registry) feeds fleet health events through the WebSocket hub. No new infrastructure needed.

**Alternatives considered**:
- Polling-only approach — rejected; 30-second polling creates unacceptable lag for real-time fleet monitoring (SC-004 requires < 5 second lag).
- Server-Sent Events — rejected; the platform standardized on WebSocket (feature 019), and SSE would be a divergent pattern.

---

## Decision 4: Performance Charts Time-Series Data

**Decision**: Use `Recharts` (already in stack) with `FleetPerformanceProfile` history as the time-series data source. The backend endpoint `GET /fleets/{fleet_id}/performance-profile/history` returns a list of profiles over time — each profile's `period_start` becomes the x-axis timestamp, and `success_rate`, `avg_completion_time_ms`, `cost_per_task` become y-axis values for the three charts.

Time range selector (1h, 6h, 24h, 7d, 30d) maps to query parameters on the history endpoint.

**Rationale**: Recharts is the established charting library in the stack. The performance profile history endpoint already provides the data in the right granularity — no additional aggregation needed on the frontend. Three separate `LineChart` components (success rate, latency, cost) share a synchronized tooltip via Recharts' `syncId` prop.

**Alternatives considered**:
- Single combined chart with multiple y-axes — rejected; three different units (percentage, milliseconds, currency) on one chart creates confusing y-axis scaling.
- ClickHouse direct query from frontend — rejected; frontend never queries analytics stores directly (Constitution IV).

---

## Decision 5: Topology Graph Clustering for 50+ Nodes

**Decision**: When node count exceeds 50, apply automatic grouping using @xyflow/react's parent-child node feature. Nodes are grouped by their role (executor, lead, observer, worker) into expandable group nodes. Each group shows a summary (member count, aggregate health) and expands on click to reveal individual nodes within.

**Rationale**: @xyflow/react's native parent-child relationship supports collapsible groups without additional libraries. Grouping by role is the most semantically meaningful clustering for fleet operators — they care about "how many executors are healthy" more than spatial proximity.

**Alternatives considered**:
- Viewport-based clustering (cluster nodes that overlap visually) — rejected; grouping by spatial position is arbitrary and doesn't convey semantic meaning.
- Paginated graph (show first 50, "load more") — rejected; breaks the topology visualization's purpose of showing the complete fleet structure.

---

## Decision 6: Observer Findings

**Decision**: Observer findings are consumed from `GET /fleets/{fleet_id}/observer-findings` which aggregates attention requests (from feature 024's `attention_requests` table) filtered by observer agents assigned to the fleet. Each finding has: severity (info/warning/critical), timestamp, observer FQN, description, suggested actions, acknowledgment status.

**Rationale**: Observer agents report findings through the standard Attention pattern (Constitution XIII). The backend aggregates these per fleet, filtering by the observer agents in `observer_assignments`. The frontend only needs to display and acknowledge — no computation.

**Alternatives considered**:
- Consume raw attention requests and filter on the frontend — rejected; filtering should happen server-side to avoid transmitting unrelated attention data.
- Separate observer reporting system — rejected; the Attention pattern is the established mechanism for agent-initiated signals.

---

## Decision 7: Fleet Control Actions

**Decision**: Fleet controls map to dedicated backend action endpoints:

| Control | Endpoint | Notes |
|---------|----------|-------|
| Pause | `POST /fleets/{fleet_id}/pause` | Graceful halt; transitions status pausing → paused |
| Resume | `POST /fleets/{fleet_id}/resume` | Transitions paused → active |
| Scale | `POST /fleets/{fleet_id}/members` + `DELETE` | Add/remove members via existing API |
| Stress test | `POST /simulation/runs` (feature 040) | With `fleet_id` context parameter |

**Rationale**: Pause/resume are status transitions with side effects (halting active executions), so they need dedicated action endpoints rather than a generic PUT. Scaling uses the existing member CRUD API. Stress testing delegates to the simulation infrastructure (features 012, 040) which already handles simulated load.

**Alternatives considered**:
- PUT /fleets/{fleet_id} with status field — rejected; status transitions have side effects that warrant explicit action semantics.
- Custom scaling endpoint — rejected; scaling IS add/remove members, and the existing API already supports this.

---

## Decision 8: New npm Dependencies

**Decision**: One new npm package required: `dagre` (~15KB, graph layout algorithm for @xyflow/react topology visualization). All other dependencies are already in the frontend stack.

Existing stack items used by this feature:
- `shadcn/ui` — DataTable, Tabs, Dialog, Badge, Tooltip, Progress, Alert, AlertDialog, Accordion, Select
- `@xyflow/react 12+` — topology graph (ReactFlow, Background, Controls, MiniMap)
- `Recharts 2.x` — performance charts (LineChart, Area, Tooltip, ResponsiveContainer)
- `TanStack Query v5` — all server state
- `Zustand 5.x` — topology viewport state (optional)
- `date-fns 4.x` — timestamp formatting
- `Lucide React` — icons
- `Tailwind CSS 3.4+` — all styling

**Rationale**: dagre is justified because @xyflow/react provides the rendering layer but not the layout computation — dagre is the officially recommended layout engine in @xyflow/react documentation. It's the minimal addition needed to make the topology graph functional.
