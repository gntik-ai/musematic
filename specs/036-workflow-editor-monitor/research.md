# Research: Workflow Editor and Execution Monitor

**Phase 0 — Research Output**  
**Date**: 2026-04-13  
**Feature**: 036-workflow-editor-monitor

---

## Monaco Editor — YAML + JSON Schema in Next.js App Router

**Decision**: Use `@monaco-editor/react` with `monaco-yaml` for YAML language service.

**Rationale**: `@monaco-editor/react` is the canonical React wrapper for Monaco Editor (0.50+, already in constitution). `monaco-yaml` provides a YAML language service that integrates with Monaco's built-in JSON Schema validation pipeline. This combination enables:
- YAML syntax highlighting and bracket matching
- JSON Schema-driven inline diagnostics (error squiggles)
- Auto-complete from the schema's property definitions

**Alternatives considered**:
- `@uiw/react-codemirror` with `@codemirror/lang-yaml` — lighter but not Monaco-compatible; rejected because constitution locks Monaco 0.50+.
- Plain Monaco with custom YAML parsing — more code, same result; rejected for maintainability.

**Configuration approach**: The workflow JSON Schema is fetched once from `/api/v1/workflows/schema` and registered with `monaco-yaml`'s `setDiagnosticsOptions`. Schema is cached in TanStack Query with a long stale time (1 hour) since it changes only on backend deployments.

**SSR handling**: Monaco is dynamically imported (`next/dynamic` with `ssr: false`) to avoid SSR incompatibilities. The editor renders inside a `ResizablePanelGroup` (shadcn) split between the YAML pane and the graph preview pane.

---

## @xyflow/react — DAG Layout Algorithm

**Decision**: Use `dagre` layout algorithm via `@dagrejs/dagre` for automatic DAG positioning.

**Rationale**: `@xyflow/react 12+` (in constitution) does not auto-layout nodes by default — nodes require explicit `position: {x, y}`. `dagre` computes hierarchical top-to-bottom layouts appropriate for workflow DAGs. It handles:
- Topological sort of steps by dependencies
- Horizontal centering per layer
- Edge routing for dependency arrows

**Alternatives considered**:
- `elkjs` (ELK layout engine) — more powerful but heavier bundle; overkill for 100-step workflows. Rejected.
- Manual fixed positioning — brittle for dynamic YAML-derived graphs. Rejected.

**Performance**: For ≤100 nodes, `dagre` layout completes in <10ms in browser. Acceptable for debounced (500ms) YAML-on-change updates.

**Minimap + controls**: `@xyflow/react` includes `<MiniMap>`, `<Controls>`, and `<Background>` components. These cover the zoom/pan/minimap acceptance criteria with no custom code.

---

## Execution WebSocket Channel

**Decision**: Use existing `wsClient.subscribe()` with channel `execution:${executionId}`.

**Rationale**: The WebSocket gateway (feature 019) supports dynamic channel subscriptions. The execution monitor subscribes to the `execution` channel type (documented in 019 spec as one of 11 channel types). The existing `lib/ws.ts` `subscribe<T>(channel, handler)` pattern exactly matches what's needed.

**Event handling pattern**:
```
wsClient.subscribe<ExecutionWsEvent>(`execution:${executionId}`, (event) => {
  switch (event.event_type) {
    case 'step.state_changed': // update step node color in Zustand store
    case 'event.appended':     // add event to timeline (React Query cache)
    case 'budget.threshold':   // update cost tracker
    case 'correction.iteration': // update self-correction chart
  }
})
```

**Reconnect + replay**: The existing `wsClient` auto-reconnects with exponential backoff. On reconnect, the monitor re-fetches execution state via `GET /executions/{id}/state` and journal events via `GET /executions/{id}/journal?since_sequence={lastSeen}` to reconcile any missed events.

**Alternatives considered**: Polling `GET /executions/{id}/state` every 2s — heavier than WebSocket; acceptable fallback only. Use as fallback when WebSocket is unavailable (existing `ConnectionStatusBanner` pattern from 026).

---

## Missing Control Endpoints — Assumed Contracts

The research revealed `/cancel`, `/resume`, and `/rerun` endpoints. The following four are not explicitly documented in the 029 contracts but are required by the spec:

| Action | Assumed Endpoint | Notes |
|--------|-----------------|-------|
| Pause execution | `POST /executions/{id}/pause` | Stops new step dispatch; active steps complete |
| Retry failed step | `POST /executions/{id}/steps/{step_id}/retry` | Re-executes step with original inputs |
| Skip step | `POST /executions/{id}/steps/{step_id}/skip` | Marks step skipped, passes empty output downstream |
| Inject variable | `POST /executions/{id}/hot-change` body: `{variable_name, value}` | Maps to 029's "hot change" mechanism |

**Rationale**: The 029 spec explicitly mentions "hot change", "retry", "skip", and "pause" as execution control operations in its functional description. The contract files don't list their exact paths — these patterns are inferred from the existing endpoint naming convention.

**Risk**: If actual endpoints differ, the API hook layer abstracts this — only `lib/hooks/use-execution-controls.ts` needs updating, not the UI components.

---

## Reasoning Trace — Data Delivery

**Decision**: Reasoning trace is retrieved via the execution journal (as `REASONING_TRACE_EMITTED` events), not a separate endpoint.

**Rationale**: The execution journal's `REASONING_TRACE_EMITTED` event payload contains branch tree data. For completed steps, the full trace is assembled by filtering journal events by `step_id` and `event_type=REASONING_TRACE_EMITTED`. For active steps, new branches stream in via WebSocket.

**Lazy loading**: When a step has >50 reasoning branches (paginated threshold), the UI shows the first page and a "Load more branches" trigger. The journal endpoint supports `?event_type=REASONING_TRACE_EMITTED&step_id={id}&limit=20&offset=N` for pagination.

**Self-correction data**: `SELF_CORRECTION_STARTED` and individual iteration results are embedded in the same journal stream. The convergence chart is built by collecting all `self_correction.iteration` events for a given step, sorted by iteration number.

---

## Cost Data — Delivery Mechanism

**Decision**: Real-time token/cost data arrives via WebSocket execution channel events; historical per-step breakdown via `GET /analytics/usage` filtered by `execution_id`.

**Rationale**: The reasoning engine's `BudgetEvent` stream (via `runtime.reasoning` Kafka topic → WS gateway) provides real-time token threshold events. These are forwarded on the `execution` WS channel. For total cost accumulation, the frontend accumulates events locally in the Zustand store.

**Per-step breakdown**: Fetched lazily when the operator expands the cost panel, via the analytics endpoint with appropriate filters.

---

## Step Detail — Inputs/Outputs Delivery

**Decision**: Step inputs and outputs are retrieved from `GET /executions/{id}/steps/{step_id}` (assumed endpoint, analogous to state endpoint structure in 029).

**Rationale**: The execution state endpoint returns high-level step status lists. Step-level inputs/outputs, timing, errors, and context quality score require a dedicated detail endpoint. This matches the TaskPlanRecord pattern (per-step sub-resource).

---

## Task Plan Viewer — Full Payload Loading

**Decision**: Task plan records are loaded lazily when the operator clicks a step node and opens the "Task Plan" tab.

**Rationale**: The `TaskPlanFullResponse` payload can be large (candidates with scores, parameter provenance map). Loading it eagerly for all steps wastes bandwidth. Lazy loading on tab open is consistent with how the reasoning trace viewer works.

**Empty state**: If no task plan exists for a step (e.g., trigger steps, approval gate steps), the tab shows an empty state: "No task plan available — this step was not dispatched to an agent."
