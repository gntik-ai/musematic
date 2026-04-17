"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import {
  normalizeServiceHealthSnapshot,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";

export function useServiceHealth() {
  const query = useAppQuery(
    operatorDashboardQueryKeys.serviceHealth,
    async () =>
      normalizeServiceHealthSnapshot(await operatorDashboardApi.get("/health")),
    {
      refetchInterval: 30_000,
    },
  );

  return {
    snapshot: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
