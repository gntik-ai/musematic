# UI Component Contracts: Evaluation and Testing UI

**Feature**: 050-evaluation-testing-ui  
**Phase**: 1 — Design  
**Date**: 2026-04-18

---

## Evaluation Hooks (`lib/hooks/use-eval-*.ts`)

### `useEvalSets`
```typescript
function useEvalSets(
  workspaceId: string,
  filters: EvalListFilters,
): UseQueryResult<EvalSetListResponse, Error>
// GET /api/v1/evaluations/eval-sets?status=...&page=...
// staleTime: 30_000
```

### `useEvalSet`
```typescript
function useEvalSet(evalSetId: string): UseQueryResult<EvalSetResponse, Error>
// GET /api/v1/evaluations/eval-sets/{evalSetId}
```

### `useEvalSetCases`
```typescript
function useEvalSetCases(
  evalSetId: string,
  page?: number,
): UseQueryResult<BenchmarkCaseListResponse, Error>
// GET /api/v1/evaluations/eval-sets/{evalSetId}/cases
```

### `useEvalRuns`
```typescript
function useEvalRuns(
  workspaceId: string,
  evalSetId?: string,
): UseQueryResult<EvaluationRunListResponse, Error>
// GET /api/v1/evaluations/runs?eval_set_id=...
```

### `useEvalRun`
```typescript
function useEvalRun(runId: string): UseQueryResult<EvaluationRunResponse, Error>
// GET /api/v1/evaluations/runs/{runId}
// refetchInterval: terminal status → false, otherwise 3000ms
```

### `useEvalRunVerdicts`
```typescript
function useEvalRunVerdicts(
  runId: string,
  page?: number,
): UseQueryResult<JudgeVerdictListResponse, Error>
// GET /api/v1/evaluations/runs/{runId}/verdicts
```

### `useAbExperiment`
```typescript
function useAbExperiment(
  experimentId: string | null,
): UseQueryResult<AbExperimentResponse, Error>
// GET /api/v1/evaluations/experiments/{experimentId}
// refetchInterval: terminal status → false, otherwise 3000ms
// enabled: Boolean(experimentId)
```

### `useAteConfigs`
```typescript
function useAteConfigs(workspaceId: string): UseQueryResult<ATEConfigListResponse, Error>
// GET /api/v1/evaluations/ate
```

### `useAteRun`
```typescript
function useAteRun(ateRunId: string | null): UseQueryResult<ATERunResponse, Error>
// GET /api/v1/evaluations/ate/runs/{ateRunId}
// refetchInterval: terminal status → false, otherwise 3000ms
// enabled: Boolean(ateRunId)
```

### `useEvalMutations`
```typescript
function useEvalMutations(): {
  createEvalSet: UseMutationResult<EvalSetResponse, Error, EvalSetCreateInput>;
  addCase: UseMutationResult<BenchmarkCaseResponse, Error, { evalSetId: string; payload: BenchmarkCaseCreateInput }>;
  runEval: UseMutationResult<EvaluationRunResponse, Error, { evalSetId: string; agentFqn: string }>;
  createExperiment: UseMutationResult<AbExperimentResponse, Error, { runAId: string; runBId: string; name: string }>;
  runAte: UseMutationResult<ATERunResponse, Error, { ateConfigId: string; agentFqn: string }>;
}
// Each mutation POSTs to the corresponding endpoint
```

---

## Simulation Hooks (`lib/hooks/use-simulation-*.ts`)

### `useSimulationRuns`
```typescript
function useSimulationRuns(
  workspaceId: string,
  cursor?: string,
): UseQueryResult<SimulationRunListResponse, Error>
// GET /api/v1/simulations/?workspace_id=...&cursor=...
```

### `useSimulationRun`
```typescript
function useSimulationRun(runId: string): UseQueryResult<SimulationRunResponse, Error>
// GET /api/v1/simulations/{runId}
// refetchInterval: terminal status → false, otherwise 3000ms
```

### `useDigitalTwins`
```typescript
function useDigitalTwins(
  workspaceId: string,
  activeOnly?: boolean,
): UseQueryResult<DigitalTwinListResponse, Error>
// GET /api/v1/simulations/twins?workspace_id=...&is_active=true
```

### `useIsolationPolicies`
```typescript
function useIsolationPolicies(
  workspaceId: string,
): UseQueryResult<SimulationIsolationPolicyListResponse, Error>
// GET /api/v1/simulations/isolation-policies?workspace_id=...
```

