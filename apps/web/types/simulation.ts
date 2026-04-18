export type SimRunStatus =
  | "provisioning"
  | "running"
  | "completed"
  | "cancelled"
  | "failed"
  | "timeout";
export type PredictionStatus =
  | "pending"
  | "completed"
  | "insufficient_data"
  | "failed";
export type ConfidenceLevel = "high" | "medium" | "low" | "insufficient_data";
export type ComparisonType =
  | "simulation_vs_simulation"
  | "simulation_vs_production"
  | "prediction_vs_actual";
export type ComparisonVerdict =
  | "primary_better"
  | "secondary_better"
  | "equivalent"
  | "inconclusive";
export type ComparisonReportStatus = "pending" | "completed" | "failed";

export interface SimulationRunResponse {
  run_id: string;
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

export interface SimulationRunListResponse {
  items: SimulationRunResponse[];
  next_cursor: string | null;
}

export interface DigitalTwinResponse {
  twin_id: string;
  workspace_id: string;
  source_agent_fqn: string;
  source_revision_id: string | null;
  version: number;
  parent_twin_id: string | null;
  config_snapshot: Record<string, unknown>;
  behavioral_history_summary: Record<string, unknown>;
  modifications: Array<Record<string, unknown>>;
  is_active: boolean;
  created_at: string;
  warning_flags: string[];
}

export interface DigitalTwinListResponse {
  items: DigitalTwinResponse[];
  next_cursor: string | null;
}

export interface SimulationIsolationPolicyResponse {
  policy_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  blocked_actions: Array<Record<string, unknown>>;
  stubbed_actions: Array<Record<string, unknown>>;
  permitted_read_sources: Array<Record<string, unknown>>;
  is_default: boolean;
  halt_on_critical_breach: boolean;
  created_at: string;
  updated_at: string;
}

export interface SimulationIsolationPolicyListResponse {
  items: SimulationIsolationPolicyResponse[];
}

export interface MetricDifference {
  metric_name: string;
  primary_value: number | null;
  secondary_value: number | null;
  delta: number | null;
  delta_percent: number | null;
  direction: "better" | "worse" | "neutral" | null;
}

export interface SimulationComparisonReportResponse {
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

export interface SimulationRunCreateInput {
  workspace_id: string;
  name: string;
  description?: string | null | undefined;
  digital_twin_ids: string[];
  scenario_config: Record<string, unknown>;
  isolation_policy_id?: string | null | undefined;
}

export interface SimulationComparisonCreateInput {
  primaryRunId: string;
  secondaryRunId?: string | null | undefined;
  productionBaselinePeriod?: Record<string, unknown> | null | undefined;
  comparisonType: ComparisonType;
}

export const simQueryKeys = {
  root: ["evaluationTesting", "simulations"] as const,
  runs: (workspaceId: string | null | undefined, cursor?: string | null) =>
    ["evaluationTesting", "simulations", "runs", workspaceId ?? "none", cursor ?? "root"] as const,
  run: (runId: string | null | undefined) =>
    ["evaluationTesting", "simulations", "run", runId ?? "none"] as const,
  twins: (workspaceId: string | null | undefined, activeOnly?: boolean) =>
    ["evaluationTesting", "simulations", "twins", workspaceId ?? "none", activeOnly ?? false] as const,
  isolationPolicies: (workspaceId: string | null | undefined) =>
    ["evaluationTesting", "simulations", "isolationPolicies", workspaceId ?? "none"] as const,
  comparison: (reportId: string | null | undefined) =>
    ["evaluationTesting", "simulations", "comparison", reportId ?? "none"] as const,
};
