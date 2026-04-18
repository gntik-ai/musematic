# Quickstart: Evaluation and Testing UI

**Feature**: 050-evaluation-testing-ui  
**Phase**: 1 — Design  
**Date**: 2026-04-18

## What This Feature Creates

```text
apps/web/
├── app/(main)/evaluation-testing/
│   ├── layout.tsx                          # NEW — tab nav: "Eval Suites" | "Simulations"
│   ├── page.tsx                            # NEW — eval suite list
│   ├── new/page.tsx                        # NEW — create eval suite form
│   ├── compare/page.tsx                    # NEW — eval run A/B comparison
│   ├── [evalSetId]/page.tsx                # NEW — eval suite detail + runs
│   ├── [evalSetId]/runs/[runId]/page.tsx   # NEW — run detail: verdicts + histogram
│   ├── simulations/
│   │   ├── page.tsx                        # NEW — simulation runs list
│   │   ├── new/page.tsx                    # NEW — create simulation form
│   │   ├── compare/page.tsx                # NEW — simulation comparison view
│   │   └── [runId]/page.tsx               # NEW — simulation detail + SIMULATION badge
│
├── components/features/eval/              # NEW directory
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
├── components/features/simulations/       # NEW directory
│   ├── SimulationRunDataTable.tsx
│   ├── CreateSimulationForm.tsx
│   ├── SimulationDetailView.tsx
│   └── SimulationComparisonView.tsx
│
├── lib/hooks/
│   ├── use-eval-sets.ts                    # NEW
│   ├── use-eval-runs.ts                    # NEW
│   ├── use-eval-verdicts.ts                # NEW
│   ├── use-ab-experiment.ts               # NEW
│   ├── use-ate.ts                          # NEW
│   ├── use-eval-mutations.ts              # NEW
│   ├── use-simulation-runs.ts             # NEW
│   ├── use-digital-twins.ts               # NEW
│   ├── use-isolation-policies.ts          # NEW
│   ├── use-simulation-comparison.ts       # NEW
│   └── use-simulation-mutations.ts        # NEW
│
└── types/
    ├── evaluation.ts                       # NEW
    └── simulation.ts                       # NEW
```

## Development Setup

No new npm packages required. All libraries are already installed:
- `recharts` (score histogram)
- `@tanstack/react-query` (data fetching + polling)
- `react-hook-form` + `zod` (forms)
- `shadcn/ui` (all UI primitives)
- `date-fns` (date formatting)

---

## Testing Per User Story

### US1 — Eval Suite Browsing and Run Detail

**Setup (MSW handlers)**:
```typescript
http.get("*/api/v1/evaluations/eval-sets", () =>
  HttpResponse.json({
    items: [
      { id: "es-1", workspace_id: "ws-1", name: "KYC Agent Quality",
        description: null, scorer_config: {}, pass_threshold: 0.7,
        status: "active", created_by: "user-1",
        created_at: "2026-04-10T00:00:00Z", updated_at: "2026-04-10T00:00:00Z" },
    ],
    total: 1, page: 1, page_size: 20,
  }),
)
http.get("*/api/v1/evaluations/runs", () =>
  HttpResponse.json({
    items: [
      { id: "run-1", workspace_id: "ws-1", eval_set_id: "es-1",
        agent_fqn: "finance:kyc", agent_id: null, status: "completed",
        started_at: "2026-04-17T10:00:00Z", completed_at: "2026-04-17T10:05:00Z",
        total_cases: 20, passed_cases: 17, failed_cases: 2, error_cases: 1,
        aggregate_score: 0.85, error_detail: null,
        created_at: "2026-04-17T10:00:00Z", updated_at: "2026-04-17T10:05:00Z" },
    ],
    total: 1, page: 1, page_size: 20,
  }),
)
http.get("*/api/v1/evaluations/runs/run-1/verdicts", () =>
  HttpResponse.json({
    items: [
      { id: "v-1", run_id: "run-1", benchmark_case_id: "bc-1",
        actual_output: "Approved", scorer_results: {}, overall_score: 0.9,
        passed: true, error_detail: null, status: "scored", human_grade: null,
        created_at: "...", updated_at: "..." },
      { id: "v-2", run_id: "run-1", benchmark_case_id: "bc-2",
        actual_output: "", scorer_results: {}, overall_score: null,
        passed: null, error_detail: "Timeout after 30s", status: "error",
        human_grade: null, created_at: "...", updated_at: "..." },
    ],
    total: 2, page: 1, page_size: 50,
  }),
)
```

