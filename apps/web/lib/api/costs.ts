"use client";

import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import { createApiClient } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";

export type CostType = "model" | "compute" | "storage" | "overhead";
export type BudgetPeriodType = "daily" | "weekly" | "monthly";
export type AnomalyState = "open" | "acknowledged" | "resolved";
export type AnomalySeverity = "low" | "medium" | "high" | "critical";

export interface CostAttributionRecord {
  id: string;
  execution_id: string;
  step_id?: string | null;
  workspace_id: string;
  agent_id?: string | null;
  user_id?: string | null;
  origin: string;
  model_id?: string | null;
  currency: string;
  model_cost_cents: string;
  compute_cost_cents: string;
  storage_cost_cents: string;
  overhead_cost_cents: string;
  total_cost_cents: string;
  token_counts: Record<string, unknown>;
  created_at: string;
}

export interface WorkspaceBudgetResponse {
  id: string;
  workspace_id: string;
  period_type: BudgetPeriodType;
  budget_cents: number;
  soft_alert_thresholds: number[];
  hard_cap_enabled: boolean;
  admin_override_enabled: boolean;
  currency: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceBudgetRequest {
  period_type: BudgetPeriodType;
  budget_cents: number;
  soft_alert_thresholds: number[];
  hard_cap_enabled: boolean;
  admin_override_enabled: boolean;
  currency: string;
}

export interface BudgetAlertResponse {
  id: string;
  budget_id: string;
  workspace_id: string;
  threshold_percentage: number;
  period_start: string;
  period_end: string;
  spend_cents: string;
  triggered_at: string;
}

export interface ChargebackReportRequest {
  dimensions: string[];
  group_by: string[];
  since: string;
  until: string;
  workspace_filter?: string[];
}

export interface ChargebackReportRow {
  dimensions: Record<string, string | number | null>;
  model_cost_cents: string;
  compute_cost_cents: string;
  storage_cost_cents: string;
  overhead_cost_cents: string;
  total_cost_cents: string;
  currency: string;
}

export interface ChargebackReportResponse {
  dimensions: string[];
  time_range: { since: string; until: string };
  group_by: string[];
  rows: ChargebackReportRow[];
  totals: Record<string, string>;
  currency: string;
  generated_at: string;
}

export interface CostForecastResponse {
  id: string;
  workspace_id: string;
  period_start: string;
  period_end: string;
  forecast_cents: string | null;
  confidence_interval: Record<string, unknown>;
  currency: string;
  computed_at: string;
  freshness_seconds?: number | null;
}

export interface CostAnomalyResponse {
  id: string;
  workspace_id: string;
  anomaly_type: string;
  severity: AnomalySeverity;
  state: AnomalyState;
  baseline_cents: string;
  observed_cents: string;
  period_start: string;
  period_end: string;
  summary: string;
  correlation_fingerprint: string;
  detected_at: string;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
}

export interface WorkspaceCostSummary {
  workspace_id: string;
  total_cost_cents: number;
  model_cost_cents: number;
  compute_cost_cents: number;
  storage_cost_cents: number;
  overhead_cost_cents: number;
  top_agents: Array<{ agent_id: string | null; total_cost_cents: number }>;
  top_users: Array<{ user_id: string | null; total_cost_cents: number }>;
  breakdown: Array<Record<string, unknown>>;
}

const COSTS_API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const costsApiClient = createApiClient(COSTS_API_BASE_URL);

export const costsQueryKeys = {
  summary: (workspaceId?: string | null) => ["costs", "summary", workspaceId ?? "none"] as const,
  budgets: (workspaceId?: string | null) => ["costs", "budgets", workspaceId ?? "none"] as const,
  alerts: (workspaceId?: string | null) => ["costs", "alerts", workspaceId ?? "none"] as const,
  forecast: (workspaceId?: string | null) => ["costs", "forecast", workspaceId ?? "none"] as const,
  anomalies: (workspaceId?: string | null, state?: string) =>
    ["costs", "anomalies", workspaceId ?? "none", state ?? "all"] as const,
  anomaly: (id?: string | null) => ["costs", "anomaly", id ?? "none"] as const,
};

function cents(value: unknown): number {
  return Number(value ?? 0);
}

function addAgentTotals(rows: Array<Record<string, unknown>>) {
  const totals = new Map<string | null, number>();
  for (const row of rows) {
    const rawKey = row.agent_id;
    const id = typeof rawKey === "string" ? rawKey : null;
    totals.set(id, (totals.get(id) ?? 0) + cents(row.total_cost_cents));
  }
  return [...totals.entries()]
    .map(([agent_id, total_cost_cents]) => ({ agent_id, total_cost_cents }))
    .sort((left, right) => right.total_cost_cents - left.total_cost_cents)
    .slice(0, 5);
}

function addUserTotals(rows: Array<Record<string, unknown>>) {
  const totals = new Map<string | null, number>();
  for (const row of rows) {
    const rawKey = row.user_id;
    const id = typeof rawKey === "string" ? rawKey : null;
    totals.set(id, (totals.get(id) ?? 0) + cents(row.total_cost_cents));
  }
  return [...totals.entries()]
    .map(([user_id, total_cost_cents]) => ({ user_id, total_cost_cents }))
    .sort((left, right) => right.total_cost_cents - left.total_cost_cents)
    .slice(0, 5);
}

export async function fetchWorkspaceCostSummary(
  workspaceId: string,
): Promise<WorkspaceCostSummary> {
  const response = await costsApiClient.get<{
    items: Array<Record<string, unknown>>;
    group_by?: string[];
  }>(`/api/v1/costs/workspaces/${workspaceId}/attributions?limit=500`);
  const rows = response.items ?? [];
  return {
    workspace_id: workspaceId,
    total_cost_cents: rows.reduce((sum, row) => sum + cents(row.total_cost_cents), 0),
    model_cost_cents: rows.reduce((sum, row) => sum + cents(row.model_cost_cents), 0),
    compute_cost_cents: rows.reduce((sum, row) => sum + cents(row.compute_cost_cents), 0),
    storage_cost_cents: rows.reduce((sum, row) => sum + cents(row.storage_cost_cents), 0),
    overhead_cost_cents: rows.reduce((sum, row) => sum + cents(row.overhead_cost_cents), 0),
    top_agents: addAgentTotals(rows),
    top_users: addUserTotals(rows),
    breakdown: rows,
  };
}

export function fetchBudgets(workspaceId: string) {
  return costsApiClient.get<WorkspaceBudgetResponse[]>(
    `/api/v1/costs/workspaces/${workspaceId}/budgets`,
  );
}

export function saveBudget(workspaceId: string, payload: WorkspaceBudgetRequest) {
  return costsApiClient.post<WorkspaceBudgetResponse>(
    `/api/v1/costs/workspaces/${workspaceId}/budgets`,
    payload,
  );
}

export function deleteBudget(workspaceId: string, periodType: BudgetPeriodType) {
  return costsApiClient.delete<void>(
    `/api/v1/costs/workspaces/${workspaceId}/budgets/${periodType}`,
  );
}

export function fetchBudgetAlerts(workspaceId: string) {
  return costsApiClient.get<BudgetAlertResponse[]>(
    `/api/v1/costs/workspaces/${workspaceId}/alerts`,
  );
}

export function issueOverride(workspaceId: string, reason: string) {
  return costsApiClient.post<{ token: string; expires_at: string }>(
    `/api/v1/costs/workspaces/${workspaceId}/budget/override`,
    { reason },
  );
}

export function fetchLatestForecast(workspaceId: string) {
  return costsApiClient.get<CostForecastResponse>(
    `/api/v1/costs/workspaces/${workspaceId}/forecast`,
  );
}

export function fetchOpenAnomalies(workspaceId: string, state: AnomalyState | "all" = "open") {
  const query = state === "all" ? "" : `?state=${state}`;
  return costsApiClient.get<CostAnomalyResponse[]>(
    `/api/v1/costs/workspaces/${workspaceId}/anomalies${query}`,
  );
}

export function fetchAnomaly(id: string) {
  return costsApiClient.get<CostAnomalyResponse>(`/api/v1/costs/anomalies/${id}`);
}

export function acknowledgeAnomaly(id: string, notes?: string) {
  return costsApiClient.post<CostAnomalyResponse>(
    `/api/v1/costs/anomalies/${id}/acknowledge`,
    { notes },
  );
}

export function resolveAnomaly(id: string) {
  return costsApiClient.post<CostAnomalyResponse>(`/api/v1/costs/anomalies/${id}/resolve`);
}

export function generateChargebackReport(payload: ChargebackReportRequest) {
  return costsApiClient.post<ChargebackReportResponse>(
    "/api/v1/costs/reports/chargeback",
    payload,
  );
}

export async function exportChargebackReport(
  payload: ChargebackReportRequest,
  format: "csv" | "ndjson",
) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = useAuthStore.getState().accessToken;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${COSTS_API_BASE_URL}/api/v1/costs/reports/chargeback/export`, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...payload, format }),
  });
  if (!response.ok) {
    throw new Error("chargeback_export_failed");
  }
  return response.text();
}

export function useWorkspaceCostSummary(workspaceId?: string | null) {
  return useAppQuery(
    costsQueryKeys.summary(workspaceId),
    () => fetchWorkspaceCostSummary(workspaceId ?? ""),
    { enabled: Boolean(workspaceId) },
  );
}

export function useWorkspaceBudgets(workspaceId?: string | null) {
  return useAppQuery(costsQueryKeys.budgets(workspaceId), () => fetchBudgets(workspaceId ?? ""), {
    enabled: Boolean(workspaceId),
  });
}

export function useBudgetAlerts(workspaceId?: string | null) {
  return useAppQuery(
    costsQueryKeys.alerts(workspaceId),
    () => fetchBudgetAlerts(workspaceId ?? ""),
    { enabled: Boolean(workspaceId) },
  );
}

export function useLatestForecast(workspaceId?: string | null) {
  return useAppQuery(
    costsQueryKeys.forecast(workspaceId),
    () => fetchLatestForecast(workspaceId ?? ""),
    { enabled: Boolean(workspaceId), retry: false },
  );
}

export function useOpenAnomalies(workspaceId?: string | null) {
  return useAppQuery(
    costsQueryKeys.anomalies(workspaceId, "open"),
    () => fetchOpenAnomalies(workspaceId ?? "", "open"),
    { enabled: Boolean(workspaceId) },
  );
}

export function useAnomaly(id?: string | null) {
  return useAppQuery(costsQueryKeys.anomaly(id), () => fetchAnomaly(id ?? ""), {
    enabled: Boolean(id),
  });
}

export function useSaveBudget(workspaceId?: string | null) {
  return useAppMutation((payload: WorkspaceBudgetRequest) => saveBudget(workspaceId ?? "", payload), {
    invalidateKeys: [costsQueryKeys.budgets(workspaceId), costsQueryKeys.summary(workspaceId)],
  });
}

export function useIssueOverride(workspaceId?: string | null) {
  return useAppMutation((reason: string) => issueOverride(workspaceId ?? "", reason));
}
