"use client";

import { analyticsApi, analyticsQueryKeys } from "@/lib/hooks/use-analytics-usage";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { RecommendationsResponse } from "@/types/analytics";

function buildRecommendationsPath(workspaceId: string): string {
  const searchParams = new URLSearchParams({ workspace_id: workspaceId });
  return `/api/v1/analytics/recommendations?${searchParams.toString()}`;
}

export function useOptimizationRecommendations(
  workspaceId: string | null | undefined,
) {
  return useAppQuery<RecommendationsResponse>(
    analyticsQueryKeys.recommendations(workspaceId),
    () =>
      analyticsApi.get<RecommendationsResponse>(
        buildRecommendationsPath(workspaceId ?? ""),
      ),
    {
      enabled: Boolean(workspaceId),
      staleTime: 300_000,
    },
  );
}
