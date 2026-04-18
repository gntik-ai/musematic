# Feature Specification: Evaluation and Testing UI

**Feature Branch**: `050-evaluation-testing-ui`  
**Created**: 2026-04-18  
**Status**: Draft  
**Input**: Eval suite management, results with score distribution, adversarial test generation, and simulation creation/comparison.  
**Requirements Traceability**: FEAT-FE-011 (Evaluation and Testing UI)

## User Scenarios & Testing

### User Story 1 - Eval Suite Browsing and Run Detail (Priority: P1)

An operator responsible for agent quality opens the evaluation page and sees a table listing all eval suites in their workspace. Each row shows the suite name, the target agent, the date of the last run, the aggregate score from the most recent run, and the current status (active or archived). The operator can filter the table by status and search by name. They click on a suite to open its detail page. The detail page shows the suite metadata (name, description, target agent, scorer configuration) and a list of evaluation runs ordered by date (most recent first). Selecting a run reveals its results: a table of individual test case verdicts (case name, expected output summary, actual output, score, pass/fail), aggregate metrics (total cases, passed count, failed count, average score), and a score distribution histogram showing how scores are spread across the run's verdicts.

**Why this priority**: Without the ability to browse and inspect eval results, operators cannot assess agent quality at all. This is the foundational view that all other evaluation features build upon.

**Independent Test**: Open the evaluation page with existing eval suites. Verify the DataTable renders with correct columns and data. Click a suite — verify the detail page loads with runs. Select a run — verify verdicts table, aggregate metrics, and score histogram all render correctly.

**Acceptance Scenarios**:

1. **Given** a workspace with eval suites, **When** the operator opens the evaluation page, **Then** a DataTable displays all suites with columns: name, target agent, last run date, last score, status.
2. **Given** the eval suite list is displayed, **When** the operator types in the search input, **Then** the table filters to show only suites whose name matches the search text.
3. **Given** the eval suite list is displayed, **When** the operator selects "active" in the status filter, **Then** only active suites are shown.
4. **Given** the operator clicks on an eval suite row, **When** the detail page loads, **Then** the suite metadata (name, description, target agent, scorer configuration) is displayed, along with a list of runs ordered by most recent first.
5. **Given** the operator selects an evaluation run, **When** the run detail expands, **Then** a verdicts table shows: case name, expected output summary, actual output, per-case score, pass/fail status.
6. **Given** a run is selected, **When** the operator views the aggregate metrics, **Then** total cases, passed count, failed count, and average score are displayed.
7. **Given** a run is selected, **When** the operator views the score histogram, **Then** a bar chart shows the distribution of verdict scores across defined buckets (e.g., 0–0.2, 0.2–0.4, …, 0.8–1.0).
8. **Given** a verdict has a status of "error", **When** the operator views that row, **Then** the error detail is visible in an expandable area, and the row is visually distinct (e.g., muted with a warning indicator).

---

### User Story 2 - Create and Run Evaluations (Priority: P1)

An operator wants to create a new eval suite to test an agent's quality. They click a "Create Eval Suite" button, fill in a name, select the target agent from a dropdown of agents in their workspace, and optionally add a description. They then add test cases one at a time, providing an input prompt and an expected output for each case. Alternatively, they can generate test cases adversarially (see US3). They configure the scorer by selecting from available scoring modes (e.g., LLM Judge with rubric, trajectory scoring) and setting thresholds. After saving the suite, they can trigger an evaluation run by clicking a "Run Evaluation" button. The run starts asynchronously — the status updates from "pending" to "running" to "completed" (or "failed"), with the page polling or subscribing for updates. Once complete, the results appear in the run detail view (US1).

**Why this priority**: Creating and running evaluations is the core write action — operators need to define what to test and execute it. Without this, the read view from US1 has no data.

**Independent Test**: Click "Create Eval Suite". Fill in name, select agent, add two test cases. Save. Click "Run Evaluation". Verify the run appears in the run list with status "pending", transitions to "running", then "completed". Navigate to the run detail and verify verdicts appear for each test case.

**Acceptance Scenarios**:

