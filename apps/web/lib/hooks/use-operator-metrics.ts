"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import {
  normalizeOperatorMetrics,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";

export function useOperatorMetrics() {
  const query = useAppQuery(
    operatorDashboardQueryKeys.metrics,
    async () =>
      normalizeOperatorMetrics(
        await operatorDashboardApi.get("/api/v1/dashboard/metrics"),
      ),
    {
      refetchInterval: 15_000,
    },
  );

  const metrics = query.data;
  const isStale = metrics
    ? Date.now() - new Date(metrics.computedAt).getTime() > 30_000
    : false;

  return {
    metrics,
    isLoading: query.isLoading,
    isError: query.isError,
    isStale,
  };
}