### `useSimulationComparison`
```typescript
function useSimulationComparison(
  reportId: string | null,
): UseQueryResult<SimulationComparisonReportResponse, Error>
// GET /api/v1/simulations/comparisons/{reportId}
// refetchInterval: terminal status → false, otherwise 3000ms
// enabled: Boolean(reportId)
```

### `useSimulationMutations`
```typescript
function useSimulationMutations(): {
  createRun: UseMutationResult<SimulationRunResponse, Error, SimulationRunCreateInput>;
  cancelRun: UseMutationResult<SimulationRunResponse, Error, string>;
  createComparison: UseMutationResult<SimulationComparisonReportResponse, Error, SimulationComparisonCreateInput>;
}
```

---

## Page Components

### `EvaluationTestingLayout`
**File**: `apps/web/app/(main)/evaluation-testing/layout.tsx`
- Two-tab navigation: "Eval Suites" and "Simulations"
- Tab active state driven by URL path prefix

### `EvalSuitesPage`
**File**: `apps/web/app/(main)/evaluation-testing/page.tsx`
- Renders `EvalSuiteDataTable` + "Create Eval Suite" button (navigates to `/evaluation-testing/new`)
- Owns `useEvalSets` with filter state

### `CreateEvalSuitePage`
**File**: `apps/web/app/(main)/evaluation-testing/new/page.tsx`
- Full-page form for creating eval suite + initial test cases

### `EvalSuiteDetailPage`
**File**: `apps/web/app/(main)/evaluation-testing/[evalSetId]/page.tsx`
- Suite metadata + run list + "Run Evaluation" button + "Generate Adversarial Tests" button

### `EvalRunDetailPage`
**File**: `apps/web/app/(main)/evaluation-testing/[evalSetId]/runs/[runId]/page.tsx`
- Verdicts table + aggregate metrics + score histogram

### `EvalComparePage`
**File**: `apps/web/app/(main)/evaluation-testing/compare/page.tsx`
- Reads `?runA=...&runB=...` from URL params
- Owns `useAbExperiment` for statistical comparison

### `SimulationsPage`
**File**: `apps/web/app/(main)/evaluation-testing/simulations/page.tsx`
- Renders `SimulationRunDataTable` + "Create Simulation" button

### `CreateSimulationPage`
**File**: `apps/web/app/(main)/evaluation-testing/simulations/new/page.tsx`
- Full-page form for creating simulation run

### `SimulationDetailPage`
**File**: `apps/web/app/(main)/evaluation-testing/simulations/[runId]/page.tsx`
- Simulation result view with SIMULATION badge + "Compare with Production" button

### `SimulationComparePage`
**File**: `apps/web/app/(main)/evaluation-testing/simulations/compare/page.tsx`
- Reads `?primary=...&secondary=...&type=...` from URL params
- Owns `useSimulationComparison`

---

## Section Components

### `EvalSuiteDataTable`
**File**: `components/features/eval/EvalSuiteDataTable.tsx`
```typescript
interface EvalSuiteDataTableProps {
  evalSets: EvalSetResponse[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
  onRowClick: (evalSetId: string) => void;
}
```
Columns: Name, Target Agent (last run `agent_fqn` or "—"), Last Run Date, Last Score (`aggregate_score` formatted as %), Status badge

### `EvalRunList`
**File**: `components/features/eval/EvalRunList.tsx`
```typescript
interface EvalRunListProps {
  runs: EvaluationRunResponse[];
  evalSetId: string;
  onRunSelect: (runId: string) => void;
  selectedRunId?: string;
}
```

### `EvalRunDetail`
**File**: `components/features/eval/EvalRunDetail.tsx`
```typescript
interface EvalRunDetailProps {
  run: EvaluationRunResponse;
}
// Renders aggregate metrics + conditionally: verdicts table + histogram (when complete)
// or: progress indicator (when pending/running)
// or: error detail (when failed)
```

### `VerdictTable`
**File**: `components/features/eval/VerdictTable.tsx`
```typescript
interface VerdictTableProps {
  verdicts: JudgeVerdictResponse[];
  cases: BenchmarkCaseResponse[];   // for case name lookup by benchmark_case_id
  total: number;
  page: number;
  onPageChange: (page: number) => void;
}
```
Columns: Case (input_data summary or category), Expected Output (truncated), Actual Output (truncated + expand), Score, Pass/Fail badge, Status badge (error variant)