1. **Given** the operator is on the evaluation page, **When** they click "Create Eval Suite", **Then** a form appears with fields: name (required), target agent (required, dropdown), description (optional).
2. **Given** the create form is open, **When** the operator clicks "Add Test Case", **Then** a row is added with fields: input prompt (required, multiline) and expected output (required, multiline).
3. **Given** test cases are added, **When** the operator configures the scorer, **Then** they can select a scoring mode and set parameters (e.g., rubric template, pass threshold).
4. **Given** the form is complete, **When** the operator clicks "Save", **Then** the eval suite is created and the operator is navigated to the suite detail page.
5. **Given** the operator is on a suite detail page, **When** they click "Run Evaluation", **Then** a new run is created with status "pending" and appears in the runs list.
6. **Given** a run is in "pending" or "running" status, **When** the operator views the run, **Then** a progress indicator (spinner with status label) is shown, and the status auto-updates without manual page refresh.
7. **Given** a run transitions to "completed", **When** the operator views the run, **Then** the verdicts, aggregate metrics, and score histogram are available immediately.
8. **Given** the form has validation errors (e.g., no name, no agent selected, zero test cases), **When** the operator clicks "Save", **Then** validation messages appear for each failing field and the form is not submitted.

---

### User Story 3 - Adversarial Test Generation (Priority: P2)

An operator who wants to stress-test an agent's robustness uses the adversarial test generation feature. From the eval suite creation form (or from a suite's detail page), they click "Generate Adversarial Tests". The system sends a request to the backend ATE (Adversarial Testing Evaluation) service, which generates adversarial test cases based on the agent's configuration and known vulnerability patterns. The generated cases appear in a review list where the operator can accept, edit, or discard each one before adding them to the eval suite. A progress indicator shows while generation is running, since it may take time. Once added, these cases are treated identically to manually created cases.

**Why this priority**: Adversarial generation builds on the create flow from US2 but is a secondary enhancement — operators can create suites manually without it. It adds significant value for operators focused on safety and robustness.

**Independent Test**: Open a suite's detail page. Click "Generate Adversarial Tests". Wait for generation to complete. Verify generated cases appear in a review list. Accept one, edit another, discard a third. Verify accepted/edited cases are added to the suite's test cases. Discarded cases are removed.

**Acceptance Scenarios**:

1. **Given** the operator is on a suite detail page or in the create form, **When** they click "Generate Adversarial Tests", **Then** the system prompts the operator to confirm the target agent and starts an asynchronous generation request.
2. **Given** adversarial generation is running, **When** the operator waits, **Then** a progress indicator (spinner with "Generating..." label) is shown. The operator can continue viewing the suite while generation is in progress.
3. **Given** generation completes, **When** the operator views the results, **Then** a list of generated test cases is displayed, each with: input prompt, expected behavior, and a category tag (e.g., "injection", "boundary", "evasion").
4. **Given** the generated cases list is displayed, **When** the operator clicks "Accept" on a case, **Then** that case is added to the suite's test case list.
5. **Given** the generated cases list is displayed, **When** the operator clicks "Edit" on a case, **Then** the case opens in an editable form where the operator can modify the input, expected output, or category before accepting it.
6. **Given** the generated cases list is displayed, **When** the operator clicks "Discard" on a case, **Then** that case is removed from the generated list and is not added to the suite.
7. **Given** no adversarial cases could be generated (e.g., insufficient agent configuration), **When** the generation completes, **Then** a message explains why no cases were generated and suggests providing more agent context.

---

### User Story 4 - Eval Run Comparison (Priority: P2)

An operator wants to compare the results of two evaluation runs to understand whether a change improved or degraded agent quality. They select two runs (from the same or different suites) and open a side-by-side comparison view. The comparison shows: per-metric differences (average score, pass rate, total cases), a paired verdicts table where matching test cases are aligned side by side (showing both scores and whether each passed or failed), and a visual indicator for which run performed better overall. If the runs do not share the same test cases, unmatched cases are shown in a separate section.

**Why this priority**: Comparison enables the core iteration loop — operators run evaluations, make changes, re-evaluate, and compare. Without this, they must mentally compare results across separate pages.

**Independent Test**: Select two completed eval runs. Click "Compare". Verify side-by-side metrics render. Verify paired verdicts table aligns matching cases. Verify an overall verdict indicator shows which run is better.

**Acceptance Scenarios**:

