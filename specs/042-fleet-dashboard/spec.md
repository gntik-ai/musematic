# Feature Specification: Fleet Dashboard

**Feature Branch**: `042-fleet-dashboard`  
**Created**: 2026-04-16  
**Status**: Draft  
**Input**: User description for fleet list with topology visualization, member health, fleet performance charts, observer panel, and fleet controls.  
**Requirements Traceability**: FEAT-FE-007

## User Scenarios & Testing

### User Story 1 - Browse and Search Fleet List (Priority: P1)

A platform operator opens the fleet dashboard to find and inspect their active fleets. They see a searchable, sortable data table showing each fleet's name, topology type (e.g., hierarchical, mesh, star), member count, composite health score, and current status (active, paused, degraded, disbanded). They can filter by topology type, health threshold, or status. Clicking a fleet row navigates to its detail page showing the full fleet view.

**Why this priority**: The fleet list is the entry point for all fleet management activities. Without the ability to discover and navigate to fleets, no other dashboard capability (topology, controls, performance) is reachable. This is the foundational navigation surface.

**Independent Test**: Open the fleet dashboard page. Confirm a data table renders with columns: name, topology type, member count, health score, status. Type a search term — confirm filtering. Sort by health score — confirm ordering changes. Filter by status "active" — confirm only matching fleets shown. Click a row — confirm navigation to fleet detail.

**Acceptance Scenarios**:

1. **Given** 20 registered fleets, **When** the operator opens the fleet dashboard, **Then** a data table renders showing each fleet's name, topology type, member count, health score (0–100 with color indicator), and status with pagination (default 20 per page).
2. **Given** the fleet list is open, **When** the operator types "fraud" in the search field, **Then** the table filters within 300ms to show only fleets whose name contains "fraud".
3. **Given** the fleet list is open, **When** the operator selects filter "status: degraded", **Then** only fleets with degraded status are shown.
4. **Given** a filtered fleet list, **When** the operator clicks a fleet row, **Then** the browser navigates to that fleet's detail page.

---

### User Story 2 - View Fleet Topology Visualization (Priority: P1)

The operator views a fleet's topology as an interactive graph where each member agent is a node and communication channels are edges. Nodes display the agent's name and are color-coded by health status (green for healthy, yellow for degraded, red for critical). The graph layout matches the fleet's topology type (hierarchical tree for hierarchical, radial for star, force-directed for mesh). The operator can zoom, pan, and click a node to see that member's details in a side panel.

**Why this priority**: The topology visualization is the defining feature of the fleet dashboard — it transforms abstract fleet relationships into an intuitive visual representation. Operators cannot understand fleet structure or quickly identify problem areas without this view.

**Independent Test**: Navigate to a fleet detail page. Confirm a graph renders with agents as nodes and communication as edges. Confirm node colors match health status. Confirm zoom and pan work. Click a node — confirm side panel shows member details. Confirm layout matches topology type.

**Acceptance Scenarios**:

1. **Given** a fleet with 8 members in a hierarchical topology, **When** the operator opens the fleet detail, **Then** a graph renders with 8 nodes in a tree layout, edges showing communication channels, and each node color-coded by its health score.
2. **Given** the topology graph, **When** the operator zooms in on a cluster of nodes, **Then** the graph zooms smoothly and node labels remain readable.
3. **Given** the topology graph, **When** the operator clicks a member node, **Then** a side panel opens showing that agent's name, FQN, role, individual health score, status, and recent activity.
4. **Given** a fleet with a star topology, **When** the graph renders, **Then** the central orchestrator node appears at the center with member nodes arranged radially around it.

---

### User Story 3 - Monitor Fleet Health and Performance (Priority: P1)

The operator monitors a fleet's overall health via a composite health score gauge and views performance trends over time through charts showing success rate, average latency, and cost. The health gauge provides a breakdown of contributing factors on hover. The charts support time range selection (1h, 6h, 24h, 7d, 30d) and update in real-time when new data arrives via WebSocket.