**Test checks**:
1. DataTable renders with "KYC Agent Quality" row
2. Status filter "active" shows only active suites
3. Search filters rows by name
4. Clicking suite row navigates to detail
5. Run list shows "run-1" with status "completed" and score "85%"
6. Selecting run shows verdicts table with "v-1" (pass) and "v-2" (error, expandable)
7. Aggregate metrics: Total 20, Passed 17, Failed 2, Average 85%
8. Score histogram renders with one bin at 0.8–0.9 (count: 1)

---

### US2 — Create and Run Evaluations

**Setup (MSW handlers)**:
```typescript
http.post("*/api/v1/evaluations/eval-sets", () =>
  HttpResponse.json({ id: "es-new", name: "My Suite", status: "active", ... }, { status: 201 }),
)
http.post("*/api/v1/evaluations/eval-sets/es-new/cases", () =>
  HttpResponse.json({ id: "bc-new", position: 0, ... }, { status: 201 }),
)
http.post("*/api/v1/evaluations/eval-sets/es-new/run", () =>
  HttpResponse.json({ id: "run-new", status: "pending", ... }, { status: 202 }),
)
// Poll sequence: pending → running → completed
let pollCount = 0;
http.get("*/api/v1/evaluations/runs/run-new", () => {
  pollCount++;
  const status = pollCount < 2 ? "pending" : pollCount < 4 ? "running" : "completed";
  return HttpResponse.json({ id: "run-new", status, aggregate_score: pollCount >= 4 ? 0.8 : null, ... });
})
```

**Test checks**:
1. Form validation: empty name shows error, no test cases shows error
2. Submit creates eval set and navigates to detail
3. "Run Evaluation" button triggers POST and shows run in list with "pending"
4. Status auto-updates from pending → running → completed within 15s (3 poll cycles)
5. After completion, verdicts become visible

---

### US3 — Adversarial Test Generation

**Setup (MSW handlers)**:
```typescript
http.get("*/api/v1/evaluations/ate", () =>
  HttpResponse.json({ items: [{ id: "ate-1", name: "Default ATE", ... }], ... }),
)
http.post("*/api/v1/evaluations/ate/ate-1/run/finance:kyc", () =>
  HttpResponse.json({ id: "ate-run-1", status: "pending", report: null, ... }, { status: 202 }),
)
let atePollCount = 0;
http.get("*/api/v1/evaluations/ate/runs/ate-run-1", () => {
  atePollCount++;
  if (atePollCount < 3) return HttpResponse.json({ id: "ate-run-1", status: "running", report: null });
  return HttpResponse.json({
    id: "ate-run-1", status: "completed",
    report: { generated_cases: [
      { input_prompt: "What if I use SQL injection?", expected_behavior: "Rejected", category: "injection" },
      { input_prompt: "Boundary case 0", expected_behavior: "Handled", category: "boundary" },
    ]}, ...
  });
})
```

**Test checks**:
1. "Generate Adversarial Tests" button opens modal with spinner while polling
2. After completion, two generated cases appear in review list
3. Accepting case 1 adds it to the suite's case list
4. Discarding case 2 removes it from review list
5. With no ATE configs (`items: []`), button is disabled with tooltip "Admin must configure ATE first"

---

### US4 — Eval Run Comparison

**Setup (MSW handlers)**:
```typescript
http.post("*/api/v1/evaluations/experiments", () =>
  HttpResponse.json({ id: "exp-1", status: "pending", run_a_id: "run-1", run_b_id: "run-2", ... }, { status: 202 }),
)
let expPollCount = 0;
http.get("*/api/v1/evaluations/experiments/exp-1", () => {
  expPollCount++;
  if (expPollCount < 3) return HttpResponse.json({ id: "exp-1", status: "pending", winner: null });
  return HttpResponse.json({
    id: "exp-1", status: "completed",
    winner: "run_b", p_value: 0.03, effect_size: 0.4,
    analysis_summary: "Run B shows statistically significant improvement.", ...
  });
})
```

