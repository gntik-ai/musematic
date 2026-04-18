# Research: Evaluation and Testing UI

**Feature**: 050-evaluation-testing-ui  
**Phase**: 0 — Research  
**Date**: 2026-04-18

## Decision 1: Route Structure

**Decision**: Single route group `app/(main)/evaluation-testing/` covering both evaluation and simulation domains. Sub-routes:

```
/evaluation-testing                      → Eval suites list (US1)
/evaluation-testing/new                  → Create eval suite (US2)
/evaluation-testing/[evalSetId]          → Eval suite detail + run list (US1)
/evaluation-testing/[evalSetId]/runs/[runId]  → Run detail with verdicts + histogram (US1)
/evaluation-testing/compare              → Eval run A/B comparison (US4)
/evaluation-testing/simulations          → Simulation runs list (US5)
/evaluation-testing/simulations/new      → Create simulation (US5)
/evaluation-testing/simulations/[runId]  → Simulation run detail (US5)
/evaluation-testing/simulations/compare  → Simulation vs production comparison (US6)
```

**Rationale**: Evaluation and simulation are both quality/safety tooling for agents — grouping them under one route keeps navigation clear. The spec covers both domains and the user mental model is "testing" broadly. Separate sub-paths for the two domains avoid confusion.

**Alternatives considered**:
- Separate top-level routes (`/evaluation` and `/simulations`): Would require two sidebar entries and duplicated layout work. Unified route group is one feature delivery.

---

## Decision 2: Async Status Polling

**Decision**: TanStack Query `refetchInterval` on in-progress runs. While a run's `status` is `"pending"` or `"running"`, set `refetchInterval: 3000` (3s). When status reaches a terminal state (`"completed"`, `"failed"`, `"timeout"`, `"cancelled"`), set `refetchInterval: false` to stop polling.

```typescript
useQuery({
  queryKey: evalRunQueryKeys.run(runId),
  queryFn: () => evalApi.get(`/runs/${runId}`),
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    return status && ["completed", "failed"].includes(status) ? false : 3000;
  },
})
```

