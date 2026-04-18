export type Granularity = "hourly" | "daily" | "monthly";

export type RecommendationType =
  | "model_switch"
  | "self_correction_tuning"
  | "context_optimization"
  | "underutilization";

export type ConfidenceLevel = "high" | "medium" | "low";

export interface UsageRollupItem {
  period: string;
  workspace_id: string;
  agent_fqn: string;
  model_id: string;
  provider: string;
  execution_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_duration_ms: number;
  self_correction_loops: number;
}

export interface UsageResponse {
  items: UsageRollupItem[];
  total: number;
  workspace_id: string;
  granularity: Granularity;
  start_time: string;
  end_time: string;
}

export interface AgentCostQuality {
  agent_fqn: string;
  model_id: string;
  provider: string;
  total_cost_usd: number;
  avg_quality_score: number | null;
  cost_per_quality: number | null;
  execution_count: number;
  efficiency_rank: number;
}

export interface CostIntelligenceResponse {
  workspace_id: string;
  period_start: string;
  period_end: string;
  agents: AgentCostQuality[];
}

export interface OptimizationRecommendation {
  recommendation_type: RecommendationType;
  agent_fqn: string;
  title: string;
  description: string;
  estimated_savings_usd_per_month: number;
  confidence: ConfidenceLevel;
  data_points: number;
  supporting_data: Record<string, number | string | null>;
}

export interface RecommendationsResponse {
  workspace_id: string;
  recommendations: OptimizationRecommendation[];
  generated_at: string;
}

export interface ForecastPoint {
  date: string;
  projected_cost_usd_low: number;
  projected_cost_usd_expected: number;
  projected_cost_usd_high: number;
}

export interface ResourcePrediction {
  workspace_id: string;
  horizon_days: number;
  generated_at: string;
  trend_direction: string;
  high_volatility: boolean;
  data_points_used: number;
  warning: string | null;
  daily_forecast: ForecastPoint[];
  total_projected_low: number;
  total_projected_expected: number;
  total_projected_high: number;
}

export interface KpiDataPoint {
  period: string;
  total_cost_usd: number;
  execution_count: number;
  avg_duration_ms: number;
  avg_quality_score: number | null;
  cost_per_quality: number | null;
}

export interface KpiSeries {
  workspace_id: string;
  granularity: Granularity;
  start_time: string;
  end_time: string;
  items: KpiDataPoint[];
}

export interface DriftAlertResponse {
  id: string;
  agent_fqn: string;
  workspace_id: string;
  historical_mean: number;
  historical_stddev: number;
  recent_mean: number;
  degradation_delta: number;
  analysis_window_days: number;
  suggested_actions: string[];
  resolved_at: string | null;
  created_at: string;
}

export interface DriftAlertListResponse {
  items: DriftAlertResponse[];
  total: number;
  limit: number;
  offset: number;
}

export type DateRangePreset = "7d" | "30d" | "90d" | "custom";

export interface AnalyticsDateRange {
  from: Date;
  to: Date;
  preset: DateRangePreset;
}

export type BreakdownMode = "workspace" | "agent" | "model";

export type ForecastHorizon = 7 | 30 | 90;

export interface AnalyticsFilters {
  workspaceId: string;
  from: string;
  to: string;
  granularity: Granularity;
}

export interface CostChartPoint {
  period: string;
  [key: string]: number | string;
}

export interface TokenBarPoint {
  period: string;
  [provider: string]: number | string;
}

export interface ScatterPoint {
  agentFqn: string;
  modelId: string;
  provider: string;
  costUsd: number;
  qualityScore: number | null;
  executionCount: number;
  efficiencyRank: number;
  hasQualityData: boolean;
}

export interface ForecastChartPoint {
  date: string;
  low: number;
  expected: number;
  high: number;
}

export interface DriftChartPoint {
  period: string;
  value: number | null;
  baseline: number;
  isAnomaly: boolean;
}

export const DATE_RANGE_PRESET_LABELS: Record<DateRangePreset, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
  custom: "Custom",
};

export const BREAKDOWN_MODE_LABELS: Record<BreakdownMode, string> = {
  workspace: "Workspace",
  agent: "Agent",
  model: "Model",
};

export const FORECAST_HORIZON_LABELS: Record<ForecastHorizon, string> = {
  7: "7 days",
  30: "30 days",
  90: "90 days",
};