**Why this priority**: Health and performance monitoring is the primary reason operators visit the fleet dashboard during operations. Without these metrics, operators cannot assess whether a fleet is meeting its objectives or detect degradation trends.

**Independent Test**: Open a fleet detail page. Confirm the health score gauge renders with a composite score and breakdown tooltip. Confirm three charts render: success rate, latency, cost. Change time range to 24h — confirm charts update. Confirm real-time data updates appear without page refresh.

**Acceptance Scenarios**:

1. **Given** a fleet with health data, **When** the operator views the fleet detail, **Then** a composite health score gauge (0–100) renders with color coding (red < 40, yellow 40–70, green > 70) and a breakdown tooltip showing component scores.
2. **Given** the fleet detail page, **When** the operator views the performance section, **Then** three charts display: success rate (percentage over time), average latency (milliseconds over time), and cost (currency units over time) for the default time range (24h).
3. **Given** the performance charts, **When** the operator selects "7d" time range, **Then** all three charts update to show the last 7 days of data with appropriate time axis labels.
4. **Given** an active fleet receiving new execution results, **When** new data arrives, **Then** the health gauge and performance charts update in real-time without requiring a page refresh.

---

### User Story 4 - Manage Fleet Members (Priority: P2)

The operator views all members of a fleet in a panel showing each member's name, FQN, role within the fleet, individual health score, and status. From this panel, the operator can add new members (selecting from registered agents), remove existing members (with confirmation), and view each member's contribution to fleet performance.

**Why this priority**: Member management is essential for fleet operations but builds on the fleet detail page (US2/US3) as the context. Operators need to understand fleet state before adding or removing members.

**Independent Test**: Open a fleet's member panel. Confirm all members listed with name, FQN, role, health, and status. Click "Add Member" — confirm agent selector appears. Select an agent — confirm it appears in the member list. Click "Remove" on a member — confirm dialog, confirm removal.

**Acceptance Scenarios**:

