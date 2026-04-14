# Tasks: Workflow Editor and Execution Monitor

**Input**: Design documents from `/specs/036-workflow-editor-monitor/`  
**Branch**: `036-workflow-editor-monitor`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included — acceptance criteria requires ≥95% coverage (Vitest + RTL + Playwright + MSW).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task serves (US1–US6 from spec.md)

## Path Conventions

Frontend only. All paths relative to `apps/web/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new packages, create route skeletons, and scaffold MSW mock stubs before any story work begins.

- [X] T001 Add `monaco-yaml` and `@dagrejs/dagre` to `apps/web/package.json` and run `pnpm install` in `apps/web/`
- [X] T002 [P] Create route skeleton pages: `app/(main)/workflow-editor-monitor/page.tsx`, `app/(main)/workflow-editor-monitor/new/page.tsx`, `app/(main)/workflow-editor-monitor/[id]/page.tsx`, `app/(main)/workflow-editor-monitor/[id]/executions/page.tsx`, `app/(main)/workflow-editor-monitor/[id]/executions/[executionId]/page.tsx` — each exports a minimal React component returning `null`
- [X] T003 [P] Add workflow-editor-monitor nav entry to the sidebar in `components/layout/Sidebar.tsx` (or wherever sidebar nav items are defined per existing pattern in `app/(main)/layout.tsx`)

**Checkpoint**: `pnpm dev` starts without errors; all 5 routes return 200.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: TypeScript types, Zustand stores, API hooks, and MSW mocks — required before any user story UI can be built.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Create `apps/web/types/workflows.ts` — `WorkflowDefinition`, `WorkflowVersion`, `WorkflowIR`, `WorkflowIRStep`, `WorkflowStepType`, `ReasoningMode`, `ContextBudget`, `WorkflowTrigger` (from `contracts/ts-types.ts` WorkflowDefinitionResponse, WorkflowVersionResponse, WorkflowIRResponse shapes)
- [X] T005 [P] Create `apps/web/types/execution.ts` — `ExecutionStatus`, `StepStatus`, `Execution`, `ExecutionState`, `StepResult`, `StepError`, `ExecutionEvent`, `ExecutionEventType`, `StepDetail`, `TokenUsage` (from `contracts/ts-types.ts`)
- [X] T006 [P] Create `apps/web/types/reasoning.ts` — `ReasoningTrace`, `ReasoningBranch`, `ChainOfThoughtStep`, `BudgetSummary`, `SelfCorrectionLoop`, `SelfCorrectionIteration` (from `data-model.md`)
- [X] T007 [P] Create `apps/web/types/task-plan.ts` — `TaskPlanRecord`, `TaskPlanCandidate`, `ParameterProvenance`, `ParameterSource`, `RejectedAlternative` (from `contracts/ts-types.ts` TaskPlanFullResponse)
- [X] T008 [P] Create `apps/web/lib/stores/workflow-editor-store.ts` — Zustand store with `yamlContent`, `validationErrors`, `isDirty`, `isSaving`, `lastSavedVersionId`, `graphNodes`, `graphEdges`, `parseError`, and actions `setYamlContent`, `setValidationErrors`, `markSaved` (from `data-model.md` WorkflowEditorStore)
- [X] T009 [P] Create `apps/web/lib/stores/execution-monitor-store.ts` — Zustand store with `executionId`, `executionStatus`, `stepStatuses`, `lastEventSequence`, `selectedStepId`, `activeDetailTab`, `totalTokens`, `totalCostUsd`, `wsConnectionStatus`, and actions `setExecutionState`, `applyEvent`, `selectStep`, `setDetailTab`, `setWsStatus`, `accumulateCost` (from `data-model.md` ExecutionMonitorStore)
- [X] T010 [P] Create `apps/web/lib/hooks/use-workflow-list.ts` — `useInfiniteQuery` wrapping `GET /api/v1/workflows?workspace_id&cursor&limit`; returns `WorkflowDefinition[]` with cursor pagination
- [X] T011 [P] Create `apps/web/lib/hooks/use-workflow.ts` — `useQuery` wrapping `GET /api/v1/workflows/{id}` and `GET /api/v1/workflows/{id}/versions/{versionId}`; returns `WorkflowDefinition` + `WorkflowVersion`
- [X] T012 [P] Create `apps/web/lib/hooks/use-workflow-save.ts` — two `useMutation` hooks: `useCreateWorkflow` (POST) and `useUpdateWorkflow` (PATCH); both invalidate `['workflows']` on success
- [X] T013 [P] Create `apps/web/lib/hooks/use-workflow-schema.ts` — `useQuery` wrapping `GET /api/v1/workflows/schema`; staleTime 1 hour; returns JSON Schema object
- [X] T014 [P] Create `apps/web/lib/hooks/use-execution-list.ts` — `useInfiniteQuery` wrapping `GET /api/v1/executions?workflow_id&cursor`
- [X] T015 [P] Create `apps/web/lib/hooks/use-execution-journal.ts` — `useInfiniteQuery` wrapping `GET /api/v1/executions/{id}/journal?since_sequence&event_type&step_id&limit&offset`
- [X] T016 [P] Create `apps/web/lib/hooks/use-step-detail.ts` — `useQuery` wrapping `GET /api/v1/executions/{executionId}/steps/{stepId}`; disabled until stepId provided
- [X] T017 [P] Create `apps/web/lib/hooks/use-reasoning-trace.ts` — derives reasoning branches from journal events filtered by `step_id` and `event_type=REASONING_TRACE_EMITTED`; wraps `use-execution-journal` with those filters
- [X] T018 [P] Create `apps/web/lib/hooks/use-task-plan.ts` — `useQuery` wrapping `GET /api/v1/executions/{executionId}/task-plan/{stepId}`; disabled until `enabled` flag set (lazy-loaded on tab open)
- [X] T019 [P] Create `apps/web/lib/hooks/use-execution-controls.ts` — seven `useMutation` hooks: `usePauseExecution`, `useResumeExecution`, `useCancelExecution`, `useRetryStep`, `useSkipStep`, `useInjectVariable`, `useApprovalDecision`; each optimistically updates `execution-monitor-store` status and rolls back on error
- [X] T020 [P] Create `apps/web/lib/hooks/use-cost-tracker.ts` — reads `totalTokens` and `totalCostUsd` from `execution-monitor-store`; exposes `expandedBreakdown` trigger that lazily fetches `GET /api/v1/analytics/usage?execution_id={id}`
- [X] T021 [P] Create MSW handler file `apps/web/src/mocks/handlers/workflows.ts` — handlers for GET/POST/PATCH workflow endpoints + schema endpoint
- [X] T022 [P] Create MSW handler file `apps/web/src/mocks/handlers/executions.ts` — handlers for execution CRUD, state, journal, step detail, and all 7 control action endpoints
- [X] T023 [P] Create MSW handler file `apps/web/src/mocks/handlers/task-plan.ts` — handler for `GET /executions/{id}/task-plan/{stepId}`
- [X] T024 [P] Create MSW handler file `apps/web/src/mocks/handlers/analytics.ts` — handler for `GET /analytics/usage?execution_id=...`
- [X] T025 [P] Write Vitest unit tests for all Zustand stores in `apps/web/lib/stores/__tests__/workflow-editor-store.test.ts` and `execution-monitor-store.test.ts` — test each action, derived state, and event application logic
- [X] T026 [P] Write Vitest unit tests for API hooks in `apps/web/lib/hooks/__tests__/` — test `use-workflow-list.ts`, `use-workflow.ts`, `use-workflow-save.ts`, `use-execution-controls.ts` with MSW

**Checkpoint**: All 23 hooks + 2 stores created, MSW handlers respond with fixture data, store tests pass, hook tests pass.

---

## Phase 3: User Story 1 — Author a Workflow Definition (Priority: P1) 🎯 MVP

**Goal**: Workflow authors can create and edit YAML workflow definitions with inline schema validation and a live DAG graph preview.

**Independent Test**: Open `/workflow-editor-monitor/new`, type a 4-step workflow YAML, see 4 nodes in the graph preview with correct edges, trigger a validation error, fix it, and save — all within the page.

### Implementation for User Story 1

- [X] T027 [P] [US1] Create `apps/web/lib/hooks/use-workflow-graph.ts` — parses `WorkflowIR` from `WorkflowVersion.compiledIr` into dagre-positioned `@xyflow/react` nodes and edges; `useMemo` on `compiledIr`; returns `{ nodes, edges, parseError }`; uses `@dagrejs/dagre` for top-to-bottom layout
- [X] T028 [P] [US1] Create `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx` — dynamic import (`next/dynamic`, `ssr: false`) of `@monaco-editor/react`; configure `monaco-yaml` with schema from `useWorkflowSchema()`; controlled by `workflow-editor-store.yamlContent`; 500ms debounced `onChange` dispatches `setYamlContent`; dark mode: sets `theme="vs-dark"` when `document.documentElement.classList.has('dark')`
- [X] T029 [US1] Create `apps/web/components/features/workflows/editor/WorkflowGraphPreview.tsx` — `<ReactFlow>` with `<MiniMap>`, `<Controls>`, `<Background>`; nodes sourced from `use-workflow-graph`; node background color driven by `data.hasValidationError` (red tint) or step type; `fitView` on initial load; zoom/pan enabled; empty state when `yamlContent` is empty
- [X] T030 [US1] Create `apps/web/components/features/workflows/editor/EditorToolbar.tsx` — Save button (calls `useUpdateWorkflow` or `useCreateWorkflow` depending on route); disabled when `!isDirty || isSaving`; shadcn `Badge` for version number; shadcn `Badge` (destructive) for validation error count when > 0; success toast on save
- [X] T031 [US1] Create `apps/web/components/features/workflows/editor/WorkflowEditorShell.tsx` — shadcn `ResizablePanelGroup` horizontal split (default 60/40); left panel: `MonacoYamlEditor`; right panel: `WorkflowGraphPreview`; right panel collapsible via toggle button; `EditorToolbar` above panels
- [X] T032 [US1] Implement `apps/web/app/(main)/workflow-editor-monitor/[id]/page.tsx` — fetch workflow + current version via `useWorkflow(id)`; pass version to `WorkflowEditorShell`; loading skeleton; not-found redirect; page title from workflow name
- [X] T033 [US1] Implement `apps/web/app/(main)/workflow-editor-monitor/new/page.tsx` — renders `WorkflowEditorShell` with empty YAML and no version (save → `useCreateWorkflow` → redirect to `[id]/page.tsx`)
- [X] T034 [US1] Implement `apps/web/app/(main)/workflow-editor-monitor/page.tsx` — infinite-scroll workflow card list using `useWorkflowList`; `WorkflowCard` per item (name, status badge, version number, createdAt, "Edit" link, "View Executions" link); "New Workflow" button; EmptyState when list is empty
- [X] T035 [P] [US1] Write component tests in `apps/web/components/features/workflows/editor/__tests__/` — test `MonacoYamlEditor` validation error display, `WorkflowGraphPreview` node/edge rendering, `EditorToolbar` save button state, save mutation call; use MSW + RTL

**Checkpoint**: Author can create workflow at `/workflow-editor-monitor/new`, see live graph, fix errors inline, and save. List page shows saved workflows.

---

## Phase 4: User Story 2 — Monitor a Live Execution (Priority: P1)

**Goal**: Operators see step node colors update in real time via WebSocket, with a streaming timeline of journal events and live summary metrics.

**Independent Test**: Start an execution against MSW, subscribe to mock WS events, confirm step nodes change color within 2 seconds, timeline events prepend in real time, and metrics update — without manual refresh.

### Implementation for User Story 2

- [X] T036 [P] [US2] Extend `apps/web/lib/hooks/use-execution-monitor.ts` — full implementation: call `wsClient.subscribe('execution:{executionId}', handler)`; on `step.state_changed` → `store.applyEvent`; on `execution.status_changed` → update status; on `event.appended` → invalidate journal query; on `budget.threshold` → `store.accumulateCost`; on disconnect → set `wsConnectionStatus`; on reconnect → re-fetch state + journal `since_sequence=lastEventSequence`; return unsubscribe on unmount
- [X] T037 [P] [US2] Create `apps/web/components/features/workflows/monitor/ExecutionGraph.tsx` — reuse `WorkflowGraphPreview` node/edge structure but source node color from `execution-monitor-store.stepStatuses` (see color mapping in `data-model.md`); click handler on node calls `store.selectStep(stepId)`; selected node has ring highlight; `fitView` on mount; minimap + zoom/pan
- [X] T038 [US2] Create `apps/web/components/features/workflows/monitor/ExecutionTimeline.tsx` — infinite-scroll list of `ExecutionEvent` items using `useExecutionJournal`; most recent at top; each event shows icon (by event category), event type label, step name (if stepId present), timestamp (date-fns `formatDistanceToNow`); color-coded left border by category (step events: blue, failures: red, approvals: yellow, reasoning: purple); "Load more" trigger at bottom
- [X] T039 [US2] Create `apps/web/components/features/workflows/monitor/ExecutionMonitorShell.tsx` — three-panel layout: left (40%) `ExecutionGraph`, center (35%) `ExecutionTimeline`, right (25%) `StepDetailPanel` (hidden/collapsed until `selectedStepId` is set); execution status header with current status badge, elapsed time, step progress (`completed/total`); `ConnectionStatusBanner` (reuse from 026 pattern) when `wsConnectionStatus !== 'connected'`
- [X] T040 [US2] Implement `apps/web/app/(main)/workflow-editor-monitor/[id]/executions/[executionId]/page.tsx` — fetch execution + workflow version via `useExecution(id)` and `useWorkflow(workflowId)`; mount `ExecutionMonitorShell`; pass execution to monitor store on mount; start execution monitor WebSocket subscription via `useExecutionMonitor(executionId)` 
- [X] T041 [US2] Implement `apps/web/app/(main)/workflow-editor-monitor/[id]/executions/page.tsx` — list past executions for a workflow via `useExecutionList(workflowId)`; each row: status badge, start time, duration, triggered by, "View Monitor" link; "Start New Execution" button → calls `useStartExecution` mutation (POST /executions) → redirect to monitor page
- [X] T042 [P] [US2] Write WebSocket simulation tests in `apps/web/components/features/workflows/monitor/__tests__/ExecutionGraph.test.tsx` and `ExecutionTimeline.test.tsx` — dispatch mock WS events via test utility, assert step node color changes and timeline event prepend; test reconnect + replay flow

**Checkpoint**: Operator can open an execution monitor, see real-time step color changes, and scroll the live timeline.

---

## Phase 5: User Story 3 — Inspect Step Details and Reasoning Traces (Priority: P2)

**Goal**: Clicking a step node opens a detail panel with inputs/outputs/timing, an expandable reasoning branch tree, and a self-correction convergence chart.

**Independent Test**: Click a completed step with reasoning traces — confirm detail panel opens with inputs/outputs shown, reasoning tab has expandable branches with statuses, and self-correction tab shows a quality-over-iterations line chart.

### Implementation for User Story 3

- [X] T043 [P] [US3] Create `apps/web/components/features/workflows/monitor/StepOverviewTab.tsx` — shows: inputs (JSON viewer component from shared), outputs (JSON viewer), duration (`formatDuration` from date-fns), context quality score (shadcn Progress or ScoreGauge from shared), error message + code when `error !== null`; skeleton while `useStepDetail` loading; empty state for steps not yet started
- [X] T044 [P] [US3] Create `apps/web/components/features/workflows/monitor/ReasoningTraceViewer.tsx` — recursive tree of `ReasoningBranch` items using shadcn `Collapsible`; each branch shows: status icon (completed=green check, pruned=gray X, failed=red X, active=blue spinner), token usage badge, budget remaining bar; chain-of-thought steps shown as numbered list inside expanded branch; "Load more branches" shadcn Button at bottom when `totalBranches > shown`; empty state: "No reasoning traces available for this step"
- [X] T045 [P] [US3] Create `apps/web/components/features/workflows/monitor/SelfCorrectionChart.tsx` — Recharts `<LineChart>`; X-axis: iteration number; Y-axis: quality score (0–1, fixed domain); `<Line>` for quality trend; `<ReferenceLine>` at convergence point (green dashed) or budget limit (red dashed) based on `loop.finalStatus`; `<Tooltip>` on hover shows quality score + token cost + delta; click `<Dot>` opens shadcn `Popover` with iteration detail; empty state: "No self-correction iterations for this step"
- [X] T046 [US3] Create `apps/web/components/features/workflows/monitor/StepDetailPanel.tsx` — shadcn `Tabs` with four triggers: "Overview", "Reasoning Trace", "Self-Correction", "Task Plan"; conditionally renders `StepOverviewTab`, `ReasoningTraceViewer`, `SelfCorrectionChart`, `TaskPlanViewer` per active tab; shows step name in panel header; close button sets `store.selectStep(null)`; renders loading skeleton while step data loads; mounts when `selectedStepId !== null`; `activeDetailTab` synced to `execution-monitor-store.activeDetailTab`
- [X] T047 [US3] Wire `StepDetailPanel` into `ExecutionMonitorShell.tsx` — show panel in right column when `selectedStepId` is set; animate slide-in; keyboard: Escape closes panel
- [X] T048 [P] [US3] Write component tests in `apps/web/components/features/workflows/monitor/__tests__/StepDetailPanel.test.tsx`, `ReasoningTraceViewer.test.tsx`, `SelfCorrectionChart.test.tsx` — test each tab renders correct data from MSW fixtures; test empty states; test "Load more branches" pagination trigger; test chart renders reference lines for converged vs budget-exceeded loops

**Checkpoint**: Clicking any completed step node shows its detail panel with all four tab stubs; Overview and Reasoning tabs populate from MSW data.

---

## Phase 6: User Story 4 — Control Execution Flow (Priority: P2)

**Goal**: Operators can pause, resume, cancel, retry a failed step, skip a blocking step, and inject a variable — each with a confirmation dialog.

**Independent Test**: Mount the monitor for a running execution; click Pause → confirm dialog appears → confirm → execution status changes to "paused"; click Resume → confirm → returns to running; click Retry on a failed step → step re-executes.

### Implementation for User Story 4

- [X] T049 [US4] Create `apps/web/components/features/workflows/monitor/ExecutionControls.tsx` — toolbar with 6 action buttons: Pause (enabled when status=`running`), Resume (enabled when status=`paused`), Cancel (enabled when status=`running|paused`), Retry (enabled when a `failed` step is `selectedStepId`), Skip (enabled when a `pending` step is `selectedStepId`), Inject Variable (enabled when status=`running|paused`); each button disabled with tooltip when RBAC insufficient (check `auth-store.user.roles`); buttons use shadcn `Button` with `variant="outline"` and Lucide icons
- [X] T050 [US4] Add `shadcn AlertDialog` confirmation flow to `ExecutionControls.tsx` — each action click opens `AlertDialog` with: title (action name), description (consequence text per action), Cancel + Confirm buttons; Confirm calls the corresponding mutation from `use-execution-controls`; dialog closes on success or error; error shown as shadcn `Toast`
- [X] T051 [US4] Add "Inject Variable" dialog to `ExecutionControls.tsx` — shadcn `Dialog` with React Hook Form + Zod form: `variableName` (required string, min 1 char) and `value` (required, JSON textarea validated with `JSON.parse`); optional `reason` textarea; Submit calls `useInjectVariable` mutation; form resets on success; validation errors shown inline
- [X] T052 [US4] Add approval decision flow to `StepDetailPanel.tsx` — when `activeTab === 'Overview'` and step status is `waiting_for_approval`: show "Approve" and "Reject" buttons + optional comment textarea; calls `useApprovalDecision`; buttons disabled while mutation pending
- [X] T053 [P] [US4] Write tests in `apps/web/components/features/workflows/monitor/__tests__/ExecutionControls.test.tsx` — test all 7 control action confirmation flows; test RBAC button disable; test inject variable form validation; test error toast on mutation failure

**Checkpoint**: All 7 control actions work end-to-end against MSW; confirmation dialogs appear before every action; RBAC correctly disables buttons for viewer role.

---

## Phase 7: User Story 5 — View Task Plan Records (Priority: P3)

**Goal**: Operators can open the "Task Plan" tab in step detail to see which agents were considered, which was selected and why, and the provenance of each parameter.

**Independent Test**: Click a completed agent-dispatched step, open "Task Plan" tab — confirm candidate list renders with suitability scores, selected agent is highlighted, rationale text is visible, and each parameter shows its source label.

### Implementation for User Story 5

- [X] T054 [P] [US5] Create `apps/web/components/features/workflows/monitor/TaskPlanViewer.tsx` — expandable tree using shadcn `Collapsible`: root node (step name) → "Candidates" section → each `TaskPlanCandidate` row (FQN, score as Progress bar, selected badge using shadcn `Badge`); → "Selected Agent" section (FQN + rationale text in shadcn `Alert`); → "Parameters" section → each `ParameterProvenance` row (name, value rendered as inline code, source badge with color by source type); "Rejected Alternatives" collapsible section; empty state: "No task plan available — this step was not dispatched to an agent"
- [X] T055 [US5] Wire lazy loading in `StepDetailPanel.tsx` — `use-task-plan` hook `enabled` prop set to `activeDetailTab === 'task-plan'`; show skeleton while loading; show empty state if 404 response
- [X] T056 [P] [US5] Write component tests in `apps/web/components/features/workflows/monitor/__tests__/TaskPlanViewer.test.tsx` — test candidate rendering with correct suitability scores, selected badge, rationale display, parameter provenance badges, empty state for non-agent steps; test lazy loading triggers only on tab open

**Checkpoint**: Task Plan tab loads lazily, shows full planning decision tree for any agent-dispatched step, shows empty state for non-agent steps.

---

## Phase 8: User Story 6 — Track Real-Time Costs (Priority: P3)

**Goal**: Operators see a real-time cost tracker showing accumulating token count and cost, with an expandable per-step breakdown.

**Independent Test**: Start an execution, dispatch mock `budget.threshold` WS events — confirm total tokens and cost increment in the tracker. Expand breakdown — confirm per-step rows sum to total, highest-cost step is highlighted.

### Implementation for User Story 6

- [X] T057 [P] [US6] Create `apps/web/components/features/workflows/monitor/CostTracker.tsx` — sticky bottom bar inside `ExecutionMonitorShell`; shows total tokens (formatted with thousands separator) + total cost USD (`$X.XXXX`); updates from `execution-monitor-store.totalTokens` and `totalCostUsd`; expand button shows per-step breakdown sorted by `costUsd` desc; highest-cost step row has `bg-yellow-50 dark:bg-yellow-950` highlight; per-step rows: step name, token count, cost USD, `percentageOfTotal` as shadcn `Progress`; "Expand" trigger uses shadcn `Collapsible`
- [X] T058 [US6] Wire `use-cost-tracker.ts` to WebSocket events — in `use-execution-monitor.ts`, on `budget.threshold` event call `store.accumulateCost(tokens, costUsd)` from the event payload; on step completion, fetch final `StepDetail.tokenUsage` and record per-step breakdown in store; lazy analytics fetch in `use-cost-tracker.ts` when breakdown expanded
- [X] T059 [P] [US6] Write component tests in `apps/web/components/features/workflows/monitor/__tests__/CostTracker.test.tsx` — test incremental token accumulation from WS events, per-step breakdown sum equals total, highest-cost highlighting, empty state when `totalTokens === 0`

**Checkpoint**: Cost tracker shows live total and accurate per-step breakdown; highest-cost step highlighted.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode, responsive layout, E2E tests, and coverage gap closure.

- [X] T060 [P] Dark mode: Ensure Monaco uses `vs-dark` theme when `document.documentElement.classList.has('dark')`; wire to `next-themes` `useTheme` hook in `MonacoYamlEditor.tsx`; verify `@xyflow/react` node styles use CSS custom property colors (not hardcoded hex) in `ExecutionGraph.tsx` and `WorkflowGraphPreview.tsx`
- [X] T061 [P] Responsive layout: Add mobile Sheet drawer for `ExecutionControls` (trigger via floating `MoreVertical` button on mobile); `ExecutionMonitorShell` collapses to single panel with tab-based switching on mobile (Graph / Timeline / Detail); `WorkflowEditorShell` stacks Monaco on top of graph preview on mobile (vertical split)
- [X] T062 [P] Accessibility: Add ARIA `role="img"` + `aria-label` on all `@xyflow/react` graph nodes; keyboard navigation (arrow keys move focus between nodes, Enter selects); `aria-live="polite"` region on `ExecutionTimeline` for new event announcements; focus trap in all dialogs and the step detail panel; label all form fields in the inject-variable dialog
- [X] T063 [P] Write Playwright E2E test in `apps/web/e2e/workflow-editor-monitor.spec.ts` — full golden path: open list → create new workflow → type YAML → verify graph → save → navigate to executions → start execution → monitor step transitions → click step → view reasoning tab → use pause control → resume; uses MSW WS mock for WS events
- [X] T064 [P] Coverage gap closure: Identify any hooks or utilities with <95% coverage via `pnpm test --coverage`; add targeted Vitest unit tests to `apps/web/lib/hooks/__tests__/` for uncovered branches (edge cases: empty journal, disconnected WS, failed mutations, optimistic rollback)
- [X] T065 [P] Validate dark mode renders correctly via Playwright visual snapshot test in `apps/web/e2e/workflow-editor-monitor.spec.ts` — set `colorScheme: 'dark'` in Playwright config, assert no white background on graph nodes, editor uses dark theme
- [X] T066 Run `pnpm lint` and TypeScript strict check (`pnpm tsc --noEmit`) in `apps/web/`; fix all lint errors and type errors introduced by new files

**Checkpoint**: All 15 acceptance criteria from spec satisfied; `pnpm test --coverage` shows ≥95% coverage; `pnpm lint` and `pnpm tsc` pass clean.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Depends on Phase 1 completion — **BLOCKS all user story phases**
- **Phase 3 (US1)**: Depends on Phase 2 — independent of US2–US6
- **Phase 4 (US2)**: Depends on Phase 2 — independent of US1 (shares store; reads step statuses only)
- **Phase 5 (US3)**: Depends on Phase 4 (step detail panel lives in monitor shell) — builds on US2
- **Phase 6 (US4)**: Depends on Phase 4 (controls live in monitor) — can be developed in parallel with US3
- **Phase 7 (US5)**: Depends on Phase 5 (task plan is a tab in step detail panel)
- **Phase 8 (US6)**: Depends on Phase 4 (cost tracker lives in monitor shell) — can be developed in parallel with US3/US4/US5
- **Phase 9 (Polish)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: After Foundation — no dependency on US2–US6
- **US2 (P1)**: After Foundation — no dependency on US1
- **US3 (P2)**: After US2 (step detail panel lives inside execution monitor shell)
- **US4 (P2)**: After US2 (controls live inside execution monitor) — parallel with US3
- **US5 (P3)**: After US3 (task plan is the 4th tab in step detail panel)
- **US6 (P3)**: After US2 (cost tracker is in monitor shell) — parallel with US3/US4/US5

### Within Each User Story

- Types (Phase 2) → Stores (Phase 2) → API Hooks (Phase 2) → Components → Page wiring → Tests
- Models/stores before hooks, hooks before components, components before page wiring
- Tests in each phase can be written alongside or immediately after implementation

### Parallel Opportunities

- All `[P]` tasks within Phase 2 (T004–T026) can run concurrently — different files
- US1 and US2 can run in parallel (different component trees, different stores sections)
- US3, US4, and US6 can all run in parallel after US2 is complete
- All tests marked `[P]` within each phase can be run in parallel

---

## Parallel Example: Foundation Phase (Phase 2)

```bash
# Run all in parallel — all touch different files:
Task T004: Create apps/web/types/workflows.ts
Task T005: Create apps/web/types/execution.ts
Task T006: Create apps/web/types/reasoning.ts
Task T007: Create apps/web/types/task-plan.ts
Task T008: Create apps/web/lib/stores/workflow-editor-store.ts
Task T009: Create apps/web/lib/stores/execution-monitor-store.ts
Task T010: Create apps/web/lib/hooks/use-workflow-list.ts
Task T011: Create apps/web/lib/hooks/use-workflow.ts
# ... then when types/stores are done:
Task T021: Create MSW handlers/workflows.ts
Task T022: Create MSW handlers/executions.ts
Task T023: Create MSW handlers/task-plan.ts
Task T024: Create MSW handlers/analytics.ts
```

## Parallel Example: US1 + US2 (run simultaneously after Phase 2)

```bash
# Developer A: US1 (workflow editor)
Task T027: use-workflow-graph.ts
Task T028: MonacoYamlEditor.tsx
Task T029: WorkflowGraphPreview.tsx
Task T030: EditorToolbar.tsx
Task T031: WorkflowEditorShell.tsx
Task T032: [id]/page.tsx
Task T033: new/page.tsx
Task T034: page.tsx (list)

