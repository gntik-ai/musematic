# Feature Specification: Frontend Updates for All New Features

**Feature Branch**: `070-frontend-updates-cross-cutting`
**Created**: 2026-04-20
**Status**: Draft
**Input**: User description: "Update frontend to support FQN, visibility, workspace goals, alerts, governance, contracts, evaluation enhancements, A2A/MCP management, certification, decommissioning, and warm pool status."

---

## User Scenarios & Testing (mandatory)

### User Story 1 — Agent authoring with FQN, purpose, role, and visibility (Priority: P1)

As an **agent creator**, I need to define a new agent or edit an existing one with all the new identity and governance fields so the agent is addressable by fully-qualified name (FQN), declares an explicit purpose and approach, carries a role classification, and defines who can see it.

**Why this priority**: Without FQN + purpose + role + visibility editing in the UI, every other new backend capability (marketplace discovery, policy enforcement, zero-trust visibility) has no human-facing entry point. This is the single most-blocking UI gap.

**Independent Test**: Open the agent-edit form, populate namespace + local_name + purpose (≥ 50 chars) + approach + role_type + 2 visibility FQN patterns, save; verify the agent appears in the marketplace card list with its FQN displayed and its visibility honored (only matching workspaces can see it).

**Acceptance Scenarios**:

1. **Given** a user with create-agent permission in a workspace, **When** they open "Create Agent" and fill the form, **Then** they must provide (a) a namespace from the dropdown, (b) a local_name (alphanumeric + `-` + `_`), (c) a purpose textarea with ≥ 50 chars (the form blocks save with an inline error below 50), (d) an approach textarea (optional but recommended), (e) a role_type from a dropdown of all role enum values, and (f) zero or more visibility FQN patterns added via a repeatable input.
2. **Given** an existing agent created before this feature shipped, **When** the user opens "Edit Agent", **Then** the form loads the agent's existing FQN + purpose + approach + role + visibility patterns; any field that is `null` in the backend displays an empty input (not "undefined").
3. **Given** a user is editing the visibility pattern list, **When** they add the pattern `workspace:*/agent:*`, **Then** the UI previews the implied audience (e.g., "All workspaces, all agents") using a live description derived from the pattern.
4. **Given** the user attempts to save with `purpose` length < 50 chars, **When** they click Save, **Then** the save button is disabled and a character-count hint shows "X / 50" in red.

---

### User Story 2 — Marketplace discovery via FQN + purpose excerpt + role + certification (Priority: P1)

As an **agent consumer** browsing the marketplace, I need to discover agents by FQN and scan their purpose, role, and certification-expiry status at a glance so I can choose a trustworthy agent quickly.

**Why this priority**: FQN and certification are the two new identity dimensions that directly affect trust and discovery. Without them visible on cards, the marketplace remains pre-governance.

**Independent Test**: From the marketplace landing page, use the search bar to enter a partial FQN (e.g., `ops:`) and confirm the card grid filters to agents whose FQN matches; each filtered card shows the FQN, a purpose excerpt (first 120 chars with "…"), a role badge color-coded by role_type, and a certification-expiry indicator (green = > 30 days, amber = 7–30 days, red = < 7 days or expired).

**Acceptance Scenarios**:

1. **Given** an agent with FQN `research:arxiv-summarizer`, **When** the user types `research:` in the marketplace search bar, **Then** only agents whose FQN starts with `research:` appear in the grid (300ms debounce matches existing marketplace search UX).
2. **Given** a certified agent whose certification expires in 12 days, **When** the user views its marketplace card, **Then** the card shows an amber "Expires in 12 days" pill; on hover the pill reveals the exact expiry timestamp.
3. **Given** an agent whose certification has been revoked or expired, **When** the user views its marketplace card, **Then** the card shows a red "Certification expired" pill and the "Invoke Agent" button is disabled with a tooltip "Agent is not currently certified for use".

---

### User Story 3 — Workspace goal lifecycle + goal-scoped filtering + decision rationale (Priority: P1)

As a **workspace operator**, I need to see the current goal's lifecycle state, filter messages by goal, complete the goal when done, and inspect the agent's reasoning rationale in the debug panel so I can drive the conversation toward an explicit objective and audit agent decisions.

