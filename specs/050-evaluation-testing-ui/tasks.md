# Tasks: Evaluation and Testing UI

**Input**: Design documents from `specs/050-evaluation-testing-ui/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ui-components.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

---

## Phase 1: Setup (Types and Query Keys)

**Purpose**: TypeScript type definitions and TanStack Query key objects. No UI, no network calls — just types.

- [X] T001 Create `apps/web/types/evaluation.ts` with all evaluation TypeScript types: EvalSetStatus, RunStatus, VerdictStatus, ExperimentStatus, ATERunStatus, ReviewDecision, EvalSetResponse, EvalSetListResponse, BenchmarkCaseResponse, BenchmarkCaseListResponse, EvaluationRunResponse, EvaluationRunListResponse, JudgeVerdictResponse, JudgeVerdictListResponse, HumanAiGradeResponse, AbExperimentResponse, ATEConfigResponse, ATEConfigListResponse, ATERunResponse, EvalListFilters, ScoreHistogramBin, PairedVerdict, ATEGeneratedCase, BenchmarkCaseCreateInput, EvalSetCreateInput; export `evalQueryKeys` object with keys: evalSets, evalSet, cases, runs, run, verdicts, experiment, ateConfigs, ateRun
- [X] T002 [P] Create `apps/web/types/simulation.ts` with all simulation TypeScript types: SimRunStatus, PredictionStatus, ConfidenceLevel, ComparisonType, ComparisonVerdict, ComparisonReportStatus, SimulationRunResponse, SimulationRunListResponse, SimulationRunCreateInput, DigitalTwinResponse, DigitalTwinListResponse, SimulationIsolationPolicyResponse, SimulationIsolationPolicyListResponse, MetricDifference, SimulationComparisonReportResponse, SimulationComparisonCreateInput; export `simQueryKeys` object with keys: runs, run, twins, isolationPolicies, comparison

---

## Phase 2: Foundational (Hooks and Route Shell)

**Purpose**: All 11 TanStack Query hooks + layout + page stubs. MUST be complete before any user story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Create `apps/web/lib/hooks/use-eval-sets.ts` exporting `useEvalSets(workspaceId: string, filters: EvalListFilters)` and `useEvalSet(evalSetId: string)` using `useAppQuery`; GET `/api/v1/evaluations/eval-sets` with `?status=&search=&page=` query params; `staleTime: 30_000`; uses `evalQueryKeys.evalSets` and `evalQueryKeys.evalSet`
- [X] T004 [P] Create `apps/web/lib/hooks/use-eval-runs.ts` exporting `useEvalRuns(workspaceId: string, evalSetId?: string)` (GET `/api/v1/evaluations/runs?eval_set_id=...`) and `useEvalRun(runId: string)` (GET `/api/v1/evaluations/runs/{runId}`) with `refetchInterval: (query) => ["completed","failed"].includes(query.state.data?.status) ? false : 3000`
- [X] T005 [P] Create `apps/web/lib/hooks/use-eval-verdicts.ts` exporting `useEvalSetCases(evalSetId: string, page?: number)` (GET `/api/v1/evaluations/eval-sets/{evalSetId}/cases`) and `useEvalRunVerdicts(runId: string, page?: number)` (GET `/api/v1/evaluations/runs/{runId}/verdicts`)
- [X] T006 [P] Create `apps/web/lib/hooks/use-ab-experiment.ts` exporting `useAbExperiment(experimentId: string | null)` (GET `/api/v1/evaluations/experiments/{experimentId}`) with `enabled: Boolean(experimentId)` and `refetchInterval: (query) => ["completed","failed"].includes(query.state.data?.status) ? false : 3000`
- [X] T007 [P] Create `apps/web/lib/hooks/use-ate.ts` exporting `useAteConfigs(workspaceId: string)` (GET `/api/v1/evaluations/ate`) and `useAteRun(ateRunId: string | null)` (GET `/api/v1/evaluations/ate/runs/{ateRunId}`) with `enabled: Boolean(ateRunId)` and `refetchInterval` stopping on terminal statuses: `"completed" | "failed" | "pre_check_failed"`
- [X] T008 [P] Create `apps/web/lib/hooks/use-eval-mutations.ts` exporting `useEvalMutations()` returning: `createEvalSet` (POST `/api/v1/evaluations/eval-sets`), `addCase` (POST `/api/v1/evaluations/eval-sets/{evalSetId}/cases`), `runEval` (POST `/api/v1/evaluations/eval-sets/{evalSetId}/run`), `createExperiment` (POST `/api/v1/evaluations/experiments`), `runAte` (POST `/api/v1/evaluations/ate/{ateConfigId}/run/{agentFqn}`); each invalidates the relevant `evalQueryKeys` on success
- [X] T009 [P] Create `apps/web/lib/hooks/use-simulation-runs.ts` exporting `useSimulationRuns(workspaceId: string, cursor?: string)` (GET `/api/v1/simulations/?workspace_id=...&cursor=...`) and `useSimulationRun(runId: string)` (GET `/api/v1/simulations/{runId}`) with `refetchInterval` stopping on terminal statuses: `"completed" | "cancelled" | "failed" | "timeout"`
- [X] T010 [P] Create `apps/web/lib/hooks/use-digital-twins.ts` exporting `useDigitalTwins(workspaceId: string, activeOnly?: boolean)` (GET `/api/v1/simulations/twins?workspace_id=...&is_active=true`)
- [X] T011 [P] Create `apps/web/lib/hooks/use-isolation-policies.ts` exporting `useIsolationPolicies(workspaceId: string)` (GET `/api/v1/simulations/isolation-policies?workspace_id=...`)
- [X] T012 [P] Create `apps/web/lib/hooks/use-simulation-comparison.ts` exporting `useSimulationComparison(reportId: string | null)` (GET `/api/v1/simulations/comparisons/{reportId}`) with `enabled: Boolean(reportId)` and `refetchInterval` stopping on terminal statuses: `"completed" | "failed"`
- [X] T013 [P] Create `apps/web/lib/hooks/use-simulation-mutations.ts` exporting `useSimulationMutations()` returning: `createRun` (POST `/api/v1/simulations/`), `cancelRun` (POST `/api/v1/simulations/{runId}/cancel`), `createComparison` (POST `/api/v1/simulations/{runId}/compare`); each invalidates relevant `simQueryKeys` on success
- [X] T014 Create `apps/web/app/(main)/evaluation-testing/layout.tsx` with two-tab navigation: "Eval Suites" (links to `/evaluation-testing`) and "Simulations" (links to `/evaluation-testing/simulations`); tab active state driven by `usePathname()` prefix matching; renders `{children}` below tabs
- [X] T015 [P] Create all 8 page stubs under `apps/web/app/(main)/evaluation-testing/` each returning a `<div>` placeholder with page title: `new/page.tsx` ("Create Eval Suite"), `compare/page.tsx` ("Eval Comparison"), `[evalSetId]/page.tsx` ("Eval Suite Detail"), `[evalSetId]/runs/[runId]/page.tsx` ("Run Detail"), `simulations/page.tsx` ("Simulations"), `simulations/new/page.tsx` ("Create Simulation"), `simulations/compare/page.tsx` ("Simulation Comparison"), `simulations/[runId]/page.tsx` ("Simulation Detail"); update `apps/web/app/(main)/evaluation-testing/page.tsx` stub with title "Eval Suites"

**Checkpoint**: Navigate to `/evaluation-testing` — tabs render, all paths resolve without 404, TypeScript compiles.

---

## Phase 3: Eval Suite Browsing (US1, Priority: P1) 🎯 MVP

**Goal**: Operators can browse eval suites, view run history, and inspect per-case verdicts with score histogram.

**Independent Test**: With MSW handlers from quickstart.md US1 — DataTable renders "KYC Agent Quality" row, status filter works, clicking suite shows run list, selecting run shows verdicts table and histogram, aggregate metrics display Total 20 / Passed 17 / Failed 2 / Avg 85%, error verdict "v-2" shows expanded error detail.

- [X] T016 [P] [US1] Create `apps/web/components/features/eval/EvalSuiteDataTable.tsx` implementing `EvalSuiteDataTableProps` interface; reuses shared `DataTable` component with columns: Name (link to `[evalSetId]`), Target Agent (`agent_fqn` from last run or "—"), Last Run Date (formatted with `date-fns`), Last Score (`aggregate_score` as `%` or "—"), Status (`StatusBadge`); shadcn `Input` for search and shadcn `Select` for status filter ("all" | "active" | "archived"); loading skeleton; `EmptyState` with "Create Eval Suite" CTA when no suites
- [X] T017 [P] [US1] Create `apps/web/components/features/eval/AggregateMetrics.tsx` implementing `AggregateMetricsProps`; renders 4 `MetricCard` components: Total Cases (`total_cases`), Passed (`passed_cases`, green), Failed (`failed_cases`, red), Average Score (`aggregate_score` as `%` or "—"); handles `null` aggregate_score gracefully
- [X] T018 [P] [US1] Create `apps/web/components/features/eval/ScoreHistogram.tsx` implementing `ScoreHistogramProps`; computes 10 equal-width bins [0.0, 0.1, …, 1.0] client-side from `verdicts` array (skip verdicts with `overall_score === null`); renders Recharts `BarChart` with `Bar`, `XAxis` (bin labels "0.0–0.1"), `YAxis`, `Tooltip`; shows "No scores available" `EmptyState` when all scores are null; `height` prop with default 200
- [X] T019 [P] [US1] Create `apps/web/components/features/eval/VerdictTable.tsx` implementing `VerdictTableProps`; reuses shared `DataTable` with columns: Case (lookup `input_data` or `category` from `cases` by `benchmark_case_id`, truncate at 60 chars), Expected Output (truncate at 80 chars), Actual Output (truncate at 80 chars + expand `Button`), Score (`overall_score` as `%` or "—"), Pass/Fail (`Badge` green/red/gray), Status (`StatusBadge`; error variant for `status: "error"`); expand button reveals full actual_output + error_detail in `Collapsible`; pagination controls
- [X] T020 [P] [US1] Create `apps/web/components/features/eval/EvalRunList.tsx` implementing `EvalRunListProps`; renders list of run rows using shadcn `Card` or table rows; each row shows: run ID (truncated), status (`StatusBadge`), score (`aggregate_score` as `%`), date (`format(started_at, 'MMM d, yyyy HH:mm')` from date-fns), total/passed/failed counts; row click calls `onRunSelect`; selected row highlighted; loading skeleton while data fetches
- [X] T021 [US1] Create `apps/web/components/features/eval/EvalRunDetail.tsx` implementing `EvalRunDetailProps`; conditionally renders: `AggregateMetrics` always; when `run.status === "completed"`: `VerdictTable` + `ScoreHistogram` (verdicts passed as prop from parent); when `run.status === "pending" | "running"`: `Progress` indicator with status text "Evaluation in progress…"; when `run.status === "failed"`: `Alert` variant="destructive" showing `error_detail`
- [X] T022 [US1] Implement `apps/web/app/(main)/evaluation-testing/page.tsx` (replace stub); owns `useEvalSets(workspaceId, filters)` with local `filters` state; renders `EvalSuiteDataTable` with `onRowClick` navigating to `/evaluation-testing/{evalSetId}`; "Create Eval Suite" `Button` navigating to `/evaluation-testing/new`; gets `workspaceId` from Zustand workspace store
- [X] T023 [US1] Implement `apps/web/app/(main)/evaluation-testing/[evalSetId]/page.tsx` (replace stub); owns `useEvalSet(evalSetId)` + `useEvalRuns(workspaceId, evalSetId)`; renders suite name/description/pass_threshold metadata at top; `EvalRunList` below with `onRunSelect` navigating to `/evaluation-testing/{evalSetId}/runs/{runId}`; placeholder "Run Evaluation" `Button` (wired in US2); placeholder "Generate Adversarial Tests" `Button` (wired in US3)
- [X] T024 [US1] Implement `apps/web/app/(main)/evaluation-testing/[evalSetId]/runs/[runId]/page.tsx` (replace stub); owns `useEvalRun(runId)` + `useEvalRunVerdicts(runId)` + `useEvalSetCases(evalSetId)`; renders breadcrumb back to suite; renders `EvalRunDetail` passing `run`, `verdicts`, `cases`; breadcrumb: "Eval Suites → {suiteName} → Run {runId}"

**Checkpoint**: US1 fully functional with MSW handlers. DataTable, suite detail, run detail, verdicts, histogram all work.

---

## Phase 4: Create and Run Evaluations (US2, Priority: P1)

**Goal**: Operators can create an eval suite with test cases via a form, then trigger an eval run that auto-updates status.

**Independent Test**: With MSW handlers from quickstart.md US2 — empty name shows validation error, no test cases shows validation error, submit creates suite and navigates to detail, "Run Evaluation" shows pending → running → completed within 15s without manual refresh.

- [X] T025 [US2] Create `apps/web/components/features/eval/CreateEvalSuiteForm.tsx` implementing `CreateEvalSuiteFormProps`; React Hook Form with Zod schema: `name` (required, 1–255 chars), `description` (optional), `pass_threshold` (number 0–1, default 0.7), `cases` array (min 1 item) each with `input_prompt` (required) and `expected_output` (required, min 1 char); shadcn `Slider` for `pass_threshold`; `useFieldArray` for dynamic test cases with "Add Test Case" `Button` and remove `Button` per row; on submit calls `createEvalSet` then `addCase` for each case sequentially; calls `onSuccess(evalSetId)` on completion; shows `Alert` on API error
- [X] T026 [US2] Implement `apps/web/app/(main)/evaluation-testing/new/page.tsx` (replace stub); renders `CreateEvalSuiteForm`; `onSuccess` navigates to `/evaluation-testing/{evalSetId}`; back link to `/evaluation-testing`
- [X] T027 [US2] Wire "Run Evaluation" button on `apps/web/app/(main)/evaluation-testing/[evalSetId]/page.tsx`; replace placeholder with shadcn `Popover` triggered by `Button`; popover contains an `Input` for `agentFqn` (pre-filled from suite's last run `agent_fqn` if available), a confirm `Button`; on confirm calls `useEvalMutations().runEval({ evalSetId, agentFqn })`; on success appends new run to `EvalRunList` (query invalidation handles this); `useEvalRun` polling activates automatically for pending/running status

**Checkpoint**: US2 functional. Form validates, creates suite+cases, run triggers and status auto-updates.

---

## Phase 5: Adversarial Test Generation (US3, Priority: P2)

**Goal**: Operators can auto-generate adversarial test cases from the backend ATE system and review them before adding to the suite.

**Independent Test**: With MSW handlers from quickstart.md US3 — modal opens with spinner during ATE run, generated cases appear in review list, accept/edit/discard each work, accepted cases added to suite; with `items: []` ATE config, button is disabled with tooltip.

- [X] T028 [US3] Create `apps/web/components/features/eval/AdversarialTestReviewModal.tsx`; props: `{ evalSetId: string; agentFqn: string; onClose: () => void }`; shadcn `Dialog`; on open calls `useAteConfigs(workspaceId)`; if no configs: renders "No ATE configuration found. An admin must set this up." with disabled "Generate" `Button`; if configs found: "Generate" `Button` calls `useEvalMutations().runAte({ ateConfigId: configs[0].id, agentFqn })`, stores returned `ateRunId` in local state; `useAteRun(ateRunId)` polls; shows `Loader2` spinner and status text while `status === "pending" | "running"`; when `status === "pre_check_failed"`: renders `Alert` with `pre_check_errors` list; when `status === "completed"`: maps `report.generated_cases` to local `ATEGeneratedCase[]` state with `accepted: null`; renders review list — each case shows: `input_prompt`, `expected_behavior`, `category` `Badge`; per-row Accept `Button` (sets `accepted: true`), Discard `Button` (removes from list), Edit `Button` (toggles inline editable `Input` fields); "Add Accepted Cases" `Button` disabled until ≥1 accepted; on click calls `addCase` for each accepted case, then `onClose()`
- [X] T029 [US3] Wire "Generate Adversarial Tests" button on `apps/web/app/(main)/evaluation-testing/[evalSetId]/page.tsx`; replace placeholder with `Button`; disabled when user lacks `workspace_admin` role and no ATE config exists (tooltip: "An admin must configure adversarial testing first"); on click opens `AdversarialTestReviewModal` with `evalSetId` and last run `agentFqn` (or prompt for FQN if none); on `onClose` refetches `useEvalSetCases`

**Checkpoint**: US3 functional. ATE flow works end-to-end. Accepted cases appear in suite cases list.

---

## Phase 6: Eval Run Comparison (US4, Priority: P2)

**Goal**: Operators can select two eval runs and compare them side-by-side with statistical analysis from the backend.

**Independent Test**: With MSW handlers from quickstart.md US4 — selecting 2 runs enables "Compare" button, navigating to compare page shows spinner, after completion shows metric deltas, winner indicator "Run B is better", paired verdicts table, unmatched cases sections.

- [X] T030 [US4] Create `apps/web/components/features/eval/EvalComparisonView.tsx` implementing `EvalComparisonViewProps`; owns `useAbExperiment(experimentId)` (polls until `"completed" | "failed"`); also fetches `useEvalRunVerdicts(runAId)` + `useEvalRunVerdicts(runBId)` in parallel; renders: 3 metric delta `Card` components (Average Score with delta, Pass Rate with delta, Total Cases) using directional arrows (`TrendingUp`/`TrendingDown` Lucide icons); winner `Badge` with variant per `winner` field (`"run_a"` → "Run A is better" info, `"run_b"` → "Run B is better" success, `"equivalent"` → "Equivalent" secondary); `p_value` and `effect_size` shown as sub-text; paired verdicts table: join both verdict lists by `benchmark_case_id` into `PairedVerdict[]`, columns: Case, Score A, Score B, Delta, Pass A, Pass B; "Unique to Run A" and "Unique to Run B" collapse sections for unmatched cases; spinner + "Comparing runs…" while experiment `status === "pending"`; `Alert` on `status === "failed"`
- [X] T031 [US4] Add run selection checkboxes to `apps/web/components/features/eval/EvalRunList.tsx`; each row gets a `Checkbox` (shadcn); selection state held in parent via `selectedRunId` (existing) extended to support multi-select — update `EvalRunListProps` to add `selectedRunIds?: Set<string>` and `onSelectionChange?: (ids: Set<string>) => void`; when exactly 2 runs are selected renders a "Compare" `Button` at top of list; clicking navigates to `/evaluation-testing/compare?runA={id1}&runB={id2}`
- [X] T032 [US4] Implement `apps/web/app/(main)/evaluation-testing/compare/page.tsx` (replace stub); reads `runA` and `runB` from `searchParams`; creates experiment on mount via `useEvalMutations().createExperiment({ runAId: runA, runBId: runB, name: \`Compare \${runA} vs \${runB}\` })`; stores returned `experimentId` in state; renders `EvalComparisonView` with `experimentId`, `runAId`, `runBId`; shows skeleton while experiment is being created; back link to `/evaluation-testing`

**Checkpoint**: US4 functional. Two runs selectable, compare page shows statistical results.

---

## Phase 7: Simulation Management (US5, Priority: P2)

**Goal**: Operators can list, create, and cancel simulation runs; view detail with SIMULATION badge and status polling.

**Independent Test**: With MSW handlers from quickstart.md US5 — DataTable renders "KYC Load Test", create form twin multi-select shows "finance:kyc v1", form with warning flags shows Alert, launch creates simulation, detail shows amber SIMULATION badge, status polls provisioning → running → completed, cancel button shows ConfirmDialog and cancels.

- [X] T033 [P] [US5] Create `apps/web/components/features/simulations/SimulationRunDataTable.tsx` implementing `SimulationRunDataTableProps`; reuses shared `DataTable`; columns: Name, Status (`StatusBadge` with amber for `"provisioning"`, blue for `"running"`, green for `"completed"`, red for `"failed" | "timeout"`, gray for `"cancelled"`), Digital Twin(s) (count of `digital_twin_ids` or FQN if count=1), Completion Date (formatted with date-fns or "—"); row `Checkbox` for comparison selection via `onSelectionChange`; "Load More" `Button` shown when `nextCursor !== null`; loading skeleton; `EmptyState` with "Create Simulation" CTA; "Compare" `Button` enabled when exactly 2 rows selected
- [X] T034 [US5] Create `apps/web/components/features/simulations/CreateSimulationForm.tsx` implementing `CreateSimulationFormProps`; React Hook Form + Zod schema: `name` (required), `description` (optional), `digital_twin_ids` (string array, min 1), `isolation_policy_id` (optional string), `scenario_config.duration_seconds` (positive number, optional); digital twin multi-select: shadcn `Popover` + `Command` — `useDigitalTwins(workspaceId, true)` fetches active-only twins; each option shows `source_agent_fqn` + `v{version}` + warning flag `Badge` chips; when any selected twin has `warning_flags.length > 0` renders shadcn `Alert` variant="warning" above the form; isolation policy `Select` populated from `useIsolationPolicies(workspaceId)` with default option = policy where `is_default === true`; `scenario_config` additional fields as key-value rows (add/remove); on submit calls `useSimulationMutations().createRun`; calls `onSuccess(runId)` on completion
- [X] T035 [US5] Create `apps/web/components/features/simulations/SimulationDetailView.tsx` implementing `SimulationDetailViewProps`; amber SIMULATION `Badge` (`bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200`) in page header alongside run name; status `Badge` with `aria-busy` when `"provisioning" | "running"`; `run.results` displayed via shared `JsonViewer` component when `status === "completed"`; digital twins `Accordion` — each twin: `source_agent_fqn`, `version`, `modifications` count, `warning_flags` chips; "Cancel" `Button` variant="destructive" only shown when `status === "provisioning" | "running"` — triggers `ConfirmDialog` ("Cancel this simulation? This cannot be undone.") then calls `cancelRun(runId)`; "Compare with Production" `Button` (wired in US6) — placeholder here; "Compare with Other Simulation" `Button` placeholder (wired in US6); shows `Alert` for `status === "timeout"` with text "Simulation timed out. Try re-running with a shorter duration."
- [X] T036 [US5] Implement `apps/web/app/(main)/evaluation-testing/simulations/page.tsx` (replace stub); owns `useSimulationRuns(workspaceId)`; renders `SimulationRunDataTable` with `onRowClick` navigating to `/evaluation-testing/simulations/{runId}`; "Create Simulation" `Button` navigating to `/evaluation-testing/simulations/new`; "Compare" button (from DataTable selection) navigates to `/evaluation-testing/simulations/compare?primary={id1}&secondary={id2}&type=simulation_vs_simulation` and calls `useSimulationMutations().createComparison`
- [X] T037 [US5] Implement `apps/web/app/(main)/evaluation-testing/simulations/new/page.tsx` (replace stub); renders `CreateSimulationForm`; `onSuccess` navigates to `/evaluation-testing/simulations/{runId}`; back link to `/evaluation-testing/simulations`
- [X] T038 [US5] Implement `apps/web/app/(main)/evaluation-testing/simulations/[runId]/page.tsx` (replace stub); owns `useSimulationRun(runId)` (polling active automatically) + `useDigitalTwins(workspaceId)`; passes `run` and `twins` to `SimulationDetailView`; back link to `/evaluation-testing/simulations`

**Checkpoint**: US5 functional. Simulation list, create, detail with SIMULATION badge, cancel all work.

---

## Phase 8: Simulation Comparison (US6, Priority: P3)

**Goal**: Operators can compare a simulation run against production metrics or against another simulation run.

**Independent Test**: With MSW handlers from quickstart.md US6 — "Compare with Production" opens baseline period form, submit creates comparison, spinner shows while pending, after completion metric table shows delta values with directional arrows, "Simulation is better" verdict badge; with `compatible: false` warning banner shows incompatibility reasons.

- [X] T039 [US6] Create `apps/web/components/features/simulations/SimulationComparisonView.tsx` implementing `SimulationComparisonViewProps`; two column header `Card`s (Primary = simulation, Secondary = production baseline or simulation 2) showing run names; metric differences `Table`: columns Metric, Primary, Secondary, Delta (with `+/-` prefix and color), Direction (`ArrowUpRight`/`ArrowDownRight`/`ArrowRight` Lucide icons colored green/red/gray); overall verdict `Badge` per `ComparisonVerdict`: `"primary_better"` → green "Primary is better", `"secondary_better"` → blue "Secondary is better", `"equivalent"` → gray "Equivalent", `"inconclusive"` → yellow "Inconclusive"; `Alert` variant="warning" when `compatible === false` listing `incompatibility_reasons`; loading skeleton when `report.status === "pending"`; `Alert` variant="destructive" when `report.status === "failed"`
- [X] T040 [US6] Wire "Compare with Production" button on `apps/web/components/features/simulations/SimulationDetailView.tsx`; replace placeholder with `Button`; on click opens shadcn `Popover` with baseline period form: 3 preset `Button`s ("Last 7 days", "Last 30 days", "Last 90 days") + optional custom date range (two shadcn `Input type="date"`); confirm `Button` calls `useSimulationMutations().createComparison({ primaryRunId: run.run_id, productionBaselinePeriod: selectedPeriod, comparisonType: "simulation_vs_production" })`; on success navigates to `/evaluation-testing/simulations/compare?primary={runId}&report={reportId}&type=simulation_vs_production`
- [X] T041 [US6] Wire simulation vs simulation comparison flow: update `apps/web/app/(main)/evaluation-testing/simulations/page.tsx` so that when 2 runs are selected and "Compare" clicked, it calls `createComparison({ primaryRunId: id1, secondaryRunId: id2, comparisonType: "simulation_vs_simulation" })` and navigates to `/evaluation-testing/simulations/compare?primary={id1}&secondary={id2}&report={reportId}&type=simulation_vs_simulation`
- [X] T042 [US6] Implement `apps/web/app/(main)/evaluation-testing/simulations/compare/page.tsx` (replace stub); reads URL params: `primary`, `secondary` (optional), `report`, `type`; owns `useSimulationComparison(report)` which polls; renders `SimulationComparisonView` with `report` and `type`; back link to `/evaluation-testing/simulations`

**Checkpoint**: US6 functional. Both simulation-vs-production and simulation-vs-simulation comparison flows work end-to-end.

---

## Phase 9: Polish and Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode verification, and responsive layout across all user stories.

- [X] T043 [P] Add accessibility attributes across all new components: `aria-label` on all icon-only `Button`s (run selection checkboxes, remove case buttons, expand/collapse buttons); `aria-busy="true"` on polling status indicators in `EvalRunDetail` and `SimulationDetailView`; `aria-label` on Recharts SVG wrapper in `ScoreHistogram` (e.g., "Score distribution histogram"); keyboard navigation for run selection in `EvalRunList` (Space to toggle, Enter to navigate); `role="status"` on `AggregateMetrics` container for screen reader announcement on data change
- [X] T044 [P] Verify dark mode rendering: SIMULATION badge uses `dark:bg-amber-900 dark:text-amber-200` in `SimulationDetailView`; `ScoreHistogram` bar fill uses CSS variable or `dark:` Tailwind variant instead of hardcoded hex; all status badge color variants in `SimulationRunDataTable` and `EvalRunList` use shadcn `Badge` variants (not hardcoded colors); metric delta directional arrows in `EvalComparisonView` and `SimulationComparisonView` use semantic Tailwind classes (`text-green-600 dark:text-green-400`, `text-red-600 dark:text-red-400`)
- [X] T045 [P] Verify responsive layout: `EvalSuiteDataTable` and `SimulationRunDataTable` get `overflow-x-auto` wrapper for horizontal scroll on `<768px`; `EvalComparisonView` metric cards stack vertically (`flex-col`) on `<768px` using Tailwind responsive prefix `md:flex-row`; `SimulationComparisonView` two-column header stacks vertically on mobile; `CreateEvalSuiteForm` test case rows stack label+input vertically on mobile; `CreateSimulationForm` twin multi-select popover width constrained on mobile

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (types) — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2 — can start immediately after
- **Phase 4 (US2)**: Depends on Phase 2 + T021-T024 (EvalRunDetail + [evalSetId]/page for run button wiring)
- **Phase 5 (US3)**: Depends on Phase 2 + T023 ([evalSetId]/page for button wiring) + T008 (useEvalMutations)
- **Phase 6 (US4)**: Depends on Phase 2 + T020 (EvalRunList for checkbox addition) + T008 (useEvalMutations for createExperiment)
- **Phase 7 (US5)**: Depends on Phase 2 — fully independent from US1-US4
- **Phase 8 (US6)**: Depends on Phase 7 (T035 SimulationDetailView, T036 simulations/page) + T013 (useSimulationMutations)
- **Phase 9 (Polish)**: Depends on all phases complete

### Parallel Opportunities

```bash
# Phase 1: Both type files in parallel
T001 evaluation.ts  |  T002 simulation.ts

# Phase 2: All 11 hooks in parallel
T003..T013 (each is a separate file, no inter-hook dependencies)
# After hooks: layout and stubs in parallel
T014 layout  |  T015 page stubs

# Phase 3: Core eval components in parallel
T016 EvalSuiteDataTable  |  T017 AggregateMetrics  |  T018 ScoreHistogram  |  T019 VerdictTable  |  T020 EvalRunList
# T021 EvalRunDetail depends on T017+T018+T019+T020

# Phase 7: DataTable independently parallelizable
T033 SimulationRunDataTable  (parallel with T034, T035 which are independent of each other)

# Phase 9: All polish tasks in parallel
T043 accessibility  |  T044 dark mode  |  T045 responsive
```

---

## Implementation Strategy

### MVP (US1 + US2 Only — Phases 1–4)

1. Complete Phase 1: Type definitions
2. Complete Phase 2: Hooks + route shell
3. Complete Phase 3 (US1): Eval suite browsing — **validate with quickstart.md US1**
4. Complete Phase 4 (US2): Create + run evaluations — **validate with quickstart.md US2**
5. **STOP and VALIDATE**: Core eval workflow end-to-end
6. Ship MVP: operators can manage eval suites and view results

### Full Feature (All 6 User Stories)

1. Foundation (Phases 1–2) → MVP (Phases 3–4) → adversarial gen (Phase 5) → comparison (Phase 6) → simulations (Phase 7) → sim comparison (Phase 8) → polish (Phase 9)
2. Each phase adds independently testable value
3. US5 (simulations) can be developed in parallel with US3+US4 (different files, different domain)

---

## Notes

- [P] = different files, no inter-task dependencies — safe to parallelize
- [US1]...[US6] label maps each task to the user story for delivery traceability
- Phase 2 is the critical bottleneck — all hooks must exist before any component can consume them
- `evalQueryKeys` (T001) and `simQueryKeys` (T002) must exist before hooks (T003–T013)
- US3 (ATE modal) and US4 (comparison view) reuse `useEvalMutations` from T008 — no duplication
- US5+US6 are fully independent of US1–US4 (separate domain, separate components, separate hooks)
