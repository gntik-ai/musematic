"use client";

import { analyticsApi, analyticsQueryKeys } from "@/lib/hooks/use-analytics-usage";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { AnalyticsFilters, CostIntelligenceResponse } from "@/types/analytics";

function buildCostIntelligencePath(filters: AnalyticsFilters): string {
  const searchParams = new URLSearchParams({
    workspace_id: filters.workspaceId,
    start_time: filters.from,
    end_time: filters.to,
  });

  return `/api/v1/analytics/cost-intelligence?${searchParams.toString()}`;
}

export function useCostIntelligence(filters: AnalyticsFilters | null | undefined) {
  return useAppQuery<CostIntelligenceResponse>(
    analyticsQueryKeys.costIntelligence(
      filters?.workspaceId,
      filters?.from ?? "",
      filters?.to ?? "",
    ),
    () =>
      analyticsApi.get<CostIntelligenceResponse>(
        buildCostIntelligencePath(
          filters ?? {
            workspaceId: "",
            from: "",
            to: "",
            granularity: "daily",
          },
        ),
      ),
    {
      enabled: Boolean(filters?.workspaceId),
    },
  );
}
