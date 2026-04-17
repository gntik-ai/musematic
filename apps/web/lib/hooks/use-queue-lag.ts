"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import {
  normalizeQueueLagSnapshot,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";

export function useQueueLag() {
  const query = useAppQuery(
    operatorDashboardQueryKeys.queueLag,
    async () =>
      normalizeQueueLagSnapshot(
        await operatorDashboardApi.get("/api/v1/dashboard/queue-lag"),
      ),
    {
      refetchInterval: 15_000,
    },
  );

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
