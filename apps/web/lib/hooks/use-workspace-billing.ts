"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

const billingApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export interface BillingSubscription {
  id: string;
  scope_type: string;
  plan_slug: string;
  plan_version: number;
  status: string;
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
  next_billing_eur: string;
}

export interface BillingPlanCaps {
  executions_per_day: number;
  executions_per_month: number;
  minutes_per_day: number;
  minutes_per_month: number;
  max_workspaces: number;
  max_agents_per_workspace: number;
  max_users_per_workspace: number;
  overage_price_per_minute: string;
  allowed_model_tier: string;
}

export interface BillingUsage {
  executions_today: number;
  executions_this_period: number;
  minutes_today: string;
  minutes_this_period: string;
  active_workspaces: number;
  active_agents_in_this_workspace: number;
  active_users_in_this_workspace: number;
}

export interface BillingForecast {
  executions_at_period_end: number;
  minutes_at_period_end: string;
  estimated_overage_eur: string;
  burn_rate_minutes_per_day: string;
}

export interface OverageAuthorizationState {
  billing_period_start: string;
  billing_period_end: string;
  is_authorized: boolean;
  authorization_id: string | null;
  authorization_required: boolean;
  current_overage_eur: string;
  max_overage_eur: string | null;
  authorized_by?: string | null;
  authorized_at?: string | null;
  forecast_total_overage_eur: string;
}

export interface WorkspaceBillingSummary {
  subscription: BillingSubscription;
  plan_caps: BillingPlanCaps;
  usage: BillingUsage;
  forecast: BillingForecast;
  overage: OverageAuthorizationState;
  payment_method: { status: string; last_four: string | null; expires: string | null };
  available_actions: string[];
}

export interface UsageHistoryItem {
  metric: "executions" | "minutes";
  period_start: string;
  period_end: string;
  quantity: string;
  is_overage: boolean;
}

export function workspaceBillingKeys(workspaceId: string) {
  return {
    summary: ["workspace", workspaceId, "billing"] as const,
    overage: ["workspace", workspaceId, "billing", "overage"] as const,
    history: ["workspace", workspaceId, "billing", "history"] as const,
  };
}

export function useWorkspaceBilling(workspaceId: string) {
  return useAppQuery(
    workspaceBillingKeys(workspaceId).summary,
    () => billingApi.get<WorkspaceBillingSummary>(`/api/v1/workspaces/${workspaceId}/billing`),
    { enabled: workspaceId.length > 0 },
  );
}

export function useOverageAuthorization(workspaceId: string) {
  return useAppQuery(
    workspaceBillingKeys(workspaceId).overage,
    () =>
      billingApi.get<OverageAuthorizationState>(
        `/api/v1/workspaces/${workspaceId}/billing/overage-authorization`,
      ),
    { enabled: workspaceId.length > 0 },
  );
}

export function useUsageHistory(workspaceId: string, periods = 12) {
  return useAppQuery(
    workspaceBillingKeys(workspaceId).history,
    () =>
      billingApi.get<{ items: UsageHistoryItem[] }>(
        `/api/v1/workspaces/${workspaceId}/billing/usage-history?periods=${periods}`,
      ),
    { enabled: workspaceId.length > 0 },
  );
}

export { billingApi };
