"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  type ActiveExecution,
  type ActiveExecutionsFilters,
} from "@/lib/types/operator-dashboard";
import {
  asNumber,
  normalizeActiveExecution,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";
import { wsClient } from "@/lib/ws";

interface ActiveExecutionsResponse {
  executions: ActiveExecution[];
  totalCount: number;
}

function buildPath(
  workspaceId: string,
  filters: ActiveExecutionsFilters,
): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    status:
      filters.status === "all"
        ? "running,paused,waiting_for_approval,compensating"
        : filters.status,
    page_size: "100",
    sort_by: filters.sortBy,
  });

  return `/api/v1/executions?${searchParams.toString()}`;
}

export function useActiveExecutions(
  workspaceId: string | null | undefined,
  filters: ActiveExecutionsFilters,
) {
  const queryClient = useQueryClient();
  const query = useAppQuery<ActiveExecutionsResponse>(
    operatorDashboardQueryKeys.activeExecutions(workspaceId, filters),
    async () => {
      const response = (await operatorDashboardApi.get(
        buildPath(workspaceId ?? "", filters),
      )) as Record<string, unknown>;
      const items = Array.isArray(response.items) ? response.items : [];

      return {
        executions: items.map(normalizeActiveExecution),
        totalCount: asNumber(response.total, items.length),
      };
    },
    {
      enabled: Boolean(workspaceId),
      refetchInterval: 5_000,
    },
  );

  useEffect(() => {
    if (!workspaceId) {
      return undefined;
    }

    const unsubscribe = wsClient.subscribe(`workspace:${workspaceId}`, () => {
      void queryClient.invalidateQueries({
        queryKey: ["operatorDashboard", "activeExecutions", workspaceId],
      });
    });

    return () => {
      unsubscribe();
    };
  }, [queryClient, workspaceId]);

  return {
    executions: query.data?.executions ?? [],
    totalCount: query.data?.totalCount ?? 0,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