**Why this priority**: Workspace goals are the new correlation dimension (GID) that ties conversation history, execution metrics, and trust signals together. Exposing them in the UI is the only way users realize they exist.

**Independent Test**: Open a workspace, create a new goal with title + description, enter some agent-user turns, toggle the "Goal-scoped" message filter (seeing only messages tagged with the active goal), click "Complete Goal", confirm the goal moves to `completed` state, and open the debug panel to inspect one agent response's decision rationale (tool-choice, memory-retrieval, risk-assessment flags).

**Acceptance Scenarios**:

1. **Given** a workspace with an active goal, **When** the user loads the workspace view, **Then** the header displays a goal-state indicator (colored chip showing `open`, `in_progress`, `completed`, or `cancelled`), the goal title, and a "Complete Goal" button (disabled unless the goal is in `open` or `in_progress`).
2. **Given** the "Goal-scoped" filter is toggled on, **When** the message list re-renders, **Then** only messages whose backend correlation dimension matches the active goal's GID are shown; a banner reads "Filtered to goal: {goal title}" with a dismiss action that clears the filter.
3. **Given** the user opens the debug panel on a single agent response, **When** the response loads, **Then** the panel shows a structured "Decision Rationale" section with sub-sections for `tool_choices`, `retrieved_memories`, `risk_flags`, and `policy_checks`; each sub-section is collapsible.

---

### User Story 4 — Alert settings, per-interaction overrides, and real-time notification bell (Priority: P2)

As a **workspace user**, I need to configure which state transitions generate alerts, pick a delivery method, override alerts per interaction, and see a notification bell with an unread count that updates in real time so I stay informed without drowning in noise.

**Why this priority**: Alerts drive attention and engagement but can be noisy. A P2 priority reflects that the feature works without them (users can poll dashboards), but UX quality degrades significantly without real-time push.

**Independent Test**: Open the new alert-settings page, enable `execution.failed` and `trust.certification_expired` transitions with delivery = "in-app", disable `interaction.idle`, save; trigger a backend event matching an enabled transition; verify the notification bell increments, pulsates briefly, and shows the alert in a dropdown with a link to the relevant resource. Navigate to a specific interaction, toggle "Mute alerts for this interaction", trigger another event scoped to that interaction; verify no bell increment.

**Acceptance Scenarios**:

1. **Given** a new user visits the alert-settings page for the first time, **When** the page loads, **Then** default alert toggles are pre-populated from sensible defaults (critical transitions ON, informational OFF) and a banner reads "These are our recommended defaults; customize below".
2. **Given** the user enables an alert for `governance.verdict_issued` with delivery = "in-app", **When** the backend publishes that event for a resource visible to the user, **Then** within 3 seconds the notification bell increments its unread-count badge and the dropdown lists the alert at the top with a relative timestamp ("Just now") and a deep link to the resource.
3. **Given** the user has muted alerts on a specific interaction, **When** new alerts scoped to that interaction are published, **Then** the bell does NOT increment; but alerts scoped to a different interaction still increment normally.

---

### User Story 5 — Fleet/Workspace governance chain + visibility grants (Priority: P2)

As a **fleet or workspace administrator**, I need to configure the Observer → Judge → Enforcer governance chain and manage workspace-wide visibility grants so I can centrally control both the control plane behavior and the data boundaries of my workspace.

**Why this priority**: Governance-chain editing is a power-user feature — most workspaces will use the fleet default. Exposing it in a settings tab rather than a prominent workflow is appropriate.

**Independent Test**: Open workspace settings → "Governance" tab, drag-and-drop three agents into the Observer/Judge/Enforcer slots, save; trigger a violation event in the workspace; verify the Observer → Judge → Enforcer chain runs in order and a verdict appears in the governance verdict feed on the operator dashboard.

**Acceptance Scenarios**:

1. **Given** a workspace administrator is on the Governance tab, **When** they view the current chain, **Then** three slots (Observer, Judge, Enforcer) are displayed as card drop zones; each slot shows the currently-assigned agent's FQN + role badge or an empty placeholder labeled "No {role} assigned — fleet default applies".
2. **Given** an administrator drags an agent card from a side-panel picker into the Judge slot, **When** they save, **Then** a confirmation dialog summarizes the change ("Assign `ops:verdict-authority` as Judge?") and the save call emits a `governance.chain_updated` event; the slot updates in place.
3. **Given** the administrator opens the Visibility Grants tab, **When** they add a grant `workspace:*/agent:compliance-*`, **Then** a preview lists matching agents by FQN; on save, the grant is persisted and reflected in zero-trust visibility decisions for subsequent requests.

---

### User Story 6 — Execution detail: trajectory + checkpoints + debate + ReAct viewer (Priority: P2)

As an **evaluation engineer or debugging operator**, I need to see an execution's full trajectory with per-step efficiency indicators, roll back to any checkpoint, replay a debate transcript, and step through ReAct reasoning cycles so I can pinpoint where a run went wrong.

**Why this priority**: Trajectory visualization is the single most-requested evaluation UI addition; without it, trajectory-judge backend outputs (feature 067) are not consumable. Checkpoints unlock rerun workflows.

**Independent Test**: Open an execution detail page for a multi-step ReAct execution; verify the trajectory panel renders each step with efficiency badge (green/amber/red), a checkpoint list in the sidebar with rollback buttons, a debate transcript tab for multi-agent executions, and a ReAct cycle viewer that expands each Thought → Action → Observation triple.

**Acceptance Scenarios**:

1. **Given** an execution has 12 steps and 3 checkpoints, **When** the user opens the detail page, **Then** the trajectory visualization renders as a vertical timeline with one entry per step; each entry shows step index, tool/agent name, duration, token usage, and an efficiency badge (derived from backend trajectory-judge score).
2. **Given** the user clicks "Roll back to checkpoint" on checkpoint #2, **When** the confirmation dialog opens, **Then** it shows a summary of what will change (execution state resets, downstream steps discarded) and requires the user to type the checkpoint ID to confirm (destructive-action pattern).
3. **Given** an execution used multi-agent debate, **When** the user opens the "Debate" tab, **Then** the transcript renders as a chat-like feed colored by participant agent FQN; each message shows position (support/oppose/neutral) and a collapsible reasoning trace.
4. **Given** an execution used ReAct reasoning, **When** the user opens the "ReAct" tab, **Then** each cycle is grouped as a card with Thought (text), Action (tool call + args), and Observation (tool result); the user can expand/collapse any card.

---

### User Story 7 — Evaluation suite editor: rubric + calibration + trajectory comparison (Priority: P2)

As an **evaluation author**, I need to configure LLM-as-Judge rubrics, see calibration-score box plots, and pick a trajectory comparison method so I can build trustworthy evaluation suites.

**Why this priority**: Evaluation enhancements (LLM-as-Judge, trajectory comparison) are backend capabilities that need UI configuration to be usable. P2 because advanced evaluators can currently be configured via API directly.

**Independent Test**: Open the evaluation suite editor → "Rubric" section, add 3 rubric dimensions (each with weight + scale + description), save; run a calibration batch; verify the calibration-score box plot renders with one box per rubric dimension; switch the trajectory comparison method from "exact match" to "semantic similarity" and confirm the selection persists.

**Acceptance Scenarios**:

1. **Given** the user is editing an evaluation suite, **When** they add a rubric dimension, **Then** they must provide a name, a 1-sentence description, a weight (0.0–1.0), and a scale type (numeric 1–5 or categorical enum); the form validates weights sum to 1.0 across all dimensions with an inline hint "Weights must sum to 1.0 (current: 0.85)".
2. **Given** a rubric has been calibrated against a gold-standard set, **When** the user views the calibration panel, **Then** a box plot shows per-dimension score distribution (min / Q1 / median / Q3 / max) colored by dimension, with an outlier annotation when inter-rater agreement κ < 0.6.
3. **Given** the user selects "trajectory comparison" method, **When** they open the dropdown, **Then** they can choose from `exact_match`, `semantic_similarity`, `edit_distance`, or `trajectory_judge`; a description under the dropdown explains each option in one sentence.

---

### User Story 8 — Agent profile: contracts + A2A card + MCP servers (Priority: P3)

As an **agent operator or external integrator**, I need to manage the agent's contracts, view its A2A Agent Card JSON, and inspect its MCP server registrations so I can configure external interoperability.