1. **Given** the operator is on the evaluation page with completed runs, **When** they select two runs (via checkboxes or a selection mechanism), **Then** a "Compare" button becomes enabled.
2. **Given** the operator clicks "Compare", **When** the comparison view loads, **Then** side-by-side metric cards show: average score, pass rate, and total cases for each run, with delta values and directional indicators (up/down arrows with color).
3. **Given** both runs share overlapping test cases, **When** the paired verdicts table renders, **Then** matching cases are aligned side by side showing: case name, Run A score, Run B score, Run A pass/fail, Run B pass/fail, and the score delta.
4. **Given** some test cases exist in only one run, **When** the comparison view renders, **Then** unmatched cases are shown in a separate "Unique to Run A" / "Unique to Run B" section below the paired table.
5. **Given** the comparison is complete, **When** the operator views the overall verdict, **Then** a summary indicates which run performed better (or if they are equivalent), based on the aggregate score and pass rate.

---

### User Story 5 - Simulation Management (Priority: P2)

An operator managing agent deployments uses simulations to test changes in a safe, isolated environment. They open the simulations page and see a DataTable listing all simulation runs in their workspace with columns: name, status (provisioning, running, completed, cancelled, failed, timeout), digital twin(s) used, and completion date. They can create a new simulation by clicking "Create Simulation", selecting a digital twin (which represents a sandboxed copy of an agent), choosing a scenario configuration, optionally selecting an isolation policy, and launching the run. Once a simulation completes, the operator views its detail page showing execution results and a "SIMULATION" badge distinguishing it from production executions. The status auto-updates for in-progress simulations.

**Why this priority**: Simulation management is foundational for the simulation domain — operators must be able to list, create, and view simulations before comparing them. It parallels the evaluation browsing story (US1) in structure.

**Independent Test**: Open the simulations page. Verify the DataTable renders with correct columns. Click "Create Simulation". Select a digital twin, choose a scenario, launch. Verify the run appears in the list with status "provisioning". Verify status auto-updates. Click a completed simulation — verify detail page shows results with a "SIMULATION" badge.

**Acceptance Scenarios**:

1. **Given** a workspace with simulation runs, **When** the operator opens the simulations page, **Then** a DataTable displays all runs with columns: name, status (with status badge), digital twin(s), and completion date.
2. **Given** the simulations list is displayed, **When** the operator clicks "Create Simulation", **Then** a form appears with fields: name (required), digital twin selection (required, dropdown of active twins), scenario configuration (required), isolation policy (optional, dropdown with a default option), and an optional description.
3. **Given** the create form is complete, **When** the operator clicks "Launch", **Then** a new simulation run is created and the operator is navigated to the run detail page with status "provisioning".
4. **Given** a simulation is in an active status (provisioning, running), **When** the operator views the run detail, **Then** a progress indicator with status label is shown, and the status auto-updates without manual page refresh.
5. **Given** a simulation has completed, **When** the operator views its detail page, **Then** the execution results are displayed along with a prominent "SIMULATION" badge visually distinguishing it from production data.
6. **Given** a simulation is running, **When** the operator clicks "Cancel", **Then** a confirmation dialog appears. On confirmation, the simulation is cancelled and the status updates to "cancelled".
7. **Given** the operator views the digital twin details within the simulation, **Then** the source agent, version, and any applied modifications are visible.

---

### User Story 6 - Simulation vs Production Comparison (Priority: P3)

An operator who has run a simulation wants to understand how the simulated agent behavior compares to production behavior. They open a completed simulation and click "Compare with Production". A comparison view loads showing side-by-side metrics: the simulation's results versus production metrics for the same agent over a selected baseline period. The comparison includes metric differences (e.g., quality score delta, cost delta, latency delta), a visual verdict indicating whether the simulation performed better, worse, or equivalently, and any incompatibility warnings if the comparison is not strictly valid (e.g., different test conditions). The operator can also compare two simulation runs against each other using the same comparison interface.

**Why this priority**: Comparison is the payoff of running simulations — it answers "would this change improve things?" Without browsing and creating simulations (US5), there is nothing to compare. This is the final analytical step.

**Independent Test**: Open a completed simulation. Click "Compare with Production". Select a baseline period. Verify side-by-side metrics render. Verify the overall verdict indicator is shown. Trigger a simulation-vs-simulation comparison and verify the same interface works.

