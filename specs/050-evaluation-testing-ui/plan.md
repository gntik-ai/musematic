# Implementation Plan: Evaluation and Testing UI

**Branch**: `050-evaluation-testing-ui` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/050-evaluation-testing-ui/spec.md`

## Summary

Build a full evaluation and simulation management interface under `app/(main)/evaluation-testing/`. The feature covers two domains: (1) eval suite management with run results, score histograms, adversarial test generation, and A/B run comparison; (2) simulation management with digital twin selection, execution views with a SIMULATION badge, and simulation-vs-production comparison. Frontend-only — data from evaluation API (feature 034) at `/api/v1/evaluations/` and simulation API (feature 040) at `/api/v1/simulations/`.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router  
**Primary Dependencies**: shadcn/ui, Tailwind CSS 3.4+, TanStack Query v5, React Hook Form 7.x + Zod 3.x, Recharts 2.x, date-fns 4.x  
**Storage**: N/A (frontend only)  
**Testing**: Vitest + React Testing Library + MSW  
**Target Platform**: Web (desktop primary, mobile responsive)  
**Project Type**: Web application (multi-page feature within existing Next.js app)  
**Performance Goals**: Status polling updates UI within 5s of backend state change (SC-006)  
**Constraints**: No new npm packages; Tailwind utility classes only  
**Scale/Scope**: 9 route pages, 13 components, 11 hooks, 2 type files

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Function components only | ✅ PASS | All components use function syntax |
| shadcn/ui for ALL UI primitives | ✅ PASS | No alternative component library |
| No custom CSS (Tailwind only) | ✅ PASS | No new CSS files |
| TanStack Query for server state | ✅ PASS | `refetchInterval` for polling; no useEffect+setState for data |
| Zustand for client-only state | ✅ PASS | No shared client state needed across pages (URL params + RHF local state used) |
| date-fns for date operations | ✅ PASS | For datetime formatting in tables and forms |
| React Hook Form + Zod for forms | ✅ PASS | Both create forms use RHF + Zod |

**Post-design re-check**: No violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/050-evaluation-testing-ui/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── ui-components.md # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
apps/web/
├── app/(main)/evaluation-testing/
│   ├── layout.tsx                              # Tab nav: Eval Suites | Simulations
│   ├── page.tsx                                # Eval suite list + search + filter
│   ├── new/page.tsx                            # Create eval suite form
│   ├── compare/page.tsx                        # Eval A/B comparison (reads ?runA=&runB=)
│   ├── [evalSetId]/page.tsx                    # Eval suite detail + run list
│   ├── [evalSetId]/runs/[runId]/page.tsx       # Run detail: verdicts + histogram
│   └── simulations/
│       ├── page.tsx                            # Simulation run list
│       ├── new/page.tsx                        # Create simulation form
│       ├── compare/page.tsx                    # Simulation comparison view
│       └── [runId]/page.tsx                   # Simulation detail + SIMULATION badge
│
├── components/features/eval/                   # NEW (9 components)
│   ├── EvalSuiteDataTable.tsx
│   ├── EvalRunList.tsx
│   ├── EvalRunDetail.tsx
│   ├── VerdictTable.tsx
│   ├── ScoreHistogram.tsx
│   ├── AggregateMetrics.tsx
│   ├── CreateEvalSuiteForm.tsx
│   ├── AdversarialTestReviewModal.tsx
│   └── EvalComparisonView.tsx
│
├── components/features/simulations/            # NEW (4 components)
│   ├── SimulationRunDataTable.tsx
│   ├── CreateSimulationForm.tsx
│   ├── SimulationDetailView.tsx
│   └── SimulationComparisonView.tsx
│
├── lib/hooks/
│   ├── use-eval-sets.ts                        # NEW
│   ├── use-eval-runs.ts                        # NEW
│   ├── use-eval-verdicts.ts                    # NEW
│   ├── use-ab-experiment.ts                    # NEW
│   ├── use-ate.ts                              # NEW
│   ├── use-eval-mutations.ts                   # NEW
│   ├── use-simulation-runs.ts                  # NEW
│   ├── use-digital-twins.ts                    # NEW
│   ├── use-isolation-policies.ts              # NEW
│   ├── use-simulation-comparison.ts           # NEW
│   └── use-simulation-mutations.ts            # NEW
│
└── types/
    ├── evaluation.ts                           # NEW
    └── simulation.ts                           # NEW
```

**Structure Decision**: Two separate feature directories (`eval/` and `simulations/`) under `components/features/` for the two domains, preventing oversized directories. Route pages live under a unified `evaluation-testing/` group for cohesive navigation.

## Implementation Phases

### Phase 1: Foundation (no UI)

Goal: TypeScript types and all 11 TanStack Query hooks. No pages or components yet.

