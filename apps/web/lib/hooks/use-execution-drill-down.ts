"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import {
  normalizeActiveExecution,
  normalizeBudgetStatus,
  normalizeContextQuality,
  normalizeReasoningTrace,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";

export function useExecutionDetail(executionId: string | null | undefined) {
  return useAppQuery(
    operatorDashboardQueryKeys.executionDetail(executionId),
    async () =>
      normalizeActiveExecution(
        await operatorDashboardApi.get(
          `/api/v1/executions/${encodeURIComponent(executionId ?? "")}`,
        ),
      ),
    {
      enabled: Boolean(executionId),
      staleTime: 30_000,
    },
  );
}

export function useReasoningTrace(executionId: string | null | undefined) {
  return useAppQuery(
    operatorDashboardQueryKeys.reasoningTrace(executionId),
    async () =>
      normalizeReasoningTrace(
        await operatorDashboardApi.get(
          `/api/v1/executions/${encodeURIComponent(
            executionId ?? "",
          )}/reasoning-trace`,
        ),
      ),
    {
      enabled: Boolean(executionId),
      staleTime: 60_000,
    },
  );
}

export function useBudgetStatus(
  executionId: string | null | undefined,
  isActive: boolean,
) {
  return useAppQuery(
    operatorDashboardQueryKeys.budgetStatus(executionId),
    async () =>
      normalizeBudgetStatus(
        await operatorDashboardApi.get(
          `/api/v1/executions/${encodeURIComponent(
            executionId ?? "",
          )}/budget-status`,
        ),
      ),
    {
      enabled: Boolean(executionId),
      staleTime: isActive ? 0 : Number.POSITIVE_INFINITY,
      ...(isActive ? { refetchInterval: 5_000 } : {}),
    },
  );
}

export function useContextQuality(executionId: string | null | undefined) {
  return useAppQuery(
    operatorDashboardQueryKeys.contextQuality(executionId),
    async () =>
      normalizeContextQuality(
        await operatorDashboardApi.get(
          `/api/v1/executions/${encodeURIComponent(
            executionId ?? "",
          )}/context-quality`,
        ),
      ),
    {
      enabled: Boolean(executionId),
      staleTime: 60_000,
    },
  );
}
