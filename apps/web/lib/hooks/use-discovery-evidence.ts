"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { DiscoveryCritiqueListResponse } from "@/types/discovery";
import { discoveryQueryKeys } from "@/types/discovery";

const discoveryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useDiscoveryEvidence(hypothesisId: string, workspaceId?: string | null) {
  return useAppQuery<DiscoveryCritiqueListResponse>(
    discoveryQueryKeys.critiques(hypothesisId, workspaceId),
    () => {
      const params = workspaceId ? `?${new URLSearchParams({ workspace_id: workspaceId })}` : "";
      return discoveryApi.get<DiscoveryCritiqueListResponse>(
        `/api/v1/discovery/hypotheses/${encodeURIComponent(hypothesisId)}/critiques${params}`,
      );
    },
    { enabled: Boolean(hypothesisId && workspaceId) },
  );
}