**Acceptance Scenarios**:

1. **Given** a completed simulation, **When** the operator clicks "Compare with Production", **Then** a form appears to select the production baseline period (e.g., last 7 days, last 30 days, or custom date range).
2. **Given** the baseline period is selected, **When** the comparison loads, **Then** side-by-side metrics are displayed: simulation results vs production results, with metric names, simulation values, production values, and deltas (with directional indicators).
3. **Given** the comparison is displayed, **When** the operator views the overall verdict, **Then** a summary indicates: "simulation better", "production better", "equivalent", or "inconclusive" with supporting rationale.
4. **Given** the comparison has incompatibility warnings, **When** the verdict renders, **Then** incompatibility reasons are listed (e.g., "Different model versions used", "Production period has insufficient data").
5. **Given** the operator wants to compare two simulations, **When** they select two completed simulation runs from the list, **Then** a "Compare" button becomes enabled. Clicking it opens the same comparison interface with "Run A" vs "Run B" labels instead of "Simulation" vs "Production".
6. **Given** a simulation has no production baseline data available, **When** the comparison loads, **Then** an empty state explains that production metrics are not available for the selected period and suggests a different date range.

---

### Edge Cases

- What happens when a workspace has no eval suites? The evaluation page shows an empty state encouraging the operator to create their first eval suite with a "Create Eval Suite" call-to-action button.
- What happens when an eval run fails? The run row shows a "failed" status badge. Clicking into it shows the error detail instead of verdicts. The score histogram is not rendered.
- What happens when adversarial generation produces zero results? A message explains that no cases were generated and suggests providing more agent context (US3 scenario 7).
- What happens when comparing runs with zero overlapping test cases? The paired verdicts table shows an empty state, and all cases appear in the "Unique to Run A" / "Unique to Run B" sections.
- What happens when the operator creates a simulation but the digital twin has warning flags? A warning banner is displayed on the create form showing the twin's warning flags (e.g., "Behavioral drift detected", "Stale configuration") before launch.
- What happens when a simulation times out? The detail page shows a "timeout" status badge with a message explaining the timeout and suggesting re-running with adjusted parameters.
- What happens on mobile devices? DataTables use horizontal scrolling for wide columns. Forms stack fields vertically. The comparison view stacks Run A and Run B vertically instead of side by side.
- What happens when the backend evaluation or simulation service is unavailable? Each section shows an inline error state with a retry button. The create forms remain accessible but submit actions show an error toast.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST display a searchable, filterable DataTable of eval suites with columns: name, target agent, last run date, last score, and status
- **FR-002**: The system MUST display an eval suite detail page showing suite metadata, a list of evaluation runs, and per-run results (verdicts table, aggregate metrics, score histogram)
- **FR-003**: The system MUST provide a form to create eval suites with: name (required), target agent (required), description (optional), test cases (at least one required), and scorer configuration
- **FR-004**: The system MUST allow adding test cases individually with input prompt and expected output fields
- **FR-005**: The system MUST support triggering evaluation runs asynchronously with automatic status updates (pending → running → completed/failed) without manual page refresh
- **FR-006**: The system MUST provide adversarial test generation that produces test cases from the target agent's configuration, with a review workflow (accept, edit, discard) before adding cases to the suite
- **FR-007**: The system MUST support side-by-side comparison of two evaluation runs, showing paired verdicts, aggregate metric deltas, and an overall verdict
- **FR-008**: The system MUST display a searchable DataTable of simulation runs with columns: name, status, digital twin(s), and completion date
- **FR-009**: The system MUST provide a form to create simulation runs with: name (required), digital twin selection (required), scenario configuration (required), isolation policy (optional), and description (optional)
- **FR-010**: The system MUST display a simulation detail page showing execution results with a prominent "SIMULATION" badge
- **FR-011**: The system MUST support simulation cancellation with a confirmation dialog
- **FR-012**: The system MUST support side-by-side comparison of simulation results vs production metrics for a selectable baseline period, or between two simulation runs
- **FR-013**: The system MUST display comparison verdicts (better, worse, equivalent, inconclusive) with metric deltas and directional indicators
- **FR-014**: All asynchronous operations (eval runs, adversarial generation, simulation runs, comparisons) MUST show progress indicators and auto-update status without manual refresh
- **FR-015**: All DataTables MUST support pagination
- **FR-016**: The system MUST display appropriate empty states when no eval suites, runs, simulations, or comparison data exists
- **FR-017**: Each section MUST handle backend errors independently — a failure in one area MUST NOT prevent other areas from functioning
- **FR-018**: The dashboard MUST be accessible (keyboard navigable, screen-reader compatible with chart descriptions)
- **FR-019**: The dashboard MUST render correctly in both light and dark modes
- **FR-020**: The dashboard MUST be responsive, adapting layout to mobile, tablet, and desktop viewports

