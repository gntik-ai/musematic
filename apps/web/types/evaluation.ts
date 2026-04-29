export type EvalSetStatus = "active" | "archived";
export type RunStatus = "pending" | "running" | "completed" | "failed";
export type VerdictStatus = "scored" | "error";
export type ExperimentStatus = "pending" | "completed" | "failed";
export type RubricScaleType = "numeric_1_5" | "categorical_enum";
export type TrajectoryComparisonMethod =
  | "exact_match"
  | "semantic_similarity"
  | "edit_distance"
  | "trajectory_judge";
export type ATERunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "pre_check_failed";
export type ReviewDecision = "confirmed" | "overridden";

export interface RubricDimension {
  id: string;
  name: string;
  description: string;
  weight: number;
  scaleType: RubricScaleType;
  categoricalValues: string[] | null;
}

export interface CalibrationScore {
  dimensionId: string;
  dimensionName: string;
  distribution: {
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
  };
  kappa: number;
  isOutlier: boolean;
}

export interface EvalSetResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  scorer_config: Record<string, unknown>;
  pass_threshold: number;
  status: EvalSetStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EvalSetListResponse {
  items: EvalSetResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface BenchmarkCaseResponse {
  id: string;
  eval_set_id: string;
  input_data: Record<string, unknown>;
  expected_output: string;
  scoring_criteria: Record<string, unknown>;
  metadata_tags: Record<string, unknown>;
  category: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface BenchmarkCaseListResponse {
  items: BenchmarkCaseResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface EvaluationRunResponse {
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
  aggregate_score: number | null;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationRunListResponse {
  items: EvaluationRunResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface HumanAiGradeResponse {
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

export interface JudgeVerdictResponse {
  id: string;
  run_id: string;
  benchmark_case_id: string;
  actual_output: string;
  scorer_results: Record<string, unknown>;
  overall_score: number | null;
  passed: boolean | null;
  error_detail: string | null;
  status: VerdictStatus;
  human_grade: HumanAiGradeResponse | null;
  created_at: string;
  updated_at: string;
}

export interface JudgeVerdictListResponse {
  items: JudgeVerdictResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface AbExperimentResponse {
  id: string;
  workspace_id: string;
  name: string;
  run_a_id: string;
  run_b_id: string;
  status: ExperimentStatus;
  p_value: number | null;
  confidence_interval: Record<string, unknown> | null;
  effect_size: number | null;
  winner: string | null;
  analysis_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface ATEConfigResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  scenarios: Array<Record<string, unknown>>;
  scorer_config: Record<string, unknown>;
  performance_thresholds: Record<string, unknown>;
  safety_checks: Array<Record<string, unknown>>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ATEConfigListResponse {
  items: ATEConfigResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ATERunResponse {
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
  report: Record<string, unknown> | null;
  pre_check_errors: unknown[] | null;
  created_at: string;
  updated_at: string;
}

export interface EvalListFilters {
  status: EvalSetStatus | "all";
  search: string;
  tags: string[];
  labels: Record<string, string>;
  page: number;
}

export interface EvalRunFilters {
  tags: string[];
  labels: Record<string, string>;
}

export interface ScoreHistogramBin {
  rangeLabel: string;
  min: number;
  max: number;
  count: number;
}

export interface PairedVerdict {
  caseId: string;
  caseName: string;
  scoreA: number | null;
  scoreB: number | null;
  passedA: boolean | null;
  passedB: boolean | null;
  delta: number | null;
}

export interface ATEGeneratedCase {
  id: string;
  inputPrompt: string;
  expectedBehavior: string;
  category: string;
  accepted: boolean | null;
  editedInputPrompt?: string | undefined;
  editedExpectedOutput?: string | undefined;
}

export interface BenchmarkCaseCreateInput {
  input_data: Record<string, unknown>;
  expected_output: string;
  scoring_criteria?: Record<string, unknown> | undefined;
  metadata_tags?: Record<string, unknown> | undefined;
  category?: string | null | undefined;
  position?: number | undefined;
}

export interface EvalSetCreateInput {
  workspace_id: string;
  name: string;
  description?: string | null | undefined;
  scorer_config?: Record<string, unknown> | undefined;
  pass_threshold: number;
}

export const DEFAULT_EVAL_LIST_FILTERS: EvalListFilters = {
  status: "all",
  search: "",
  tags: [],
  labels: {},
  page: 1,
};

export const evalQueryKeys = {
  root: ["evaluationTesting", "evaluation"] as const,
  evalSets: (workspaceId: string | null | undefined, filters: EvalListFilters) =>
    ["evaluationTesting", "evaluation", "evalSets", workspaceId ?? "none", filters] as const,
  evalSet: (evalSetId: string | null | undefined) =>
    ["evaluationTesting", "evaluation", "evalSet", evalSetId ?? "none"] as const,
  cases: (evalSetId: string | null | undefined, page = 1) =>
    ["evaluationTesting", "evaluation", "cases", evalSetId ?? "none", page] as const,
  runs: (
    workspaceId: string | null | undefined,
    evalSetId?: string | null,
    filters?: EvalRunFilters,
  ) =>
    [
      "evaluationTesting",
      "evaluation",
      "runs",
      workspaceId ?? "none",
      evalSetId ?? "all",
      filters ?? { tags: [], labels: {} },
    ] as const,
  run: (runId: string | null | undefined) =>
    ["evaluationTesting", "evaluation", "run", runId ?? "none"] as const,
  verdicts: (runId: string | null | undefined, page = 1) =>
    ["evaluationTesting", "evaluation", "verdicts", runId ?? "none", page] as const,
  experiment: (experimentId: string | null | undefined) =>
    ["evaluationTesting", "evaluation", "experiment", experimentId ?? "none"] as const,
  ateConfigs: (workspaceId: string | null | undefined) =>
    ["evaluationTesting", "evaluation", "ateConfigs", workspaceId ?? "none"] as const,
  ateRun: (ateRunId: string | null | undefined) =>
    ["evaluationTesting", "evaluation", "ateRun", ateRunId ?? "none"] as const,
};