**Why this priority**: A2A and MCP are external-interop features used by a smaller subset of users. P3 reflects this is an "advanced" profile tab.

**Independent Test**: Open an agent's profile page → "Contracts" tab, view the current active contract, add a new contract version, activate it; switch to the "A2A" tab and copy the Agent Card JSON; switch to the "MCP" tab and view the list of registered MCP servers with their capabilities.

**Acceptance Scenarios**:

1. **Given** an agent has 2 historical contracts and 1 active contract, **When** the user opens the Contracts tab, **Then** the tab lists all 3 contracts chronologically with badges (`active`, `superseded`); the user can view diff between any two.
2. **Given** the user opens the A2A tab, **When** the Agent Card renders, **Then** it appears as a syntax-highlighted JSON block with a "Copy" button; if the agent has no A2A configuration, the tab shows an empty-state "This agent is not exposed via A2A" with a "Configure" CTA.
3. **Given** the user opens the MCP tab, **When** MCP servers are listed, **Then** each row shows the server name, capabilities (tool count + resource count), health status (green/red dot), and a "Disconnect" action.

---

### User Story 9 — Trust workbench: third-party certifiers, expiry dashboard, surveillance (Priority: P3)

As a **trust reviewer**, I need to manage third-party certifiers, monitor certification expiries across all agents, and track surveillance status so I can maintain the trust posture of the platform.

**Why this priority**: Trust workbench already exists (feature 043). This expands it with advanced certifier management and fleet-wide dashboards — valuable but not blocking MVP delivery.

**Independent Test**: Open the trust workbench → "Certifiers" tab, add a third-party certifier with name + endpoint + public key, save; switch to the "Expiries" dashboard and see a sortable table of all agent certifications ordered by expiry-ascending; switch to "Surveillance" and view the latest continuous-monitoring signal per agent.

**Acceptance Scenarios**:

1. **Given** the user adds a third-party certifier, **When** they fill the form, **Then** they must provide a display name, an endpoint URL (HTTPS-only, validated), a public key (PEM format, validated), and a scope (which role_types the certifier is authorized to certify).
2. **Given** 47 certified agents exist, **When** the user opens the expiries dashboard, **Then** a table lists all 47 sorted by expiry-ascending; each row shows agent FQN, certifier name, issued-at, expires-at, and a status chip (green/amber/red matching US2 rules).
3. **Given** a surveillance signal is available for an agent, **When** the user opens the agent's surveillance detail, **Then** the panel shows the latest 20 signals (timestamped, categorized by signal type) with a trend sparkline.

---

### User Story 10 — Operator dashboard: warm pool + verdicts + decommission + reliability gauges (Priority: P3)

As a **platform operator**, I need to monitor warm-pool status, see a live governance verdict feed, trigger decommissioning flows for retired agents, and read five-nines reliability gauges so I can keep the platform healthy at a glance.

**Why this priority**: These are observability + admin features that exist in partial form elsewhere; this user story consolidates them on a single operator dashboard. P3 because operators can use backend APIs or individual dashboards today.

**Independent Test**: Open the operator dashboard; verify a warm-pool status panel showing target-vs-actual replica counts per profile, a governance-verdict feed updated in real time via WebSocket, a "Decommission Agent" action list with staged rollback controls, and three reliability gauges (API, execution, event delivery) each showing availability percentage over the last 30 days.

**Acceptance Scenarios**:

1. **Given** the warm pool has 3 profiles (small/medium/large), **When** the operator views the panel, **Then** each profile shows target replicas, actual replicas, and a delta badge (green = on target, amber = within 20%, red = below target); clicking a profile opens a detail drawer with the last 5 scaling events.
2. **Given** a governance verdict is issued in the last 60 seconds, **When** the verdict feed renders, **Then** the new verdict appears at the top with a subtle highlight flash; each verdict lists the offending agent FQN, the verdict type, the enforcer agent, and the action taken (quarantine/warn/block).
3. **Given** the operator clicks "Decommission Agent" for an agent, **When** the wizard opens, **Then** it shows a 3-stage flow (1) warning banner listing downstream dependencies, (2) a dry-run diff showing what will change, (3) a confirmation requiring typing the agent FQN; on confirm the decommission request is submitted and the agent status moves to `retiring`.

