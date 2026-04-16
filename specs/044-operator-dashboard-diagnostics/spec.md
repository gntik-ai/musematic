# Feature Specification: Operator Dashboard and Diagnostics

**Feature Branch**: `044-operator-dashboard-diagnostics`  
**Created**: 2026-04-16  
**Status**: Draft  
**Input**: User description for operator overview dashboard with service health, queue backlogs, reasoning budget utilization, active executions, alert feed, execution drill-down, and attention feed.  
**Requirements Traceability**: FEAT-FE-009

## User Scenarios & Testing

### User Story 1 - View Operator Overview (Priority: P1)

A platform operator opens the operator dashboard to get an at-a-glance picture of platform health. They see a grid of metric cards showing key operational indicators: active executions, queued steps, pending approvals, recent failures, average latency, and fleet health score. Below the metric cards, they see service health indicators — a compact status panel showing the availability state of each platform data store (relational database, vector search, graph database, analytics store, cache, full-text search, event backbone, object storage) and each satellite service (runtime controller, reasoning engine, sandbox manager, simulation controller, host operations broker). Each indicator shows a color-coded status dot: green (healthy), yellow (degraded), red (down), gray (unknown/unreachable).

**Why this priority**: The overview is the operator's entry point and primary situational-awareness tool. Without it, operators have no single pane of glass for platform health and must check multiple systems independently.

**Independent Test**: Open the operator dashboard. Confirm 6 metric cards render with current values. Confirm service health panel shows status indicators for all 8 data stores and 5 satellite services. Confirm color-coded status dots reflect actual service availability. Confirm all values update when the page is refreshed.

**Acceptance Scenarios**:

1. **Given** the platform is running with 12 active executions, **When** the operator opens the dashboard, **Then** 6 metric cards render showing: active executions (12), queued steps, pending approvals, recent failures (last 1 hour), average latency (p50), and fleet health score.
2. **Given** all services are healthy, **When** the operator views the service health panel, **Then** 13 status indicators show green dots (8 data stores + 5 satellite services), each labeled with the service name.
3. **Given** the cache service is degraded, **When** the operator views the service health panel, **Then** the cache indicator shows a yellow dot with a "degraded" label.
4. **Given** metric values change, **When** the operator refreshes or the polling interval fires, **Then** the metric cards update with current values within 5 seconds.

---

### User Story 2 - Monitor Active Executions in Real Time (Priority: P1)

The operator views a real-time data table of all currently active workflow executions across the platform. Each row shows the execution ID, agent FQN, workflow name, current step, status (running, paused, waiting_approval), start time, and elapsed duration. The table updates in real time via a live connection — new executions appear, completed ones disappear, and status changes reflect immediately. The operator can sort by start time or elapsed duration and filter by status.

**Why this priority**: Active executions are the operator's primary workload indicator. Real-time visibility into running workflows is essential for detecting stalls, bottlenecks, and runaway executions before they consume excessive resources.

**Independent Test**: Open the active executions panel. Confirm a data table renders with columns: execution ID, agent FQN, workflow name, current step, status badge, start time, elapsed duration. Trigger a new execution — confirm it appears in the table within 2 seconds. Complete an execution — confirm it disappears. Filter by "paused" — confirm only paused executions shown.

**Acceptance Scenarios**:

1. **Given** 25 active executions, **When** the operator views the executions table, **Then** a data table renders with columns: execution ID (truncated with copy action), agent FQN, workflow name, current step label, status badge (color-coded), start time, and elapsed duration (live-updating counter).
2. **Given** the active executions table, **When** a new execution starts, **Then** it appears at the top of the table within 2 seconds without a manual refresh.
3. **Given** the active executions table, **When** an execution completes or fails, **Then** it is removed from the table within 2 seconds.
4. **Given** the active executions table, **When** the operator filters by "paused" status, **Then** only paused executions are shown.
5. **Given** the active executions table, **When** the operator clicks an execution row, **Then** the browser navigates to the execution drill-down view.

---

### User Story 3 - Receive and Act on Operational Alerts (Priority: P1)

The operator monitors a real-time alert feed showing platform alerts from the monitoring system. Alerts stream in as they occur via a live connection. Each alert shows: severity level (info, warning, error, critical), source service, timestamp, message summary, and a brief description. The operator can filter alerts by severity. Critical and error alerts are visually prominent. The feed scrolls automatically to show the newest alerts but pauses auto-scroll when the operator scrolls up to read older alerts.

**Why this priority**: The alert feed is the operator's primary incident detection channel. Without real-time alerts, operators cannot respond to platform issues (resource exhaustion, service failures, security events) in a timely manner.

**Independent Test**: Open the alert feed. Confirm alerts render with severity badge, source, timestamp, and message. Trigger a test alert — confirm it appears within 2 seconds. Filter by "error" — confirm only error-level alerts shown. Scroll up — confirm auto-scroll pauses. Scroll back to bottom — confirm auto-scroll resumes.

