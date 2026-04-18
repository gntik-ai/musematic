"use client";

import { analyticsApi, analyticsQueryKeys } from "@/lib/hooks/use-analytics-usage";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { DriftAlertListResponse } from "@/types/analytics";

function buildDriftAlertsPath(workspaceId: string): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    limit: "100",
    offset: "0",
  });

  return `/api/v1/context-engineering/drift-alerts?${searchParams.toString()}`;
}

export function useDriftAlerts(workspaceId: string | null | undefined) {
  return useAppQuery<DriftAlertListResponse>(
    analyticsQueryKeys.driftAlerts(workspaceId),
    () =>
      analyticsApi.get<DriftAlertListResponse>(
        buildDriftAlertsPath(workspaceId ?? ""),
      ),
    {
      enabled: Boolean(workspaceId),
    },
  );
}
