# Feature Specification: Workflow Editor and Execution Monitor

**Feature Branch**: `036-workflow-editor-monitor`  
**Created**: 2026-04-13  
**Status**: Draft  
**Input**: User description: "YAML workflow editor with Monaco, schema validation, visual graph preview, live execution monitor with graph coloring, reasoning trace viewer, self-correction convergence chart, and operator controls."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author a Workflow Definition (Priority: P1)

A workflow author opens the workflow editor to create or edit a workflow definition. They write YAML in a full-featured code editor with syntax highlighting, schema-based validation, and intelligent autocomplete. As they type, a visual graph preview beside the editor renders the workflow as a directed acyclic graph (DAG) of steps connected by dependency edges. Validation errors appear inline in the editor and as annotations on the graph. The author saves the definition, which creates a new workflow version.

**Why this priority**: Authoring is the entry point for all workflow activity. Without a reliable editor, no workflows can be created or maintained. The graph preview provides immediate visual feedback that prevents structural errors before execution.

**Independent Test**: A user can open the editor, type a valid multi-step YAML workflow, see it render as a graph with correct step connections, fix any validation errors inline, and save it — all without leaving the page.

**Acceptance Scenarios**:

1. **Given** an empty editor, **When** the user types a valid workflow YAML with 4 sequential steps, **Then** the graph preview renders 4 nodes connected by directed edges in the correct order, and no validation errors appear.
2. **Given** a workflow YAML with a missing required field (e.g., step type), **When** the user saves or the editor validates on change, **Then** the editor underlines the error location, shows a hover tooltip with the specific error message, and the graph marks the invalid step visually.
3. **Given** the user is typing a step definition, **When** they trigger autocomplete, **Then** suggestions include valid step types, available agent names, trigger types, reasoning modes, and context budget options.
4. **Given** a valid workflow definition, **When** the user clicks save, **Then** a new immutable workflow version is created and the version identifier is displayed.

---

### User Story 2 - Monitor a Live Execution (Priority: P1)

An operator navigates to an active execution to monitor its progress in real time. They see the same workflow graph from the editor, but now each step node is colored by its current execution status: not started, running, completed, failed, or waiting for approval. A timeline panel streams execution journal events as they occur. Summary metrics (elapsed time, steps completed, cost so far) update continuously.

**Why this priority**: Real-time execution visibility is the core operational need. Operators must see what is happening at a glance to detect problems early and intervene when needed.

**Independent Test**: Start an execution, open the monitor, and confirm that step colors change in real time as steps progress, the timeline streams events, and summary metrics update — all without manual page refresh.

**Acceptance Scenarios**:

1. **Given** an execution with 6 steps where 2 are completed and 1 is running, **When** the operator opens the execution monitor, **Then** completed steps are green, the running step is blue, pending steps are gray, and the graph layout matches the workflow definition.
2. **Given** a running execution, **When** a step transitions from running to failed, **Then** the step node turns red within 2 seconds, a failure event appears at the top of the timeline, and the summary metrics update.
3. **Given** a step that requires approval, **When** the step enters waiting state, **Then** the step node turns yellow, and the timeline shows an approval request event with the approver information.
4. **Given** an execution is actively running, **When** the operator's connection is temporarily lost and restored, **Then** the monitor reconnects, replays missed events, and the display reflects the current execution state.

---

### User Story 3 - Inspect Step Details and Reasoning Traces (Priority: P2)

An operator clicks on a step node in the execution graph to open its detail panel. The panel shows the step's inputs, outputs, timing information, errors (if any), and context quality score. For steps that involved reasoning, a dedicated reasoning trace viewer displays the chain-of-thought in an expandable tree: branches, their statuses (active, completed, pruned), and budget consumption. For steps that triggered self-correction, a convergence chart shows how the output quality improved across iterations until the loop converged or the budget was exhausted.

**Why this priority**: After seeing what happened (Story 2), the next need is understanding why. Reasoning traces and self-correction visibility let operators diagnose quality issues and tune agent configurations.

**Independent Test**: Click on a completed step that used reasoning and self-correction, and confirm the detail panel shows inputs/outputs/timing, the reasoning trace is expandable and shows branch statuses, and the convergence chart plots iteration-over-iteration quality scores.