**Acceptance Scenarios**:

1. **Given** the operator dashboard, **When** a new critical alert fires from the monitoring system, **Then** the alert appears in the feed within 2 seconds with a red "critical" severity badge, source service name, timestamp, and message summary.
2. **Given** the alert feed with 50 alerts, **When** the operator filters by "error" severity, **Then** only error-level alerts are shown.
3. **Given** the alert feed is auto-scrolling, **When** the operator scrolls up to read an older alert, **Then** auto-scroll pauses and a "New alerts ↓" indicator appears at the bottom.
4. **Given** auto-scroll is paused, **When** the operator scrolls back to the bottom, **Then** auto-scroll resumes.
5. **Given** the alert feed, **When** the operator clicks an alert, **Then** an expanded view shows the full alert details (description, affected service, suggested action if available).

---

### User Story 4 - Drill Into Execution with Reasoning Traces (Priority: P2)

The operator navigates to a specific execution's drill-down view to diagnose issues. The view contains three sections: (a) a reasoning trace panel showing the step-by-step reasoning chain as a collapsible tree — each step shows the reasoning mode, input summary, output summary, token count, duration, and any self-correction iterations; (b) a context quality panel showing the assembled context provenance — what data sources contributed to the context, their quality scores, and a visual provenance chain; (c) a budget consumption panel showing progress bars for each resource dimension (tokens used, tool invocations, memory writes, elapsed time) against their budgeted limits.

**Why this priority**: Execution drill-down is the diagnostic tool operators use after detecting an issue in US1–US3. Without it, operators can see that something is wrong but cannot determine why — making the overview and alert feed insufficient for incident resolution.

**Independent Test**: Navigate to an execution's drill-down. Confirm reasoning trace renders as collapsible steps. Expand a step — confirm mode, input, output, tokens, duration visible. Confirm context quality shows provenance sources with scores. Confirm budget bars show usage against limits. Confirm all three sections render for both running and completed executions.

**Acceptance Scenarios**:

1. **Given** a completed execution with 8 reasoning steps, **When** the operator opens its drill-down, **Then** the reasoning trace panel shows 8 collapsible step entries, each displaying reasoning mode label, input summary (truncated), output summary (truncated), token count, and step duration.
2. **Given** the reasoning trace, **When** the operator expands a step that had 2 self-correction iterations, **Then** the expanded view shows the correction chain: original output → correction reason → corrected output for each iteration.
3. **Given** the context quality panel, **When** the operator views it, **Then** each data source contributing to the execution's context is listed with: source type (memory, knowledge graph, evaluation), quality score (0–100), and a visual chain showing how context was assembled.
4. **Given** the budget consumption panel, **When** the operator views a running execution, **Then** progress bars display current usage / budgeted limit for each dimension: tokens (e.g., 15,000 / 50,000), tool invocations (e.g., 8 / 20), memory writes (e.g., 3 / 10), elapsed time (e.g., 45s / 120s).
5. **Given** a budget dimension at >90% usage, **When** the panel renders, **Then** that progress bar shows a warning color with a "near limit" indicator.

---

### User Story 5 - Monitor Queue Backlogs and Reasoning Budget (Priority: P2)

The operator views a queue backlog chart showing the consumer lag for each event topic as a bar chart. Each bar represents a topic, and the bar height represents the unconsumed message count (lag). Topics with high lag are highlighted in a warning color. Separately, the operator views a reasoning budget utilization gauge showing the aggregate budget usage across all active executions — representing how much of the total available reasoning capacity is currently committed.

**Why this priority**: Queue backlogs and budget utilization are leading indicators of capacity pressure. Monitoring them enables proactive scaling decisions and prevents queue overflows and budget exhaustion, which would cause execution failures.

**Independent Test**: Open the queue backlog panel. Confirm a bar chart renders with one bar per monitored topic. Confirm topics with high lag are highlighted. View the reasoning budget gauge — confirm it shows aggregate usage as a percentage. Confirm both update when data refreshes.

**Acceptance Scenarios**:

1. **Given** 10 monitored event topics, **When** the operator views the queue backlog chart, **Then** a bar chart renders with 10 labeled bars, each representing a topic's consumer lag count.
2. **Given** a topic with lag exceeding the warning threshold (default 10,000 messages), **When** the chart renders, **Then** that bar is highlighted in an amber/warning color.
3. **Given** the reasoning budget gauge, **When** the operator views it, **Then** a gauge visualization shows aggregate usage (e.g., "72% of reasoning capacity in use") computed across all active executions.
4. **Given** reasoning budget utilization exceeding 90%, **When** the gauge renders, **Then** it shows a critical color with a "capacity pressure" label.
5. **Given** both panels, **When** the underlying data refreshes (polling interval), **Then** the chart and gauge update visually within 5 seconds.