1. **Given** a fleet with 5 members, **When** the operator opens the member panel, **Then** all 5 members are listed with: name, FQN, role (executor, planner, orchestrator, observer, etc.), individual health score gauge, and status (active, idle, errored).
2. **Given** the member panel, **When** the operator clicks "Add Member", **Then** a dialog appears with a searchable list of registered agents (filtered by compatibility with the fleet's requirements), and selecting one adds it to the fleet.
3. **Given** the member panel, **When** the operator clicks "Remove" on a member, **Then** a confirmation dialog appears warning about the impact on fleet operations, and upon confirmation the member is removed from the fleet.
4. **Given** a fleet with an errored member, **When** the operator views that member, **Then** the member row is highlighted with an error indicator and shows the last error message in a tooltip.

---

### User Story 5 - Control Fleet Operations (Priority: P2)

The operator controls fleet lifecycle through operational actions: pause the fleet (halts all active executions gracefully), resume the fleet, scale the fleet (adjust target member count), and trigger a stress test (simulated load to validate fleet resilience). Each action requires confirmation and shows real-time status updates during execution.

**Why this priority**: Fleet controls are operational necessities that depend on understanding fleet state (US1–US3) before taking action. Pause/resume is critical for maintenance windows; scaling supports capacity management; stress testing validates fleet readiness.

**Independent Test**: Open a fleet's controls section. Click "Pause" — confirm dialog, confirm fleet status changes to "paused". Click "Resume" — confirm fleet returns to "active". Click "Scale" — confirm slider/input appears, set target count, confirm scaling begins. Click "Stress Test" — confirm dialog with parameters, confirm test starts with live progress.

**Acceptance Scenarios**:

1. **Given** an active fleet, **When** the operator clicks "Pause", **Then** a confirmation dialog appears with the fleet name and current active execution count, and upon confirmation the fleet status transitions to "pausing" then "paused" with real-time status updates.
2. **Given** a paused fleet, **When** the operator clicks "Resume", **Then** the fleet status transitions back to "active" and member agents begin accepting new executions.
3. **Given** an active fleet with 5 members, **When** the operator clicks "Scale" and sets the target to 8 members, **Then** the system shows a preview of which agents will be added (based on fleet requirements) and upon confirmation begins provisioning, showing real-time progress as new members join.
4. **Given** an active fleet, **When** the operator clicks "Stress Test", **Then** a dialog prompts for test parameters (duration, load level) and upon confirmation the test runs with a live progress indicator showing simulated executions, success rate, and latency during the test.

---

### User Story 6 - View Observer Agent Findings (Priority: P3)

The operator views findings from observer agents assigned to a fleet. Observer agents monitor fleet behavior and report their observations — including anomaly detections, performance concerns, coordination inefficiencies, and compliance issues. Each finding shows a severity level, timestamp, the observer that reported it, a description, and suggested actions. The operator can filter by severity and acknowledge findings.

**Why this priority**: Observer findings provide intelligence beyond raw metrics, but they are a secondary monitoring layer that builds on the base health and performance monitoring (US3). They add analytical depth for power users.

**Independent Test**: Open a fleet's observer panel. Confirm findings listed with severity, timestamp, observer name, description, and suggested action. Filter by "critical" severity — confirm only critical findings shown. Acknowledge a finding — confirm it moves to "acknowledged" status.

**Acceptance Scenarios**:

1. **Given** a fleet with 3 observer agents, **When** the operator opens the observer panel, **Then** all recent findings are listed chronologically with: severity (info, warning, critical), timestamp, reporting observer name, description, and suggested actions.
2. **Given** 20 observer findings, **When** the operator filters by severity "critical", **Then** only critical findings are shown.
3. **Given** an unacknowledged critical finding, **When** the operator clicks "Acknowledge", **Then** the finding status changes to "acknowledged" and it moves to an acknowledged section, preserving audit trail.
4. **Given** an observer finding with a suggested action, **When** the operator views the action, **Then** the suggestion includes enough detail to take corrective action (e.g., "Consider removing member X due to consistent timeout errors — 15 timeouts in last hour").

---

### Edge Cases

- What happens when a fleet has 0 members? The topology visualization shows an empty canvas with a "No members" message and a prominent "Add Member" button.
- What happens when the topology graph has more than 50 nodes? The graph applies automatic clustering for groups of tightly-connected nodes, with expandable clusters on click to prevent visual overload.
- What happens when a stress test is triggered on a fleet that is already under stress test? The action is disabled with a tooltip explaining a test is already in progress, showing elapsed time and a cancel option.
- What happens when the operator tries to pause a fleet during an active stress test? A warning dialog appears explaining that pausing will also cancel the running stress test, and asks for confirmation.
- What happens when WebSocket connection drops during real-time monitoring? A connection status banner appears (same pattern as home dashboard) and the system falls back to polling every 30 seconds until the connection is restored.
- What happens when the operator removes a member that is currently executing a task? A warning dialog explains the member has active executions and offers two options: "Wait for completion" (graceful) or "Force remove" (immediate, may affect execution).
- What happens when scaling requires agents that are not available? The scaling preview shows which positions cannot be filled and why (e.g., "No available agent with required capability: code-analysis"), allowing the operator to adjust.

## Requirements

### Functional Requirements

- **FR-001**: System MUST display a searchable, sortable, paginated data table of all fleets with columns: name, topology type, member count, health score, and status
- **FR-002**: System MUST support filtering fleets by topology type, status, health threshold, and free-text search with results appearing within 300ms of input
- **FR-003**: System MUST render an interactive topology graph showing fleet members as nodes and communication channels as edges, with layout matching the fleet's topology type
- **FR-004**: Topology graph MUST support zoom, pan, and node click to open member details
- **FR-005**: Topology graph nodes MUST be color-coded by health status (green > 70, yellow 40–70, red < 40)
- **FR-006**: System MUST display a composite fleet health score gauge (0–100) with color coding and component breakdown on hover
- **FR-007**: System MUST display three performance charts (success rate, latency, cost) with selectable time ranges (1h, 6h, 24h, 7d, 30d)
- **FR-008**: Health gauge and performance charts MUST update in real-time via WebSocket with fallback to 30-second polling
- **FR-009**: System MUST display a member panel listing all fleet members with name, FQN, role, individual health score, and status
- **FR-010**: System MUST support adding members to a fleet via a searchable agent selector filtered by fleet compatibility
- **FR-011**: System MUST support removing members with confirmation dialog that warns about active execution impact
- **FR-012**: System MUST support fleet pause (graceful halt) and resume operations with real-time status transitions
- **FR-013**: System MUST support fleet scaling with target member count, preview of proposed additions, and real-time provisioning progress
- **FR-014**: System MUST support triggering stress tests with configurable parameters (duration, load level) and live progress visualization
- **FR-015**: System MUST display observer agent findings with severity, timestamp, observer name, description, and suggested actions
- **FR-016**: System MUST support filtering observer findings by severity level and acknowledging individual findings
- **FR-017**: All interfaces MUST be keyboard navigable and screen reader compatible
- **FR-018**: All interfaces MUST render correctly in both light and dark mode
- **FR-019**: All interfaces MUST be responsive across mobile and desktop viewport sizes
- **FR-020**: Topology graph MUST apply automatic clustering when node count exceeds 50 to prevent visual overload

### Key Entities

- **Fleet**: A managed group of cooperating agents with a defined topology, operational status, composite health score, and performance history. The central management unit.
- **FleetMember**: An agent participating in a fleet with a specific role, individual health score, operational status, and contribution metrics. Nodes in the topology graph.
- **FleetTopology**: The structural arrangement of fleet members and their communication channels — defines node positions and edge connections for the visualization graph.
- **FleetPerformanceMetrics**: Time-series data tracking fleet-level success rate, average latency, and cost over configurable time ranges. Source data for performance charts.
- **ObserverFinding**: A report from an observer agent about detected anomalies, concerns, or recommendations, with severity, description, and suggested corrective actions.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An operator can find and navigate to a specific fleet from the dashboard within 10 seconds for a list of 50+ fleets
- **SC-002**: Fleet topology graph renders and becomes interactive within 3 seconds for fleets with up to 30 members
- **SC-003**: Health score gauge and performance charts load within 2 seconds of opening a fleet detail page
- **SC-004**: Real-time updates (health changes, new performance data) appear within 5 seconds of the backend event
- **SC-005**: Fleet control actions (pause, resume, scale) provide visual feedback within 1 second of operator confirmation
- **SC-006**: Stress test progress updates display in real-time with no more than 3-second lag
- **SC-007**: Observer findings panel loads and is filterable within 2 seconds for up to 100 findings
- **SC-008**: All interfaces pass WCAG 2.1 AA accessibility audit
- **SC-009**: All interfaces render correctly in both light and dark mode with no visual artifacts
- **SC-010**: Topology graph with 50+ nodes applies clustering automatically and remains interactive with no perceptible lag

## Assumptions

- Backend APIs for fleet management (feature 033) are available and operational, exposing fleet CRUD, membership management, health scores, performance metrics, and observer findings
- Fleet topology structure is provided by the backend as a graph (nodes + edges) — the frontend renders it but does not compute layouts from raw data
- Observer agents and their findings are managed by the backend; this feature only displays and allows acknowledging findings
- The stress test feature delegates to the backend simulation infrastructure (features 012, 040); this feature provides the UI trigger and progress display
- "Topology type" values include at least: hierarchical, mesh, star — the graph layout engine maps each to an appropriate layout algorithm
- The fleet health score is computed on the backend (similar to agent health in feature 034); this feature displays the pre-computed score
- WebSocket real-time updates follow the same pattern as the home dashboard (feature 026) using the existing WebSocket infrastructure (feature 019)
- Performance charts use aggregated time-series data from the backend analytics pipeline (feature 020), not raw event data
- Mobile responsiveness means usable on tablet-sized screens; the topology graph may use a simplified list view on screens below 768px