**Acceptance Scenarios**:

1. **Given** a completed step with reasoning traces, **When** the operator clicks the step node, **Then** a detail panel opens showing: inputs, outputs, duration, context quality score, and a "Reasoning Trace" tab.
2. **Given** the reasoning trace tab is open, **When** the operator expands a reasoning branch, **Then** they see the chain-of-thought steps, branch status (completed/pruned/failed), token usage, and budget remaining at each point.
3. **Given** a step that performed 4 self-correction iterations before converging, **When** the operator opens the self-correction tab, **Then** a chart plots quality score on the Y-axis and iteration number on the X-axis, showing the convergence trend. Each iteration point is clickable to see its details.
4. **Given** a step that failed due to budget exhaustion during self-correction, **When** the operator views the self-correction tab, **Then** the chart clearly marks the budget limit and the non-converging trend, and a message explains why the loop stopped.

---

### User Story 4 - Control Execution Flow (Priority: P2)

An operator monitoring an execution uses control actions to intervene. They can pause the execution (no new steps start, running steps continue to completion), resume a paused execution, cancel the entire execution, retry a failed step, skip a step that is blocking progress, or inject a variable value to override a parameter for the next step. Each action requires confirmation before execution.

**Why this priority**: Monitoring without the ability to act is insufficient. Operators need direct control to handle anomalies, recover from failures, and adapt execution on the fly.

**Independent Test**: Pause a running execution, confirm no new steps start, resume it and see steps continue, then retry a failed step and confirm it re-executes successfully.

**Acceptance Scenarios**:

1. **Given** a running execution with 2 active steps and 3 pending, **When** the operator clicks pause and confirms, **Then** no new steps are dispatched, the 2 active steps run to completion, and the execution status shows "paused."
2. **Given** a paused execution, **When** the operator clicks resume and confirms, **Then** pending steps begin dispatching according to the workflow DAG, and the execution status returns to "running."
3. **Given** a failed step, **When** the operator clicks retry and confirms, **Then** the step re-executes with its original inputs, and the timeline records a retry event.
4. **Given** a step blocking execution, **When** the operator clicks skip and confirms, **Then** the step is marked as skipped, downstream steps receive empty outputs from the skipped step, and execution continues.
5. **Given** a paused execution, **When** the operator injects a variable value, **Then** the injected value is used by the next step that references that variable, and the injection is recorded in the timeline.
6. **Given** any control action, **When** the operator clicks the action button, **Then** a confirmation dialog appears showing the action, the target (step or execution), and potential consequences before the action is executed.

---

### User Story 5 - View Task Plan Records (Priority: P3)

An operator inspects a completed or running step and navigates to the "Task Plan" tab in the step detail panel. This tab shows how the platform decided which agent to use for this step: the list of candidate agents and tools that were considered, the selected agent with the rationale for selection, and the parameter provenance (where each input parameter value came from). The view is an expandable tree: step → candidates → selected agent → parameters.

**Why this priority**: Understanding planning decisions is critical for debugging unexpected agent selection and for tuning fleet configurations. This is a specialized diagnostic view used less frequently than execution monitoring but essential for platform operators.

**Independent Test**: Open a completed step's task plan tab, and confirm it shows candidate agents, the selected agent with rationale text, and parameter provenance entries with source labels.

**Acceptance Scenarios**:

1. **Given** a completed step that considered 3 candidate agents, **When** the operator opens the task plan tab, **Then** all 3 candidates are listed with their agent names and suitability scores, and the selected agent is highlighted.
2. **Given** the selected agent is visible, **When** the operator expands the selection details, **Then** the rationale text explains why this agent was chosen over alternatives.
3. **Given** a step with 5 input parameters, **When** the operator expands the parameters section, **Then** each parameter shows its name, value, and provenance label (e.g., "from workflow definition", "from previous step output", "injected by operator").

---

### User Story 6 - Track Real-Time Costs (Priority: P3)

An operator monitoring an execution sees a persistent cost tracker that displays the total tokens consumed and the accumulated monetary cost for the current execution. The tracker updates in real time as steps consume tokens. The operator can expand it to see a per-step cost breakdown showing which steps are the most expensive.