---

### User Story 6 - Monitor Attention Feed (Priority: P2)

The operator monitors a dedicated attention feed panel showing attention request events from agents in the platform. This feed is separate from the operational alert feed (US3) — it shows only agent-initiated attention requests, not system-level operational alerts. Each attention event displays: urgency level (low, medium, high, critical), requesting agent FQN, timestamp, a brief message summarizing what the agent needs, and the target context (execution, interaction, or goal). Urgency levels are color-coded: low as gray, medium as blue, high as orange, critical as red. The operator can click an attention event to navigate to the relevant context page (the execution detail, conversation, or goal).

**Why this priority**: The attention feed surfaces agent-initiated urgency signals that require human intervention. It bridges the gap between automated platform operations (US1–US3) and the agentic mesh's need for human-in-the-loop decisions, which is a core differentiator of the platform.

**Independent Test**: Open the attention feed panel. Confirm attention events render with urgency badge (color-coded), agent FQN, timestamp, and message. Confirm a critical attention event shows a red badge. Click an attention event — confirm navigation to the linked context (execution drill-down or conversation). Confirm attention events and operational alerts appear in separate panels.

**Acceptance Scenarios**:

1. **Given** 5 pending attention requests from different agents, **When** the operator views the attention feed, **Then** 5 entries render, each showing urgency badge (color-coded), agent FQN, timestamp, and message summary.
2. **Given** an attention event with urgency "critical", **When** it renders, **Then** the urgency badge is red and the entry is visually prominent (bold border or highlighted background).
3. **Given** an attention event targeting an execution, **When** the operator clicks it, **Then** the browser navigates to the execution drill-down page for that execution.
4. **Given** an attention event targeting a conversation, **When** the operator clicks it, **Then** the browser navigates to the conversation page for that interaction.
5. **Given** new attention events arrive via the live connection, **When** they stream in, **Then** they appear at the top of the feed within 2 seconds without a page refresh.

---

### Edge Cases

- What happens when a data store or satellite service is unreachable (health check times out)? The status indicator shows a gray "unknown" dot with a tooltip "Health check timed out after 5 seconds."
- What happens when the live connection (for alerts, executions, attention) disconnects? A connection status banner appears at the top of the dashboard indicating "Live updates paused — reconnecting..." and the system falls back to periodic polling (30-second interval) until the connection is restored.
- What happens when there are zero active executions? The active executions table shows an empty state: "No active executions. The platform is idle."
- What happens when an execution completes while the operator is viewing its drill-down? The drill-down remains visible with updated status and a "Completed" badge. Budget consumption bars freeze at their final values.
- What happens when the queue backlog data is unavailable (monitoring endpoint down)? The chart shows a "Backlog data unavailable" placeholder with a retry button.
- What happens when the attention feed and alert feed both have critical items? Each feed remains independent — critical alerts and critical attention requests are shown in their respective panels without merging.
- What happens when a reasoning step has extremely long output (thousands of tokens)? The output summary is truncated to the first 500 characters with a "Show full output" toggle that expands to the complete text.

## Requirements

### Functional Requirements

- **FR-001**: System MUST display a metric card grid with 6 operational indicators: active executions, queued steps, pending approvals, recent failures (last 1 hour), average latency (p50), and fleet health score
- **FR-002**: System MUST display service health indicators for all 8 data stores and 5 satellite services, each with a color-coded status dot (green/yellow/red/gray)
- **FR-003**: System MUST display a real-time data table of active executions with columns: execution ID, agent FQN, workflow name, current step, status badge, start time, and elapsed duration
- **FR-004**: Active executions table MUST update within 2 seconds when executions start, complete, fail, or change status, via a live connection
- **FR-005**: System MUST display a real-time alert feed showing platform alerts with severity (info/warning/error/critical), source service, timestamp, and message summary
- **FR-006**: Alert feed MUST update within 2 seconds when new alerts arrive via a live connection
- **FR-007**: Alert feed MUST support auto-scroll that pauses when the operator scrolls up and resumes when the operator scrolls to the bottom
- **FR-008**: System MUST display an execution drill-down view with three sections: reasoning traces, context quality, and budget consumption
- **FR-009**: Reasoning traces MUST render as a collapsible tree showing mode, input summary, output summary, token count, duration, and self-correction iterations for each step
- **FR-010**: Context quality section MUST display each contributing data source with source type, quality score (0–100), and provenance chain visualization
- **FR-011**: Budget consumption section MUST display progress bars for each resource dimension (tokens, tool invocations, memory writes, elapsed time) showing current usage against budgeted limits
- **FR-012**: Budget progress bars exceeding 90% usage MUST display a warning visual indicator
- **FR-013**: System MUST display a queue backlog bar chart showing consumer lag for each monitored event topic
- **FR-014**: Topics with lag exceeding the warning threshold MUST be highlighted in a warning color
- **FR-015**: System MUST display a reasoning budget utilization gauge showing aggregate capacity usage across all active executions
- **FR-016**: System MUST display a dedicated attention feed panel, separate from the alert feed, showing agent-initiated attention requests with urgency level, agent FQN, timestamp, and message
- **FR-017**: Attention events MUST use urgency color coding: low as gray, medium as blue, high as orange, critical as red
- **FR-018**: Clicking an attention event MUST navigate to the relevant context (execution drill-down, conversation, or goal page)
- **FR-019**: Attention feed MUST update within 2 seconds via a live connection
- **FR-020**: System MUST show a connection status banner when the live connection is disconnected, with automatic reconnection and polling fallback
- **FR-021**: All interfaces MUST be keyboard navigable and screen reader compatible
- **FR-022**: All interfaces MUST render correctly in both light and dark mode
- **FR-023**: All interfaces MUST be responsive across mobile and desktop viewport sizes