**Files**:
- `apps/web/types/evaluation.ts` — all evaluation types (enums, EvalSetResponse, BenchmarkCaseResponse, EvaluationRunResponse, JudgeVerdictResponse, AbExperimentResponse, ATEConfigResponse, ATERunResponse, `evalQueryKeys`)
- `apps/web/types/simulation.ts` — all simulation types (SimulationRunResponse, DigitalTwinResponse, SimulationIsolationPolicyResponse, SimulationComparisonReportResponse, `simQueryKeys`)
- `apps/web/lib/hooks/use-eval-sets.ts` — `useEvalSets`
- `apps/web/lib/hooks/use-eval-runs.ts` — `useEvalRuns` + `useEvalRun` (with polling `refetchInterval`)
- `apps/web/lib/hooks/use-eval-verdicts.ts` — `useEvalSetCases` + `useEvalRunVerdicts`
- `apps/web/lib/hooks/use-ab-experiment.ts` — `useAbExperiment` (polling)
- `apps/web/lib/hooks/use-ate.ts` — `useAteConfigs` + `useAteRun` (polling)
- `apps/web/lib/hooks/use-eval-mutations.ts` — `useEvalMutations` (createEvalSet, addCase, runEval, createExperiment, runAte)
- `apps/web/lib/hooks/use-simulation-runs.ts` — `useSimulationRuns` + `useSimulationRun` (polling)
- `apps/web/lib/hooks/use-digital-twins.ts` — `useDigitalTwins`
- `apps/web/lib/hooks/use-isolation-policies.ts` — `useIsolationPolicies`
- `apps/web/lib/hooks/use-simulation-comparison.ts` — `useSimulationComparison` (polling)
- `apps/web/lib/hooks/use-simulation-mutations.ts` — `useSimulationMutations` (createRun, cancelRun, createComparison)

**Independent test**: All hook files compile. TS strict mode passes.

---

### Phase 2: Route Shell and Navigation

Goal: All 9 page stubs + layout with tab navigation.

**Files**:
- `apps/web/app/(main)/evaluation-testing/layout.tsx` — two-tab nav ("Eval Suites" / "Simulations") using shadcn `Tabs` or two shadcn `Button` links, highlighting active path; wraps child `{children}`
- All 9 `page.tsx` stubs returning `<div>` placeholders with page titles

**Independent test**: Navigate to `/evaluation-testing`. Tab renders and switches between `/evaluation-testing` and `/evaluation-testing/simulations`. No 404s.

---

### Phase 3: Eval Suite Browsing (US1)

Goal: Eval suite list with search/filter, suite detail with run list, run detail with verdicts + histogram + metrics.

**Files**:
- `components/features/eval/EvalSuiteDataTable.tsx` — reuses `DataTable` shared component; columns: Name, Agent, Last Run, Last Score, Status; search input (shadcn `Input`); status filter (shadcn `Select`); loading skeleton; empty state
- `components/features/eval/AggregateMetrics.tsx` — 4 `MetricCard`s: Total Cases, Passed, Failed, Average Score
- `components/features/eval/ScoreHistogram.tsx` — Recharts `BarChart`; 10 bins client-computed from `verdicts`; "No scores available" state
- `components/features/eval/VerdictTable.tsx` — reuses `DataTable`; columns: Case, Expected (truncated), Actual (truncated + expand button), Score, Pass/Fail, Status; error rows distinct; pagination
- `components/features/eval/EvalRunDetail.tsx` — renders `AggregateMetrics` + conditionally verdicts panel (when completed), progress indicator (when pending/running), error detail (when failed)
- `components/features/eval/EvalRunList.tsx` — list of run rows with status badge, score, date; selectable; loading skeleton
- `apps/web/app/(main)/evaluation-testing/page.tsx` — owns `useEvalSets`; renders `EvalSuiteDataTable`; "Create Eval Suite" button navigates to `/evaluation-testing/new`
- `apps/web/app/(main)/evaluation-testing/[evalSetId]/page.tsx` — owns `useEvalSet` + `useEvalRuns`; renders suite metadata + `EvalRunList`; "Run Evaluation" button (US2); "Generate Adversarial Tests" button (US3)
- `apps/web/app/(main)/evaluation-testing/[evalSetId]/runs/[runId]/page.tsx` — owns `useEvalRun` + `useEvalRunVerdicts` + `useEvalSetCases`; renders `EvalRunDetail` with verdicts and histogram; back navigation to suite

**Independent test**: MSW handlers from quickstart.md US1. DataTable renders, filters work, clicking suite navigates to detail, run selection shows verdicts, histogram bins computed correctly, error verdict shows expanded detail.

---

### Phase 4: Create and Run Evaluations (US2)

Goal: Eval suite creation form with dynamic test cases, scorer config, and run triggering.