**Why this priority**: Cost awareness during execution enables early intervention if a workflow is consuming more resources than expected, and helps operators optimize expensive workflows.

**Independent Test**: Start an execution, watch the cost tracker increment as steps run, expand to per-step view, and confirm the per-step costs sum to the total.

**Acceptance Scenarios**:

1. **Given** a running execution, **When** a step consumes tokens, **Then** the cost tracker total updates within 2 seconds to reflect the new token count and cost.
2. **Given** a completed execution with 5 steps, **When** the operator expands the cost breakdown, **Then** each step's token count and cost are listed, and their sum matches the total.
3. **Given** an execution where one step has consumed more than 50% of the total cost, **When** the cost breakdown is visible, **Then** that step is visually highlighted as the highest-cost step.

---

### Edge Cases

- What happens when a workflow YAML has circular dependencies between steps? The editor must detect and display a clear error message identifying the cycle, and the graph preview should not attempt to render the cycle.
- What happens when a workflow has 100+ steps? The graph must support zoom, pan, and a minimap for navigation. Step labels should remain readable at default zoom and gracefully truncate at lower zoom levels.
- What happens when an execution event arrives out of order due to network latency? The monitor must apply events by their sequence number, not arrival order, to maintain a consistent state.
- What happens when an operator attempts a control action on an execution that has already completed? The action must be rejected with a clear message indicating the execution is no longer controllable.
- What happens when the operator loses network connectivity during monitoring? A visible connection status indicator must appear, and the monitor must automatically reconnect and reconcile state on restore.
- What happens when the reasoning trace contains thousands of branches? The trace viewer must paginate or lazily load branches and indicate the total count.
- What happens when the user opens an execution that has no reasoning traces (simple steps only)? The reasoning tab must either be hidden or show an informational empty state.
- What happens when the YAML editor content exceeds a reasonable size (e.g., >10,000 lines)? The editor must remain performant with no visible lag in typing or validation feedback.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a code editor for authoring workflow definitions in YAML with syntax highlighting, bracket matching, and line numbering.
- **FR-002**: System MUST validate workflow YAML against the workflow definition schema in real time, displaying inline errors at the exact location of each violation.
- **FR-003**: System MUST provide context-aware autocomplete suggestions for step types, agent fully-qualified names, trigger types, reasoning modes, and context budget values.
- **FR-004**: System MUST render a directed acyclic graph (DAG) preview of the workflow beside the editor, where each step is a node and dependency relationships are directed edges.
- **FR-005**: System MUST synchronize the graph preview with editor content, updating the graph within 500 milliseconds of the user stopping typing (debounced).
- **FR-006**: System MUST detect circular dependencies in the workflow graph and display an error without attempting to render the cycle.
- **FR-007**: System MUST support saving a workflow definition, creating a new immutable version each time.
- **FR-008**: System MUST display a live execution view where each step node is colored by its current status: gray (not started), blue (running), green (completed), red (failed), yellow (waiting for approval).
- **FR-009**: System MUST stream execution journal events in real time to a timeline panel, ordered by event sequence number, with the most recent event at the top.
- **FR-010**: System MUST update execution graph node colors and summary metrics within 2 seconds of a status change occurring on the server.
- **FR-011**: System MUST allow the operator to click a step node to open a detail panel showing inputs, outputs, duration, errors, and context quality score.
- **FR-012**: System MUST display reasoning traces in an expandable tree view showing branches, their statuses (active, completed, pruned, failed), chain-of-thought content, token usage, and remaining budget.
- **FR-013**: System MUST display self-correction iteration history as a convergence chart with quality score on the Y-axis and iteration number on the X-axis, with clickable data points.
- **FR-014**: System MUST clearly indicate when self-correction stopped due to convergence versus budget exhaustion.
- **FR-015**: System MUST provide execution control actions: pause, resume, cancel, retry (failed step), skip (blocking step), and inject variable.
- **FR-016**: System MUST require confirmation for every control action, showing the action name, target, and potential consequences in a dialog before executing.
- **FR-017**: System MUST display a task plan viewer per step showing candidate agents/tools, the selected agent with rationale, and parameter provenance in an expandable tree.
- **FR-018**: System MUST keep the task plan viewer distinct and separate from the reasoning trace viewer (different tabs in the step detail panel).
- **FR-019**: System MUST display a real-time cost tracker showing total tokens consumed and accumulated monetary cost, updating as steps complete.
- **FR-020**: System MUST provide a per-step cost breakdown view that sums to the execution total.
- **FR-021**: System MUST support graph interactions: zoom, pan, minimap, and fit-to-view for large workflows.
- **FR-022**: System MUST display a connection status indicator during live monitoring, showing connected/disconnected state and auto-reconnecting with state reconciliation on restore.
- **FR-023**: System MUST restrict control actions based on the operator's role — only users with appropriate permissions can pause, resume, cancel, retry, skip, or inject variables.
- **FR-024**: System MUST lazy-load reasoning trace branches when the total count exceeds a pagination threshold, displaying total branch count upfront.
- **FR-025**: System MUST handle out-of-order execution events by applying them according to their sequence number, not arrival order.

