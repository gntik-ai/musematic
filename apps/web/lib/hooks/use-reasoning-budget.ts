"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import {
  normalizeReasoningBudgetUtilization,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";

export function useReasoningBudget() {
  const query = useAppQuery(
    operatorDashboardQueryKeys.reasoningBudget,
    async () =>
      normalizeReasoningBudgetUtilization(
        await operatorDashboardApi.get(
          "/api/v1/dashboard/reasoning-budget-utilization",
        ),
      ),
    {
      refetchInterval: 10_000,
    },
  );

  return {
    utilization: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