### `ScoreHistogram`
**File**: `components/features/eval/ScoreHistogram.tsx`
```typescript
interface ScoreHistogramProps {
  verdicts: JudgeVerdictResponse[];
  height?: number;
}
```
Computes 10 bins client-side; renders Recharts `BarChart`; "No scores available" empty state when all null

### `AggregateMetrics`
**File**: `components/features/eval/AggregateMetrics.tsx`
```typescript
interface AggregateMetricsProps {
  run: EvaluationRunResponse;
}
```
Renders 4 MetricCards: Total Cases, Passed, Failed, Average Score

### `CreateEvalSuiteForm`
**File**: `components/features/eval/CreateEvalSuiteForm.tsx`
```typescript
interface CreateEvalSuiteFormProps {
  onSuccess: (evalSetId: string) => void;
}
```
React Hook Form + Zod; name, description, pass_threshold (slider 0–1); dynamic test case array (add/remove rows); scorer config (simplified: pass threshold only for MVP, full scorer_config as JSON editor for advanced users)

### `AdversarialTestReviewModal`
**File**: `components/features/eval/AdversarialTestReviewModal.tsx`
```typescript
interface AdversarialTestReviewModalProps {
  ateRunId: string | null;
  onAccept: (cases: ATEGeneratedCase[]) => void;
  onClose: () => void;
}
```
shadcn `Dialog`; polls `useAteRun`; shows progress spinner while running; lists generated cases with Accept/Edit/Discard per row; "Add Accepted Cases" submit button

### `EvalComparisonView`
**File**: `components/features/eval/EvalComparisonView.tsx`
```typescript
interface EvalComparisonViewProps {
  experimentId: string;
  runAId: string;
  runBId: string;
}
```
Metric delta cards (score, pass rate, total cases) + paired verdicts table + overall winner indicator

### `SimulationRunDataTable`
**File**: `components/features/simulations/SimulationRunDataTable.tsx`
```typescript
interface SimulationRunDataTableProps {
  runs: SimulationRunResponse[];
  nextCursor: string | null;
  onLoadMore: () => void;
  onRowClick: (runId: string) => void;
  selectedRunIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
}
```
Columns: Name, Status badge, Digital Twin(s) (count or FQN), Completion Date; row checkbox for comparison selection

### `CreateSimulationForm`
**File**: `components/features/simulations/CreateSimulationForm.tsx`
```typescript
interface CreateSimulationFormProps {
  onSuccess: (runId: string) => void;
}
```
React Hook Form + Zod; name, description, digital twin multi-select (with warning flags), scenario config (key-value editor for `duration_seconds` + optional fields), isolation policy dropdown (default = workspace default policy)

### `SimulationDetailView`
**File**: `components/features/simulations/SimulationDetailView.tsx`
```typescript
interface SimulationDetailViewProps {
  run: SimulationRunResponse;
  twins: DigitalTwinResponse[];
}
```
SIMULATION badge + status indicator + progress while active + results display + twin details accordion + "Compare with Production" / "Cancel" buttons

### `SimulationComparisonView`
**File**: `components/features/simulations/SimulationComparisonView.tsx`
```typescript
interface SimulationComparisonViewProps {
  report: SimulationComparisonReportResponse;
  type: ComparisonType;
}
```
Side-by-side metric cards with delta + directional arrows + overall verdict badge + incompatibility warnings + metric difference table

---

## State Transitions

### Eval Run Status Flow
```
pending → running → completed (verdicts available)
                 → failed (error_detail shown)
```

### ATE Run Review Flow
```
User clicks "Generate Adversarial Tests"
  → POST /ate/{ate_config_id}/run/{agent_fqn} → ATERunResponse (status: "pending")
  → AdversarialTestReviewModal opens, polls useAteRun
  → status: "running" → spinner
  → status: "completed" → review list from report.generated_cases
  → User accepts/edits/discards cases
  → Accepted cases POSTed via addCase mutation to eval-set
  → Modal closes
  → status: "pre_check_failed" → pre_check_errors displayed, no review list
```

### Simulation Comparison Flow
```
User clicks "Compare with Production" on SimulationDetailPage
  → Form: select baseline period (7d/30d/custom)
  → POST /simulations/{run_id}/compare → SimulationComparisonReportResponse (status: "pending")
  → Navigate to /evaluation-testing/simulations/compare?primary={run_id}&report={report_id}
  → SimulationComparePage polls useSimulationComparison
  → status: "completed" → SimulationComparisonView renders
```