---

### Edge Cases

- **Agent editor with legacy agent missing FQN**: The backend returns `namespace=null` and `local_name=null` for pre-feature-053 agents; the form must display an inline prompt "This agent predates FQN — assign a namespace to activate governance features" and block save until both are filled.
- **Marketplace FQN search with special characters**: The search bar must safely handle colons, slashes, and wildcards (`*`); malformed patterns show a tooltip "Use pattern `namespace:local_name` or `namespace:*` for wildcard search" and do not submit.
- **Bell notification while dropdown is open**: A new alert must increment the count and insert at the top of the dropdown list without closing the dropdown or losing scroll position.
- **Governance chain save while Enforcer is unassigned**: Saving with one slot empty must prompt "No {slot} assigned — the fleet default will be used for this slot. Continue?" with Cancel/Confirm.
- **Trajectory panel for executions with 500+ steps**: The trajectory list must virtualize rendering (only visible entries in DOM) and display a "Showing N of total" banner.
- **Debate transcript rendering when one participant is a deleted agent**: The participant bubble must show a tombstone badge "Agent no longer exists" while still rendering their historical turns.
- **Rubric weights not summing to 1.0**: The Save button must stay disabled; the hint must show the current sum in real time as the user types.
- **A2A tab for agent with no A2A configuration**: Empty state shows "This agent is not exposed via A2A" with a "Configure" CTA that routes to the agent-edit form A2A section.
- **Operator dashboard with zero warm-pool profiles configured**: The panel shows an empty state "No warm-pool profiles configured" with a link to the runtime-controller admin page.
- **WebSocket disconnected during alert push**: The bell must show a small disconnected indicator (existing `ConnectionStatusBanner` pattern) and fall back to 30s polling for alert fetches; reconnection resumes real-time push transparently.

---

## Requirements (mandatory)

### Functional Requirements

#### Agent Authoring (US1)

- **FR-001**: The agent creation and edit forms MUST expose inputs for `namespace` (required, select from existing), `local_name` (required, `[a-zA-Z0-9_-]+`), `purpose` (required, ≥ 50 chars, multiline), `approach` (optional, multiline), `role_type` (required, select from enum), and `visibility_patterns` (zero or more, repeatable FQN pattern input with live-preview of implied audience).
- **FR-002**: The Save button on the agent form MUST be disabled when any required field is invalid or empty, with inline per-field error messages.
- **FR-003**: For an agent that predates FQN fields (legacy), the form MUST pre-fill with empty values and show a one-time prompt directing the user to complete the missing identity fields before saving.

#### Marketplace Discovery (US2)

- **FR-004**: Marketplace card listings MUST display FQN, a purpose excerpt (first 120 chars with ellipsis), a role badge color-coded by `role_type`, and a certification-expiry indicator (green > 30 days, amber 7–30 days, red < 7 days or expired).
- **FR-005**: Marketplace search MUST filter agents by FQN prefix match with 300ms debounce; search must be case-insensitive and safely handle colons, wildcards, and empty queries.
- **FR-006**: When an agent's certification is expired or revoked, its marketplace card MUST disable the "Invoke Agent" action with a tooltip explaining why.

#### Workspace Goals (US3)

- **FR-007**: The workspace view header MUST display the active goal's state (as a color-coded chip), title, and a "Complete Goal" button that is enabled only for `open` / `in_progress` states.
- **FR-008**: The workspace message list MUST support a "Goal-scoped" toggle that filters messages to those tagged with the active goal's GID; a banner announces the active filter and provides a dismiss action.
- **FR-009**: The debug panel for an agent response MUST show a "Decision Rationale" section with collapsible sub-sections: `tool_choices`, `retrieved_memories`, `risk_flags`, `policy_checks`.

#### Alert Settings & Notification Bell (US4)

