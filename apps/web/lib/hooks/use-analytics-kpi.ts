"use client";

import { analyticsApi, analyticsQueryKeys } from "@/lib/hooks/use-analytics-usage";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { AnalyticsFilters, KpiSeries } from "@/types/analytics";

function buildKpiPath(filters: AnalyticsFilters): string {
  const searchParams = new URLSearchParams({
    workspace_id: filters.workspaceId,
    start_time: filters.from,
    end_time: filters.to,
    granularity: filters.granularity,
  });

  return `/api/v1/analytics/kpi?${searchParams.toString()}`;
}

export function useAnalyticsKpi(filters: AnalyticsFilters | null | undefined) {
  return useAppQuery<KpiSeries>(
    analyticsQueryKeys.kpi(
      filters?.workspaceId,
      filters?.from ?? "",
      filters?.to ?? "",
      filters?.granularity ?? "daily",
    ),
    () =>
      analyticsApi.get<KpiSeries>(
        buildKpiPath(
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
      staleTime: 60_000,
    },
  );
}
