# Data Model: Evaluation and Testing UI

**Feature**: 050-evaluation-testing-ui  
**Phase**: 1 — Design  
**Date**: 2026-04-18  
**Source files**: `apps/web/types/evaluation.ts`, `apps/web/types/simulation.ts` (to be created)

## Overview

Frontend-only. All types mirror backend Pydantic schemas from:
- `apps/control-plane/src/platform/evaluation/schemas.py`
- `apps/control-plane/src/platform/simulation/schemas.py`

No new database tables.

---

## Evaluation Types (`apps/web/types/evaluation.ts`)

### Enums / Union Types

```typescript
type EvalSetStatus = "active" | "archived";
type RunStatus = "pending" | "running" | "completed" | "failed";
type VerdictStatus = "scored" | "error";
type ExperimentStatus = "pending" | "completed" | "failed";
type ATERunStatus = "pending" | "running" | "completed" | "failed" | "pre_check_failed";
type ReviewDecision = "confirmed" | "overridden";
```

### EvalSetResponse

Backend: `EvalSetResponse`

```typescript
interface EvalSetResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  scorer_config: Record<string, unknown>;
  pass_threshold: number;       // 0.0–1.0
  status: EvalSetStatus;
  created_by: string;
  created_at: string;           // ISO datetime
  updated_at: string;
}

interface EvalSetListResponse {
  items: EvalSetResponse[];
  total: number;
  page: number;
  page_size: number;
}
```

### BenchmarkCaseResponse

Backend: `BenchmarkCaseResponse`

```typescript
interface BenchmarkCaseResponse {
  id: string;
  eval_set_id: string;
  input_data: Record<string, unknown>;  // contains the input prompt
  expected_output: string;
  scoring_criteria: Record<string, unknown>;
  metadata_tags: Record<string, unknown>;
  category: string | null;              // e.g., "injection", "boundary", "evasion"
  position: number;
  created_at: string;
  updated_at: string;
}

interface BenchmarkCaseListResponse {
  items: BenchmarkCaseResponse[];
  total: number;
  page: number;
  page_size: number;
}
```

### EvaluationRunResponse

Backend: `EvaluationRunResponse`

```typescript
interface EvaluationRunResponse {
  id: string;
  workspace_id: string;
  eval_set_id: string;
  agent_fqn: string;
  agent_id: string | null;
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  error_cases: number;
  aggregate_score: number | null;   // 0.0–1.0
  error_detail: string | null;
  created_at: string;
  updated_at: string;
}

interface EvaluationRunListResponse {
  items: EvaluationRunResponse[];
  total: number;
  page: number;
  page_size: number;
}
```

### JudgeVerdictResponse

Backend: `JudgeVerdictResponse`

```typescript
interface JudgeVerdictResponse {
  id: string;
  run_id: string;
  benchmark_case_id: string;
  actual_output: string;
  scorer_results: Record<string, unknown>;   // per-scorer breakdown
  overall_score: number | null;              // 0.0–1.0
  passed: boolean | null;
  error_detail: string | null;
  status: VerdictStatus;
  human_grade: HumanAiGradeResponse | null;
  created_at: string;
  updated_at: string;
}

interface JudgeVerdictListResponse {
  items: JudgeVerdictResponse[];
  total: number;
  page: number;
  page_size: number;
}

interface HumanAiGradeResponse {
  id: string;
  verdict_id: string;
  reviewer_id: string;
  decision: ReviewDecision;
  override_score: number | null;
  feedback: string | null;
  original_score: number;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}
```

### AbExperimentResponse

Backend: `AbExperimentResponse`

```typescript
interface AbExperimentResponse {
  id: string;
  workspace_id: string;
  name: string;
  run_a_id: string;
  run_b_id: string;
  status: ExperimentStatus;
  p_value: number | null;
  confidence_interval: Record<string, unknown> | null;
  effect_size: number | null;
  winner: string | null;         // "run_a" | "run_b" | "equivalent"
  analysis_summary: string | null;
  created_at: string;
  updated_at: string;
}
```

### ATEConfigResponse / ATERunResponse

Backend: `ATEConfigResponse`, `ATERunResponse`

```typescript
interface ATEConfigResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  scenarios: Record<string, unknown>[];
  scorer_config: Record<string, unknown>;
  performance_thresholds: Record<string, unknown>;
  safety_checks: Record<string, unknown>[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface ATERunResponse {
  id: string;
  workspace_id: string;
  ate_config_id: string;
  agent_fqn: string;
  agent_id: string | null;
  simulation_id: string | null;
  status: ATERunStatus;
  started_at: string | null;
  completed_at: string | null;
  evidence_artifact_key: string | null;
  report: Record<string, unknown> | null;   // contains generated_cases when complete
  pre_check_errors: unknown[] | null;
  created_at: string;
  updated_at: string;
}
```

---

## Simulation Types (`apps/web/types/simulation.ts`)

### Enums / Union Types