- **FR-010**: A new alert-settings page MUST allow enabling/disabling per-transition alerts, choosing delivery method (`in-app`, `email`, `both`), and saving per-interaction overrides (mute/unmute).
- **FR-011**: A notification bell component MUST be present in the global header, displaying an unread-count badge that updates within 3 seconds of a backend alert event via WebSocket; clicking opens a dropdown of the latest 20 alerts with deep links.
- **FR-012**: Per-interaction alert overrides (mute) MUST suppress bell increments for events scoped to that interaction while still allowing increments for other scopes.
- **FR-013**: When the WebSocket is disconnected, the bell MUST show a disconnected indicator and fall back to 30s polling for alert fetches.

#### Governance Chain & Visibility Grants (US5)

- **FR-014**: A workspace (and fleet) governance settings tab MUST expose three slots (Observer / Judge / Enforcer) as drop zones; administrators can assign any compatible agent (by role_type) to a slot via drag-and-drop or a picker dialog.
- **FR-015**: Saving a governance-chain change with an empty slot MUST prompt for confirmation, indicating the fleet default will be applied to that slot.
- **FR-016**: A visibility-grants editor MUST support adding FQN patterns with live preview of matching agents by FQN; grants apply workspace-wide and persist via backend.

#### Execution Detail (US6)

- **FR-017**: The execution detail page MUST render a trajectory panel with one entry per step: step index, tool/agent name, duration, token usage, and an efficiency badge derived from the trajectory-judge score.
- **FR-018**: A checkpoint list in the sidebar MUST offer a "Roll back" action per checkpoint, gated by a destructive-action confirmation that requires typing the checkpoint ID.
- **FR-019**: For multi-agent-debate executions, a "Debate" tab MUST render the debate transcript as a participant-colored chat feed with position labels and collapsible reasoning traces.
- **FR-020**: For ReAct-mode executions, a "ReAct" tab MUST group each cycle as a card with Thought / Action / Observation, each independently expandable.
- **FR-021**: Trajectory rendering MUST virtualize for executions with more than 100 steps to maintain responsive scrolling.

#### Evaluation Suite Editor (US7)

- **FR-022**: The rubric section MUST allow adding, editing, and removing rubric dimensions (name, 1-sentence description, weight 0.0–1.0, scale type numeric or categorical).
- **FR-023**: The rubric editor MUST validate that dimension weights sum to 1.0 and disable Save when they do not.
- **FR-024**: A calibration panel MUST render per-dimension box plots (min / Q1 / median / Q3 / max) and annotate outliers where inter-rater agreement κ < 0.6.
- **FR-025**: A trajectory-comparison-method selector MUST offer `exact_match`, `semantic_similarity`, `edit_distance`, and `trajectory_judge` with a 1-sentence description of each.

#### Agent Profile — Contracts / A2A / MCP (US8)

- **FR-026**: The agent-profile Contracts tab MUST list all historical and active contracts chronologically with status badges; users can open a two-column diff between any two versions.
- **FR-027**: The A2A tab MUST display the Agent Card as syntax-highlighted JSON with a Copy action; if absent, an empty state directs users to configure A2A.
- **FR-028**: The MCP tab MUST list registered MCP servers with server name, capability counts, health status dot, and a Disconnect action.

#### Trust Workbench Expansions (US9)

- **FR-029**: A Certifiers tab MUST allow adding third-party certifiers with display name, HTTPS endpoint, PEM public key, and authorized-role-type scope.
- **FR-030**: A cross-agent expiries dashboard MUST show all certifications sorted by expiry-ascending with FQN, certifier, issued-at, expires-at, and a color-coded status chip.
- **FR-031**: A per-agent surveillance detail panel MUST render the latest 20 monitoring signals with timestamp, category, and a trend sparkline.

#### Operator Dashboard (US10)

- **FR-032**: A warm-pool status panel MUST show per-profile target and actual replica counts with a delta badge; clicking a profile opens a drawer with the 5 most recent scaling events.
- **FR-033**: A governance-verdict feed MUST render live updates via WebSocket, displaying offending agent FQN, verdict type, enforcer agent, and action taken; new entries flash briefly.
- **FR-034**: A decommission wizard MUST guide the operator through 3 stages: dependencies warning → dry-run diff → typed-confirmation; on confirm the agent moves to `retiring`.
- **FR-035**: Three reliability gauges (API, execution, event delivery) MUST show 30-day availability percentages with color thresholds (green ≥ 99.95%, amber 99.5–99.95%, red < 99.5%).

