"use client";

import { analyticsApi, analyticsQueryKeys } from "@/lib/hooks/use-analytics-usage";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { ForecastHorizon, ResourcePrediction } from "@/types/analytics";

function buildForecastPath(workspaceId: string, horizonDays: ForecastHorizon): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    horizon_days: String(horizonDays),
  });

  return `/api/v1/analytics/cost-forecast?${searchParams.toString()}`;
}

export function useCostForecast(
  workspaceId: string | null | undefined,
  horizonDays: ForecastHorizon,
) {
  return useAppQuery<ResourcePrediction>(
    analyticsQueryKeys.forecast(workspaceId, horizonDays),
    () =>
      analyticsApi.get<ResourcePrediction>(
        buildForecastPath(workspaceId ?? "", horizonDays),
      ),
    {
      enabled: Boolean(workspaceId),
    },
  );
}