### Key Entities

- **Eval Suite**: A collection of test cases targeting a specific agent. Contains: name, description, target agent, status (active/archived), scorer configuration, and a list of benchmark cases. The suite is the organizing unit for evaluation.
- **Benchmark Case**: A single test case within an eval suite. Contains: input prompt, expected output, and an optional category tag. Used by the evaluator to compare agent behavior against expectations.
- **Evaluation Run**: An execution of an eval suite against its target agent. Contains: status (pending/running/completed/failed), start and completion timestamps, aggregate score, and a list of verdicts. Runs are immutable once completed.
- **Judge Verdict**: The result of evaluating a single test case within a run. Contains: the benchmark case reference, actual output from the agent, per-scorer results, overall score, pass/fail determination, and optional error detail.
- **ATE Configuration**: A configuration for adversarial test generation. Contains: target scenarios, scorer configuration, performance thresholds, and safety check parameters. Used to generate adversarial test cases.
- **Simulation Run**: An isolated execution of a digital twin in a sandboxed environment. Contains: name, status (provisioning/running/completed/cancelled/failed/timeout), digital twin references, scenario configuration, isolation policy, and execution results.
- **Digital Twin**: A sandboxed copy of an agent used for simulation. Contains: source agent reference, version, configuration snapshot, behavioral history summary, any applied modifications, and warning flags.
- **Comparison Report**: The result of comparing two runs or a simulation against production. Contains: comparison type, metric differences, overall verdict (better/worse/equivalent/inconclusive), and any incompatibility reasons.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An operator can find a specific eval suite and view its latest run results within 3 interactions (open page, search/filter, click suite)
- **SC-002**: An operator can create an eval suite with test cases and trigger a run within 5 minutes
- **SC-003**: Adversarial test generation produces reviewable results within 60 seconds of initiation for a typical agent configuration
- **SC-004**: An operator can compare two eval runs and identify which performed better within 10 seconds of opening the comparison view
- **SC-005**: An operator can create and launch a simulation within 3 minutes
- **SC-006**: Simulation status transitions (provisioning → running → completed) are reflected in the UI within 5 seconds of the backend state change
- **SC-007**: An operator can compare simulation results against production metrics within 4 interactions (open simulation, click compare, select baseline, read verdict)
- **SC-008**: 100% of DataTables, forms, and charts render without error when backend data is available, including edge cases (zero data, failed runs, no overlapping cases)

## Assumptions

- The backend evaluation and testing service (feature 034) is deployed and serving all eval set, run, verdict, ATE, and robustness endpoints
- The backend simulation service (feature 040) is deployed and serving simulation run, digital twin, isolation policy, prediction, and comparison endpoints
- Workspace-scoped access control is enforced by the backend — the frontend sends the workspace context and trusts the backend to filter data
- Run status updates are delivered via polling (periodic refetch of run detail) unless a WebSocket channel for evaluation/simulation events is available, in which case real-time updates are preferred
- The score histogram uses frontend-computed buckets (e.g., 10 equal-width bins from 0 to 1) from the raw verdict scores — no backend histogram endpoint is needed
- The "SIMULATION" badge on simulation detail is a visual-only indicator — no special data transformation is needed beyond reading the run's origin
- Eval run comparison (US4) uses frontend logic to match test cases by case ID across runs — no backend comparison endpoint is required for eval runs
- The simulation comparison (US6) uses the backend comparison endpoint (`POST /simulations/{run_id}/compare`) which returns pre-computed metric differences and verdicts
- Digital twin selection in the create simulation form shows only active twins for the workspace
