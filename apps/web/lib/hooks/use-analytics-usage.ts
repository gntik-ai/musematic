"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { AnalyticsFilters, UsageResponse } from "@/types/analytics";

export const analyticsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const analyticsQueryKeys = {
  usage: (
    workspaceId: string | null | undefined,
    from: string,
    to: string,
    granularity: string,
    agentFqn?: string | null,
  ) =>
    [
      "analytics",
      "usage",
      workspaceId ?? "none",
      from,
      to,
      granularity,
      agentFqn ?? "all",
    ] as const,
  costIntelligence: (
    workspaceId: string | null | undefined,
    from: string,
    to: string,
  ) => ["analytics", "cost-intelligence", workspaceId ?? "none", from, to] as const,
  recommendations: (workspaceId: string | null | undefined) =>
    ["analytics", "recommendations", workspaceId ?? "none"] as const,
  forecast: (workspaceId: string | null | undefined, horizonDays: number) =>
    ["analytics", "forecast", workspaceId ?? "none", horizonDays] as const,
  kpi: (
    workspaceId: string | null | undefined,
    from: string,
    to: string,
    granularity: string,
  ) => ["analytics", "kpi", workspaceId ?? "none", from, to, granularity] as const,
  driftAlerts: (workspaceId: string | null | undefined) =>
    ["analytics", "drift-alerts", workspaceId ?? "none"] as const,
};

function buildUsagePath(filters: AnalyticsFilters, agentFqn?: string | null): string {
  const searchParams = new URLSearchParams({
    workspace_id: filters.workspaceId,
    start_time: filters.from,
    end_time: filters.to,
    granularity: filters.granularity,
  });

  if (agentFqn) {
    searchParams.set("agent_fqn", agentFqn);
  }

  return `/api/v1/analytics/usage?${searchParams.toString()}`;
}

export function useAnalyticsUsage(
  filters: AnalyticsFilters | null | undefined,
  agentFqn?: string | null,
) {
  return useAppQuery<UsageResponse>(
    analyticsQueryKeys.usage(
      filters?.workspaceId,
      filters?.from ?? "",
      filters?.to ?? "",
      filters?.granularity ?? "daily",
      agentFqn,
    ),
    () => analyticsApi.get<UsageResponse>(buildUsagePath(filters ?? {
      workspaceId: "",
      from: "",
      to: "",
      granularity: "daily",
    }, agentFqn)),
    {
      enabled: Boolean(filters?.workspaceId),
      staleTime: 60_000,
    },
  );
}