**Rationale**: No WebSocket channel exists specifically for evaluation/simulation status events (the `evaluation.events` Kafka topic exists but the WS hub supports an `evaluation` channel — checking if that's wired is a stretch goal). Polling at 3s is the safest default and matches the spec's "within 5 seconds" SC-006 requirement. This pattern is already used in `use-execution-monitor.ts`.

**Alternatives considered**:
- WebSocket via existing `ws-hub` evaluation channel: Optimal but requires verifying that the WS hub routes `evaluation.events` to a connected frontend. Polling is the safe default.
- Manual refresh button only: Does not meet SC-006.

---

## Decision 3: Eval Run Comparison (A/B Experiment vs Frontend)

**Decision**: Use the backend `POST /api/v1/evaluations/experiments` endpoint (`AbExperimentCreate` → `AbExperimentResponse`), which runs statistical analysis (p-value, effect size, confidence interval, winner determination) asynchronously. The comparison view polls `GET /api/v1/evaluations/experiments/{experiment_id}` until status is `"completed"`, then displays the structured results.

**Rationale**: The backend already implements a statistically correct A/B comparison engine. The frontend comparison view is primarily a display layer for the `AbExperimentResponse`. Frontend-only comparison would require re-implementing the statistical analysis and would be less accurate.

The comparison UI shows: metric deltas from the experiment's `confidence_interval`, `effect_size`, and `winner` fields. The paired verdict table is built client-side by matching `benchmark_case_id` across the two `JudgeVerdictListResponse` payloads (fetched independently for each run).

**Alternatives considered**:
- Frontend-only matching: Simpler but no statistical significance — operators cannot tell if differences are meaningful noise or real changes. Backend experiment is the right tool.

---

## Decision 4: Adversarial Generation UX Flow

**Decision**: The adversarial generation button in the eval suite detail page triggers `POST /api/v1/evaluations/ate/{ate_config_id}/run/{agent_fqn}` using the workspace's default ATE config (the first active config in the workspace). The ATE run result includes a `report` dict that contains the generated cases. The frontend polls `GET /api/v1/evaluations/ate/runs/{ate_run_id}` until completion, then presents the `report.generated_cases` (or equivalent key in the ATE report JSON) in a review modal.

The create flow for the ATE config itself is admin-only (workspace_admin+), so non-admin users see a disabled "Generate Adversarial Tests" button if no ATE config exists, with a tooltip "An admin must configure adversarial testing first."

**Rationale**: The ATE config model separates the configuration from the execution. The frontend treats the existing workspace ATE config as a given, rather than creating one per suite. This matches how a typical operator would use it: admins configure ATE once, operators trigger runs per suite/agent.

**Alternatives considered**:
- Inline ATE config creation in the eval form: Would expose complex config fields (scenarios, safety checks) to all users. Admin-gated config is cleaner.

---

## Decision 5: Score Histogram Client-Side Computation

**Decision**: The score histogram is computed entirely client-side. From `JudgeVerdictListResponse.items`, extract all `overall_score` values (skip nulls), bin them into 10 equal-width buckets from 0.0 to 1.0, and render a Recharts `BarChart`. The bin edges are `[0, 0.1, 0.2, …, 1.0]`.

**Rationale**: The backend has no histogram endpoint. All verdict scores for a run are already fetched for the verdicts table. Computing the histogram from in-memory data is trivial and avoids a round-trip. Recharts BarChart is the standard chart component for this.

---

## Decision 6: Component Organization

**Decision**:
```
components/features/eval/          # Evaluation domain components
components/features/simulations/   # Simulation domain components
```

Shared patterns:
- `EvalSuiteDataTable` and `SimulationRunDataTable` both use the existing `DataTable` shared component with custom column definitions
- Forms use React Hook Form + Zod following the admin settings form pattern

Hooks:
- `lib/hooks/use-eval-*.ts` prefix for evaluation hooks
- `lib/hooks/use-simulation-*.ts` prefix for simulation hooks

Types:
- `types/evaluation.ts` — all evaluation TypeScript types
- `types/simulation.ts` — all simulation TypeScript types

**Rationale**: Two separate feature directories (not one `evaluation-testing/`) because the domains have different entities, hooks, and forms. Merging them would create an oversized directory. Consistent with how `fleet` and `marketplace` have separate directories despite being on the same conceptual "operational" tier.

---

## Decision 7: Digital Twin Multi-Select in Create Simulation Form

**Decision**: `digital_twin_ids` in `SimulationRunCreateRequest` is `list[UUID]` (min 1). The form uses a shadcn multi-select pattern built with a `Popover` + `Command` (the same pattern used in the policy attachment panel). Only active twins are fetched from `GET /api/v1/simulations/twins?is_active=true`. Each twin shows its source agent FQN and version. Warning flags on a selected twin are shown as inline warning badges.

**Rationale**: Multi-select is needed because `digital_twin_ids` accepts multiple values. The shadcn `Command` in a `Popover` is the established pattern in this codebase (seen in policy attachment). Showing warning flags inline ensures operators are informed before launch.

---

## Decision 8: Simulation Comparison Status Polling

**Decision**: After triggering `POST /api/v1/simulations/{run_id}/compare`, the response is a `SimulationComparisonReportResponse` with `status: "pending"`. Poll `GET /api/v1/simulations/comparisons/{report_id}` at 3s until `status` reaches `"completed"` or `"failed"`.

**Rationale**: Same polling pattern as eval runs (Decision 2). The comparison is computationally non-trivial (metric aggregation against production) so an async backend task is expected.

---

## Decision 9: SIMULATION Badge Implementation

**Decision**: A shadcn `Badge` with `variant="outline"` and a distinct amber/yellow color (Tailwind `bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200`), labeled "SIMULATION", is rendered prominently at the top of the simulation detail page header and next to any execution view that originates from a simulation. The badge is purely visual — no data transformation.

**Rationale**: The spec (FR-010) requires a "prominent SIMULATION badge". Using a shadcn `Badge` with the amber color palette distinguishes it clearly from production status badges (which use the standard green/red/gray palette) without introducing new design tokens.

---

## Decision 10: Evaluation API Prefix

**Decision**: All evaluation endpoints are at prefix `/api/v1/evaluations/`:
- Eval sets: `/api/v1/evaluations/eval-sets`
- Runs: `/api/v1/evaluations/runs`
- Verdicts: `/api/v1/evaluations/verdicts`
- Experiments: `/api/v1/evaluations/experiments`
- ATE configs: `/api/v1/evaluations/ate`

Simulation endpoints are at prefix `/api/v1/simulations/`:
- Runs: `/api/v1/simulations/`
- Twins: `/api/v1/simulations/twins`
- Comparisons: `/api/v1/simulations/comparisons`

**Rationale**: Confirmed from the backend router files (`apps/control-plane/src/platform/api/evaluations.py` uses `prefix="/api/v1/evaluations"` and `apps/control-plane/src/platform/simulation/router.py` uses `prefix="/api/v1/simulations"`).

---

## Decision 11: Query Key Structure

**Decision**: Two separate query key objects:

```typescript
// types/evaluation.ts
export const evalQueryKeys = {
  evalSets: (workspaceId: string, status?: string) => [...],
  evalSet: (evalSetId: string) => [...],
  cases: (evalSetId: string) => [...],
  runs: (workspaceId: string, evalSetId?: string) => [...],
  run: (runId: string) => [...],
  verdicts: (runId: string) => [...],
  experiment: (experimentId: string) => [...],
  ateConfigs: (workspaceId: string) => [...],
  ateRun: (ateRunId: string) => [...],
};

export const simQueryKeys = {
  runs: (workspaceId: string, cursor?: string) => [...],
  run: (runId: string) => [...],
  twins: (workspaceId: string) => [...],
  isolationPolicies: (workspaceId: string) => [...],
  comparison: (reportId: string) => [...],
};
```

**Rationale**: Separate objects avoid key collisions between the two domains and match existing patterns (`analyticsQueryKeys`, `workflowQueryKeys`).