# Developer B: US2 (execution monitor) simultaneously
Task T036: use-execution-monitor.ts (full WS impl)
Task T037: ExecutionGraph.tsx
Task T038: ExecutionTimeline.tsx
Task T039: ExecutionMonitorShell.tsx
Task T040: [executionId]/page.tsx
Task T041: executions/page.tsx
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundation types + stores + hooks (T004–T026)
3. Complete Phase 3: US1 Workflow Editor (T027–T035)
4. **STOP and VALIDATE**: Author can create and save a workflow with graph preview
5. Demo to stakeholders

### Incremental Delivery

1. Setup + Foundation → Foundation ready
2. US1 (editor) + US2 (monitor) in parallel → **Working editor and live monitor** (MVP for operations!)
3. US3 (step detail) + US4 (controls) in parallel → **Diagnostic + control capability**
4. US5 (task plan) + US6 (cost) in parallel → **Full transparency + cost visibility**
5. Polish → **Production-ready**

### Parallel Team Strategy (3 developers)

1. All complete Phase 1 + Phase 2 together
2. After Foundation:
   - **Dev A**: US1 (editor: T027–T035)
   - **Dev B**: US2 (monitor: T036–T042), then US3 (T043–T048), then US5 (T054–T056)
   - **Dev C**: US4 (controls: T049–T053), then US6 (T057–T059)
3. All three on Phase 9 (Polish: T060–T066)

---

## Notes

- `[P]` tasks = different files, no shared state dependencies — safe to run in parallel
- `[Story]` label maps each task to its user story for traceability
- Monaco dynamic import is required — do not attempt SSR (will throw)
- `@xyflow/react` node colors use CSS custom property tokens, not hardcoded hex — dark mode compatibility
- The 4 assumed endpoints (pause/retry/skip/inject) are marked in `contracts/api-endpoints.md` — verify paths with backend team before Phase 6 (US4)
- Commit after each task or logical group; each story phase should produce a shippable increment