### Key Entities

- **Workflow Definition**: A named, versioned workflow authored in YAML. Contains a DAG of steps with dependency edges, trigger configurations, and metadata. Each save creates an immutable version.
- **Workflow Step**: A single unit of work within a workflow. Has a type, optional agent assignment, reasoning mode, context budget, timeout, retry configuration, and approval gate. Connected to other steps via dependency edges.
- **Execution**: A single run of a specific workflow version. Progresses through states (queued, running, paused, waiting for approval, completed, failed, canceled). Has an append-only journal of events.
- **Execution Event**: An immutable journal entry recording a state change, step transition, reasoning emission, self-correction iteration, or operator action during an execution. Ordered by sequence number.
- **Reasoning Trace**: A tree of thought branches produced during a step's reasoning phase. Each branch has a status (active, completed, pruned, failed), chain-of-thought content, and token consumption.
- **Self-Correction Loop**: An iterative refinement cycle within a step, tracked by iteration number, quality score, and convergence status. Terminates on convergence or budget exhaustion.
- **Task Plan Record**: A record of the planning decision for a step: which agents/tools were considered, which was selected and why, and where each input parameter value originated.
- **Cost Record**: Per-step and per-execution aggregation of tokens consumed and monetary cost.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Workflow authors can create a valid multi-step workflow definition and see it rendered as a correct visual graph in under 5 minutes for a typical 10-step workflow.
- **SC-002**: Operators can identify a failed step in a running execution within 5 seconds of the failure occurring, without manual page refresh.
- **SC-003**: 90% of operators can successfully pause, diagnose (via reasoning trace or step detail), and resume or retry an execution on their first attempt without external guidance.
- **SC-004**: The execution monitor displays the current state of all steps accurately at all times, with no stale or inconsistent state visible to the operator for more than 2 seconds.
- **SC-005**: Operators can view the cost breakdown for a completed execution and identify the most expensive step within 10 seconds.
- **SC-006**: The workflow graph remains interactive and responsive for workflows with up to 100 steps — zoom, pan, and node click respond within 300 milliseconds.
- **SC-007**: Workflow authors encounter zero save failures due to undetected validation errors — all schema violations are caught and displayed before save is attempted.
- **SC-008**: The editor autocomplete reduces workflow authoring errors by suggesting only valid values for each field context.

## Assumptions

- Operators and workflow authors are authenticated users with appropriate workspace-scoped roles (e.g., workspace member or above for viewing, workspace admin or above for control actions).
- The backend workflow execution engine (feature 029) and runtime controller (feature 009) are operational and expose the necessary APIs for workflow CRUD, execution control, and event streaming.
- The WebSocket real-time gateway (feature 019) is available for streaming execution events to the monitor via the existing `execution` channel type.
- Reasoning traces and self-correction data are emitted as execution journal events by the reasoning engine (feature 011) and are accessible through the same event stream.
- Task plan records are stored by the runtime controller (feature 009) and retrievable via API per execution step.
- Cost and token data are available from the analytics and cost intelligence service (feature 020) and are included in execution event payloads or queryable per execution.
- The workflow YAML schema is defined by the backend and can be loaded by the editor for validation and autocomplete.
- The platform's existing component library, theming system, and layout shell are used for consistent look and feel.
- The existing graph and charting libraries in the project's dependency tree are used for the DAG preview and convergence charts.