#### Cross-cutting

- **FR-036**: All new components MUST use existing shadcn/ui primitives and Tailwind tokens; no new UI libraries may be introduced.
- **FR-037**: All new data fetches MUST use TanStack Query v5 hooks consistent with the existing `lib/hooks/use-api.ts` factory pattern; loading and error states use existing `EmptyState` and `ConnectionStatusBanner` components.
- **FR-038**: All destructive actions (rollback, decommission, governance change) MUST use the existing `ConfirmDialog` pattern with typed-input confirmation where blast radius is irreversible.
- **FR-039**: All new views MUST respect existing RBAC: `platform_admin` for operator dashboard and trust workbench admin tabs; `workspace_admin` for workspace governance and visibility grants; `workspace_member` for goal operations; `viewer` for read-only observation across all surfaces.

### Key Entities

| Entity | Role in UI |
|---|---|
| **Agent** | Extended with `namespace`, `local_name`, `purpose`, `approach`, `role_type`, `visibility_patterns`, `certification` — surfaces in agent forms, marketplace cards, agent profile, governance-chain slots |
| **Workspace Goal** | `id` (GID), `title`, `description`, `state` (`open` / `in_progress` / `completed` / `cancelled`) — surfaces in workspace header, message filter, "Complete Goal" action |
| **Alert Rule** | `transition_type`, `delivery_method`, `scope` (workspace / interaction), `muted` — surfaces in alert-settings page, per-interaction overrides |
| **Alert** | `id`, `transition_type`, `resource_ref`, `timestamp`, `read` — surfaces in notification bell dropdown |
| **Governance Chain** | `observer_agent_fqn`, `judge_agent_fqn`, `enforcer_agent_fqn` (all optional — unset = fleet default) — surfaces in governance tab |
| **Visibility Grant** | `workspace_id`, `fqn_pattern`, `created_by`, `created_at` — surfaces in visibility-grants tab |
| **Trajectory Step** | `index`, `tool_or_agent_fqn`, `duration_ms`, `token_usage`, `efficiency_score` — surfaces in execution-detail trajectory panel |
| **Checkpoint** | `id`, `step_index`, `created_at`, `reason` — surfaces in execution-detail sidebar |
| **Debate Turn** | `participant_agent_fqn`, `position` (`support` / `oppose` / `neutral`), `content`, `reasoning_trace` — surfaces in debate tab |
| **ReAct Cycle** | `thought`, `action` (tool + args), `observation` — surfaces in ReAct tab |
| **Rubric Dimension** | `name`, `description`, `weight`, `scale_type` — surfaces in evaluation suite editor |
| **Agent Contract** | `version`, `status` (`active` / `superseded`), `published_at`, `signatories` — surfaces in agent-profile Contracts tab |
| **A2A Agent Card** | JSON document — surfaces in agent-profile A2A tab |
| **MCP Server Registration** | `name`, `capability_counts`, `health_status` — surfaces in agent-profile MCP tab |
| **Third-party Certifier** | `display_name`, `endpoint`, `public_key`, `authorized_scope` — surfaces in trust-workbench Certifiers tab |
| **Surveillance Signal** | `timestamp`, `category`, `value`, `trend` — surfaces in per-agent surveillance detail |
| **Warm-Pool Profile** | `name`, `target_replicas`, `actual_replicas`, `scaling_events` — surfaces in operator dashboard |
| **Governance Verdict** | `offending_agent_fqn`, `verdict_type`, `enforcer_agent_fqn`, `action_taken`, `issued_at` — surfaces in verdict feed |
| **Reliability Gauge** | `category` (API / execution / event_delivery), `availability_percent`, `window` — surfaces in operator dashboard |

---

## Success Criteria (mandatory)

### Measurable Outcomes

