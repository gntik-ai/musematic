"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  simQueryKeys,
  type DigitalTwinListResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildTwinsPath(workspaceId: string, activeOnly?: boolean): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
  });
  if (activeOnly) {
    searchParams.set("is_active", "true");
  }
  return `/api/v1/simulations/twins?${searchParams.toString()}`;
}

export function useDigitalTwins(workspaceId: string, activeOnly = false) {
  return useAppQuery<DigitalTwinListResponse>(
    simQueryKeys.twins(workspaceId, activeOnly),
    () => simulationApi.get<DigitalTwinListResponse>(buildTwinsPath(workspaceId, activeOnly)),
    {
      enabled: Boolean(workspaceId),
    },
  );
}