**Test checks**:
1. Selecting two runs enables "Compare" button
2. Clicking Compare navigates to compare page and creates experiment
3. Comparison view shows spinner while pending
4. After completion: Run A and Run B metric cards with deltas
5. "Run B is better" winner indicator displays
6. Paired verdicts table aligns cases by benchmark_case_id
7. Unmatched cases appear in "Unique to Run A/B" sections

---

### US5 — Simulation Management

**Setup (MSW handlers)**:
```typescript
http.get("*/api/v1/simulations/", () =>
  HttpResponse.json({ items: [
    { run_id: "sim-1", name: "KYC Load Test", status: "completed",
      digital_twin_ids: ["twin-1"], completed_at: "2026-04-17T12:00:00Z", ... },
  ], next_cursor: null }),
)
http.get("*/api/v1/simulations/twins", () =>
  HttpResponse.json({ items: [
    { twin_id: "twin-1", source_agent_fqn: "finance:kyc", version: 1,
      is_active: true, warning_flags: [], ... },
  ], next_cursor: null }),
)
http.post("*/api/v1/simulations/", () =>
  HttpResponse.json({ run_id: "sim-new", status: "provisioning", ... }, { status: 201 }),
)
http.post("*/api/v1/simulations/sim-new/cancel", () =>
  HttpResponse.json({ run_id: "sim-new", status: "cancelled", ... }),
)
```

**Test checks**:
1. Simulation DataTable renders "KYC Load Test" with "completed" badge
2. Create form: twin multi-select shows "finance:kyc v1"
3. Launch creates simulation and navigates to detail page
4. Detail shows SIMULATION badge (amber)
5. Status auto-updates provisioning → running → completed
6. Cancel button shows confirmation dialog; confirmed → status → "cancelled"

---

### US6 — Simulation vs Production Comparison

**Setup (MSW handlers)**:
```typescript
http.post("*/api/v1/simulations/sim-1/compare", () =>
  HttpResponse.json({ report_id: "rpt-1", status: "pending", ... }, { status: 202 }),
)
let rptPollCount = 0;
http.get("*/api/v1/simulations/comparisons/rpt-1", () => {
  rptPollCount++;
  if (rptPollCount < 3) return HttpResponse.json({ report_id: "rpt-1", status: "pending" });
  return HttpResponse.json({
    report_id: "rpt-1", status: "completed", compatible: true,
    incompatibility_reasons: [],
    overall_verdict: "primary_better",
    metric_differences: [
      { metric_name: "quality_score", primary_value: 0.88, secondary_value: 0.79, delta: 0.09, direction: "better" },
    ], ...
  });
})
```

**Test checks**:
1. "Compare with Production" opens baseline period form
2. Submit creates comparison and navigates to compare page
3. Spinner shows while pending
4. After completion: metric table with delta values and directional arrows
5. "Simulation is better" verdict badge displayed
6. With `compatible: false` and `incompatibility_reasons`: warning banner shows reasons

---

## Edge Case Scenarios

| Scenario | Expected |
|----------|----------|
| Empty workspace (no eval suites) | Empty state with "Create Eval Suite" CTA button |
| Eval run with `status: "failed"` | Error state with `error_detail`; no verdicts table; no histogram |
| ATE `status: "pre_check_failed"` | `pre_check_errors` displayed; no review list |
| Comparison with zero overlapping cases | Paired table empty state; all cases in "Unique to…" sections |
| Simulation `status: "timeout"` | "Timeout" badge; message suggests re-run with shorter duration |
| Digital twin with `warning_flags` | Warning badge in twin selector; Alert banner on form |
| Backend unavailable | Inline error per section with retry; other sections unaffected |
| Mobile viewport | DataTables scroll horizontally; forms stack vertically; comparison view stacks A/B vertically |