**Files**:
- `components/features/eval/CreateEvalSuiteForm.tsx` — RHF + Zod; name (required), description, pass_threshold (shadcn `Slider` 0–1); dynamic test case array (shadcn `Button` "Add Case" → adds row with input_data prompt + expected_output textarea); case remove button; `useFieldArray` for dynamic rows; `useEvalMutations().createEvalSet` + `addCase` per case on submit; validation: name required, at least 1 case
- `apps/web/app/(main)/evaluation-testing/new/page.tsx` — renders `CreateEvalSuiteForm`; on success navigates to `[evalSetId]`
- Wire "Run Evaluation" button on `[evalSetId]/page.tsx` — shadcn `Button`; opens confirmation popover with agent FQN input (pre-filled from suite's last run if available); `useEvalMutations().runEval`; on success navigates to run detail
- Status polling in `useEvalRun` activates automatically for pending/running status

**Independent test**: MSW handlers from quickstart.md US2. Form validation errors appear. Submit creates suite with cases. "Run Evaluation" triggers run, list shows pending → running → completed without manual refresh.

---

### Phase 5: Adversarial Test Generation (US3)

Goal: "Generate Adversarial Tests" button triggering ATE run with review modal.

**Files**:
- `components/features/eval/AdversarialTestReviewModal.tsx` — shadcn `Dialog`; props: `{ evalSetId, agentFqn, onClose }`; loads `useAteConfigs` to find workspace ATE config; if none exists: shows "No ATE config" message with disabled generate button; if exists: "Generate" button triggers `useEvalMutations().runAte`; stores returned `ateRunId` in local state; `useAteRun(ateRunId)` polls; spinner while running; on complete extracts `report.generated_cases`; renders review list (each case: input, expected, category chip, Accept/Edit/Discard buttons); "Edit" opens inline editable fields; "Add Accepted Cases" calls `addCase` for each accepted case then closes
- Wire "Generate Adversarial Tests" button on `[evalSetId]/page.tsx` — opens `AdversarialTestReviewModal`; disabled if user lacks workspace_admin role and no ATE config exists

**Independent test**: MSW handlers from quickstart.md US3. Modal opens, spinner shows, cases appear in review list, accept/edit/discard work, accepted cases added to suite.

---

### Phase 6: Eval Run Comparison (US4)

Goal: Side-by-side A/B comparison of two eval runs using the backend experiment endpoint.

**Files**:
- `components/features/eval/EvalComparisonView.tsx` — receives `experimentId`, `runAId`, `runBId`; owns `useAbExperiment(experimentId)` (polls until complete); also fetches `useEvalRunVerdicts(runAId)` + `useEvalRunVerdicts(runBId)`; renders: 3 metric delta cards (avg score, pass rate, total cases) with directional arrows; paired verdicts table (joined by `benchmark_case_id`); unmatched cases sections; overall winner indicator (shadcn `Badge` variant per winner)
- Wire run selection checkboxes on `EvalRunList` — up to 2 runs can be checked; when 2 selected a "Compare" button appears; clicking navigates to `/evaluation-testing/compare?runA={id}&runB={id}`
- `apps/web/app/(main)/evaluation-testing/compare/page.tsx` — reads `runA` and `runB` from `searchParams`; creates experiment via `useEvalMutations().createExperiment`; stores experiment ID in state; renders `EvalComparisonView`; spinner while experiment pending

**Independent test**: MSW handlers from quickstart.md US4. Two runs selected, compare navigates, experiment created, polls to completed, metric deltas displayed, paired verdicts aligned, winner shown.

---

### Phase 7: Simulation Management (US5)

Goal: Simulation list, create form (with twin multi-select and warning flags), detail page with SIMULATION badge, cancellation.

**Files**:
- `components/features/simulations/SimulationRunDataTable.tsx` — reuses `DataTable`; columns: Name, Status (with status badge), Digital Twin(s) (source FQNs), Completion Date; row checkboxes for comparison selection; "Load More" cursor pagination; loading skeleton; empty state
- `components/features/simulations/CreateSimulationForm.tsx` — RHF + Zod; name (required), description; digital twin multi-select using `Popover` + `Command` (active twins only, showing `source_agent_fqn` + version, warning flag chips inline); isolation policy `Select` (default option = workspace default policy); scenario config with `duration_seconds` number input + optional fields as JSON textarea; warning `Alert` when any selected twin has `warning_flags`; `useSimulationMutations().createRun` on submit
- `components/features/simulations/SimulationDetailView.tsx` — props: `{ run, twins }`; amber SIMULATION `Badge` in header; status indicator with `refetchInterval` polling; results section (JSON pretty-print or structured display of `run.results`); digital twins accordion (source agent FQN, version, modifications, warning flags); "Cancel" button (shadcn `Button` variant="destructive") triggers `ConfirmDialog` then `useSimulationMutations().cancelRun`; "Compare with Production" button (US6)
- `apps/web/app/(main)/evaluation-testing/simulations/page.tsx` — owns `useSimulationRuns`; renders `SimulationRunDataTable`; "Create Simulation" + "Compare" buttons
- `apps/web/app/(main)/evaluation-testing/simulations/new/page.tsx` — renders `CreateSimulationForm`; on success navigates to `[runId]`
- `apps/web/app/(main)/evaluation-testing/simulations/[runId]/page.tsx` — owns `useSimulationRun` + `useDigitalTwins`; renders `SimulationDetailView`

**Independent test**: MSW handlers from quickstart.md US5. DataTable renders, create form twin multi-select works, warning flags shown, launch creates simulation, detail page shows SIMULATION badge, status polls to completed, cancel triggers dialog.

---

### Phase 8: Simulation Comparison (US6)

Goal: Simulation vs production (or simulation vs simulation) comparison view.

**Files**:
- `components/features/simulations/SimulationComparisonView.tsx` — props: `{ report, type }`; renders: two column header cards (primary = simulation, secondary = production/simulation 2); metric difference table (metric name, primary, secondary, delta, direction icon); overall verdict `Badge` per `ComparisonVerdict`; incompatibility `Alert` when `compatible: false`; loading state while `report.status === "pending"`;
- Wire "Compare with Production" button on `SimulationDetailView` — opens baseline period form (shadcn `Popover` with 3 presets + date picker); on submit calls `useSimulationMutations().createComparison`; stores `reportId` and navigates to `/evaluation-testing/simulations/compare?primary={runId}&report={reportId}&type=simulation_vs_production`
- Wire run checkboxes on `SimulationRunDataTable` — when 2 selected, "Compare" button enabled; navigates to `/evaluation-testing/simulations/compare?primary={id}&secondary={id}&type=simulation_vs_simulation` and triggers `createComparison`
- `apps/web/app/(main)/evaluation-testing/simulations/compare/page.tsx` — reads URL params; owns `useSimulationComparison(reportId)` (polls); renders `SimulationComparisonView`

**Independent test**: MSW handlers from quickstart.md US6. Compare with production flow works end-to-end: baseline form → POST → poll → metric table with "Simulation is better" verdict. Sim vs sim flow also works via run selection.

---

### Phase 9: Polish and Cross-Cutting Concerns

Goal: Accessibility, dark mode, responsive layout.

**Files**:
- Accessibility: `aria-label` on all icon-only buttons; `aria-busy` on polling status indicators; chart descriptions on Recharts SVG wrappers; keyboard navigation for run selection checkboxes and verdict table
- Dark mode: verify all color usage in `SimulationDetailView` (SIMULATION badge amber tokens), status badges, score histogram fill colors use `dark:` variants
- Responsive: DataTable horizontal scroll on mobile; comparison views stack columns vertically on `<768px`; creation forms verify field stacking on mobile

---

## API Endpoints Used

### Evaluation (`/api/v1/evaluations/`)

| Endpoint | Method | Used by |
|----------|--------|---------|
| `/eval-sets` | GET, POST | US1 list, US2 create |
| `/eval-sets/{id}` | GET | US1 detail |
| `/eval-sets/{id}/cases` | GET, POST | US1 cases, US2 add case |
| `/eval-sets/{id}/run` | POST | US2 trigger run |
| `/runs` | GET | US1 runs list |
| `/runs/{id}` | GET | US1 run detail (polling) |
| `/runs/{id}/verdicts` | GET | US1 verdicts, US4 comparison |
| `/experiments` | POST | US4 create A/B |
| `/experiments/{id}` | GET | US4 polling |
| `/ate` | GET | US3 load configs |
| `/ate/{id}/run/{fqn}` | POST | US3 trigger ATE |
| `/ate/runs/{id}` | GET | US3 polling |

### Simulation (`/api/v1/simulations/`)

| Endpoint | Method | Used by |
|----------|--------|---------|
| `/` | GET, POST | US5 list, US5 create |
| `/{id}` | GET | US5 detail (polling) |
| `/{id}/cancel` | POST | US5 cancel |
| `/twins` | GET | US5 create form |
| `/isolation-policies` | GET | US5 create form |
| `/{id}/compare` | POST | US6 create comparison |
| `/comparisons/{id}` | GET | US6 polling |

## Dependencies

- **FEAT-FE-001** (App scaffold, feature 015): `useAppQuery`, `createApiClient`, `DataTable`, `MetricCard`, `EmptyState`, `ConfirmDialog`, layout shell
- **Feature 034** (Evaluation and Testing): Backend APIs must be deployed
- **Feature 040** (Simulation / Digital Twins): Backend APIs must be deployed

## Complexity Tracking

No constitution violations. No justification table needed.