- **SC-001**: An agent creator can complete a new agent (with FQN, purpose, role, visibility) in ≤ 3 minutes, measured from "Create Agent" click to save confirmation, on the 50th-percentile first-time use.
- **SC-002**: At least 95% of marketplace searches with a valid FQN prefix return results within 500 ms of the last keystroke (after 300 ms debounce), on the landing page with 1,000+ agents.
- **SC-003**: When a backend alert event fires, 95% of eligible in-app notifications appear in the user's bell within 3 seconds (measured from Kafka publish to DOM paint).
- **SC-004**: Execution trajectory panels load and render the first 100 steps within 1 second on a recent workstation; virtualized scrolling maintains ≥ 50 FPS on panels with 1,000 steps.
- **SC-005**: Rubric-weight validation provides corrective feedback (sum not 1.0) within 100 ms of any keystroke on a weight input.
- **SC-006**: All new surfaces pass existing accessibility criteria (WCAG 2.1 AA): keyboard-only navigation, screen-reader labels on interactive elements, color-contrast ≥ 4.5:1 for text, no reliance on color alone for state.
- **SC-007**: No regressions in existing marketplace card, workspace view, execution detail, trust workbench, or operator dashboard features measured by the existing Playwright suites after this feature ships.
- **SC-008**: Users configuring their first governance chain or visibility grant complete the flow without opening documentation in ≥ 80% of sessions, measured by analytics event "help_link_clicked".
- **SC-009**: The decommission wizard blocks accidental decommissioning: in user testing, 100% of participants who intend to cancel successfully abort before the typed-confirmation step.
- **SC-010**: Unit-test coverage for new components is ≥ 80% statements; integration-test coverage of user stories US1–US10 is measured by one Playwright scenario per story.

---

## Assumptions

1. **No new UI library**: All new components extend shadcn/ui and Tailwind tokens; Recharts remains the sole charting library. No new drag-and-drop library (HTML5 native drag-and-drop is sufficient per feature 043 precedent).
2. **Backend contracts are stable**: All backend APIs for FQN / purpose / role / visibility / goals / alerts / governance chain / contracts / A2A / MCP / certification / warm-pool / verdicts are assumed available (from features 053, 056, 058, 060, 061, 062, 063, 065, 066, 067, plus existing 043).
3. **WebSocket topics reused**: Alert push, governance verdicts, and warm-pool updates use the existing WebSocket hub (feature 019) with new channel types `alerts`, `governance-verdicts`, `warm-pool`.
4. **RBAC map unchanged**: Existing role tiers (`platform_admin`, `workspace_admin`, `workspace_member`, `viewer`) are sufficient. No new role types needed in the UI permissions map.
5. **URL-driven state**: All list/search/filter views continue the existing URL-param pattern; deep-linking works for FQN search, goal-scoped message filter, expiries-dashboard sort, trajectory step anchor.
6. **Legacy data handling**: Pre-feature agents with `namespace=null` / `local_name=null` are tolerated everywhere — they display in the marketplace with a "Legacy agent" pill and are editable with a prompt to complete identity.
7. **Per-interaction alert overrides**: Mutes persist per-user, per-interaction in the backend; the UI reads/writes the mute state via the same alert-settings API as workspace-wide alerts.
8. **Trajectory judge availability**: When no trajectory-judge score is available for a step, the efficiency badge renders as a neutral gray "Unscored" badge rather than hiding the badge.
9. **Chart responsiveness**: Box plots and sparklines use Recharts responsive containers; on screens ≤ 768 px they render stacked single-column instead of side-by-side.
10. **Accessibility defaults**: All new color-coded chips include a text label in addition to color; screen readers announce state via `aria-label` or visible text.

---

## Dependencies

- **Backend features**: 053 (zero-trust visibility), 056 (IBOR integration), 060 (attention & alerts), 061 (judge/enforcer governance), 062 (agent contracts), 063 (reprioritization & checkpoints), 064 (reasoning modes trace), 065 (A2A gateway), 066 (MCP integration), 067 (trajectory judge evaluation) — all assumed shipped and stable.
- **Existing frontend features**: 015 (Next.js scaffold), 017 (login auth), 026 (home dashboard), 027 (admin settings), 035 (marketplace UI), 041 (catalog workbench), 042 (fleet dashboard), 043 (trust workbench), 044 (operator dashboard), 049 (analytics dashboard), 050 (evaluation testing UI) — modified here per section headers in the Summary.
- **Design system**: shadcn/ui (ALL UI primitives), Tailwind 3.4+, Recharts 2.x, TanStack Query v5, Zustand 5.x, React Hook Form 7.x + Zod 3.x — no new packages.