```typescript
type SimRunStatus = "provisioning" | "running" | "completed" | "cancelled" | "failed" | "timeout";
type PredictionStatus = "pending" | "completed" | "insufficient_data" | "failed";
type ConfidenceLevel = "high" | "medium" | "low" | "insufficient_data";
type ComparisonType = "simulation_vs_simulation" | "simulation_vs_production" | "prediction_vs_actual";
type ComparisonVerdict = "primary_better" | "secondary_better" | "equivalent" | "inconclusive";
type ComparisonReportStatus = "pending" | "completed" | "failed";
```

### SimulationRunResponse

Backend: `SimulationRunResponse`

```typescript
interface SimulationRunResponse {
  run_id: string;           // aliased from "id" by backend
  workspace_id: string;
  name: string;
  description: string | null;
  status: SimRunStatus;
  digital_twin_ids: string[];
  scenario_config: Record<string, unknown>;
  isolation_policy_id: string | null;
  controller_run_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  results: Record<string, unknown> | null;
  initiated_by: string;
  created_at: string;
}

interface SimulationRunListResponse {
  items: SimulationRunResponse[];
  next_cursor: string | null;    // cursor-based pagination
}
```

### DigitalTwinResponse

Backend: `DigitalTwinResponse`

```typescript
interface DigitalTwinResponse {
  twin_id: string;           // aliased from "id"
  workspace_id: string;
  source_agent_fqn: string;
  source_revision_id: string | null;
  version: number;
  parent_twin_id: string | null;
  config_snapshot: Record<string, unknown>;
  behavioral_history_summary: Record<string, unknown>;
  modifications: Record<string, unknown>[];
  is_active: boolean;
  created_at: string;
  warning_flags: string[];
}

interface DigitalTwinListResponse {
  items: DigitalTwinResponse[];
  next_cursor: string | null;
}
```

### SimulationIsolationPolicyResponse

Backend: `SimulationIsolationPolicyResponse`

```typescript
interface SimulationIsolationPolicyResponse {
  policy_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  blocked_actions: Record<string, unknown>[];
  stubbed_actions: Record<string, unknown>[];
  permitted_read_sources: Record<string, unknown>[];
  is_default: boolean;
  halt_on_critical_breach: boolean;
  created_at: string;
  updated_at: string;
}

interface SimulationIsolationPolicyListResponse {
  items: SimulationIsolationPolicyResponse[];
}
```

### SimulationComparisonReportResponse

Backend: `SimulationComparisonReportResponse`

```typescript
interface MetricDifference {
  metric_name: string;
  primary_value: number | null;
  secondary_value: number | null;
  delta: number | null;
  delta_percent: number | null;
  direction: "better" | "worse" | "neutral" | null;
}

interface SimulationComparisonReportResponse {
  report_id: string;
  comparison_type: ComparisonType;
  primary_run_id: string;
  secondary_run_id: string | null;
  production_baseline_period: Record<string, unknown> | null;
  prediction_id: string | null;
  status: ComparisonReportStatus;
  compatible: boolean;
  incompatibility_reasons: string[];
  metric_differences: MetricDifference[];
  overall_verdict: ComparisonVerdict | null;
  created_at: string;
}
```

---

## UI State Types

### EvalListFilters

```typescript
interface EvalListFilters {
  status: EvalSetStatus | "all";
  search: string;
  page: number;
}
```

### ScoreHistogramBin

Computed client-side from `JudgeVerdictListResponse.items`.

```typescript
interface ScoreHistogramBin {
  rangeLabel: string;   // e.g., "0.0–0.1"
  min: number;          // 0.0
  max: number;          // 0.1
  count: number;
}
```

### PairedVerdict

Used in eval run comparison view.

```typescript
interface PairedVerdict {
  caseId: string;
  caseName: string;         // from BenchmarkCaseResponse.input_data or category
  scoreA: number | null;    // from JudgeVerdictResponse for run A
  scoreB: number | null;    // from JudgeVerdictResponse for run B
  passedA: boolean | null;
  passedB: boolean | null;
  delta: number | null;     // scoreB - scoreA
}
```

### ATEGeneratedCase

Extracted from `ATERunResponse.report` when ATE run completes.

```typescript
interface ATEGeneratedCase {
  id: string;             // temporary client-side ID for review flow
  inputPrompt: string;
  expectedBehavior: string;
  category: string;       // "injection" | "boundary" | "evasion" | etc.
  accepted: boolean | null;  // null = pending review
  editedInputPrompt?: string;
  editedExpectedOutput?: string;
}
```

---

## Validation Rules

- `EvalSetCreate`: `name` required (1–255 chars), at least one benchmark case required (validated client-side before submit), `pass_threshold` 0.0–1.0 (default 0.7)
- `BenchmarkCaseCreate`: `input_data` and `expected_output` both required, `expected_output` min 1 char
- `SimulationRunCreateRequest`: `name` required, `digital_twin_ids` min 1, `scenario_config.duration_seconds` must be positive if provided
- `AbExperimentCreate`: `name` required, two distinct `run_id` values required
- Score histogram: skip verdicts with `overall_score === null`; if all scores are null, show "No scores available" empty state
- ATE run status `"pre_check_failed"`: show `pre_check_errors` inline, not a generic error state
- Digital twin `warning_flags`: surfaced as inline warning chips in the multi-select and as a `Alert` on the create simulation form when any selected twin has warnings