### Key Entities

- **OperatorMetrics**: A snapshot of platform-wide operational indicators — active execution count, queued step count, pending approval count, recent failure count, average latency, fleet health score. Refreshed on a polling interval.
- **ServiceHealthStatus**: The availability state of a single platform service — service name, service type (data store or satellite), status (healthy, degraded, down, unknown), last checked timestamp.
- **ActiveExecution**: A currently running workflow execution — execution ID, agent FQN, workflow name, current step label, status (running, paused, waiting_approval), start time. Updated in real time.
- **OperatorAlert**: A platform monitoring alert — severity (info, warning, error, critical), source service, timestamp, message summary, full description, suggested action.
- **ReasoningTrace**: The step-by-step reasoning record for an execution — ordered list of trace steps, each with reasoning mode, input/output summaries, token count, duration, and self-correction iterations.
- **ContextQualityView**: The provenance record for an execution's assembled context — list of data sources, each with source type, quality score, and contribution chain.
- **BudgetConsumption**: Resource usage for an execution — dimensions (tokens, tool invocations, memory writes, elapsed time), each with current value and budgeted limit.
- **AttentionEvent**: An agent-initiated attention request — urgency level (low, medium, high, critical), requesting agent FQN, timestamp, message, target type (execution, interaction, goal), and target ID for navigation.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An operator can assess overall platform health (metric cards + service status) within 5 seconds of opening the dashboard
- **SC-002**: New active executions, alerts, and attention events appear in their respective feeds within 2 seconds of occurrence
- **SC-003**: The operator can navigate from an alert or attention event to the relevant execution drill-down within 3 clicks
- **SC-004**: Reasoning trace expansion for an execution with up to 20 steps completes rendering within 2 seconds
- **SC-005**: Queue backlog chart and reasoning budget gauge update within 5 seconds of a polling refresh
- **SC-006**: The dashboard supports at least 100 concurrent active executions in the real-time table without visual degradation
- **SC-007**: When the live connection disconnects, the polling fallback activates within 5 seconds and the operator is notified immediately
- **SC-008**: All interfaces pass WCAG 2.1 AA accessibility audit
- **SC-009**: All interfaces render correctly in both light and dark mode with no visual artifacts

## Assumptions

- Backend APIs for platform metrics, service health, and execution details are available and operational (analytics feature 020, runtime controller 009, reasoning engine 011, execution engine 029)
- The monitoring system exposes an alerting endpoint or publishes alerts to the `monitor.alerts` event topic, which is consumed via the platform's live connection infrastructure (feature 019 WebSocket gateway)
- Kafka consumer lag metrics are available through a monitoring/admin endpoint (e.g., exposed by the Strimzi operator or a metrics aggregator) — the dashboard reads pre-aggregated lag values, it does not query Kafka directly
- The attention feed receives events via the platform's live connection using the `attention:{user_id}` channel subscription (feature 019 WebSocket gateway, feature 024 attention pattern)
- Reasoning traces and context quality data are retrieved from the execution engine's detail APIs — this dashboard displays pre-existing data, it does not compute or store traces
- Budget limits per execution are defined by the policy system (feature 028) and exposed through the execution detail API — the dashboard reads these values, not the raw policy definitions
- Service health checks are performed by a backend health aggregator that pings each data store and satellite service — the dashboard consumes the aggregated health status, not individual health endpoints
- The "recent failures" metric covers the last 1 hour by default — this is not configurable in this feature
- The operator role has read-only access to all dashboard data — no write operations are exposed through this feature except navigation actions
- Queue backlog warning threshold is a platform-level default (10,000 messages) — per-topic threshold configuration is not in scope for this feature
