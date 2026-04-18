"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  simQueryKeys,
  type SimulationIsolationPolicyListResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useIsolationPolicies(workspaceId: string) {
  return useAppQuery<SimulationIsolationPolicyListResponse>(
    simQueryKeys.isolationPolicies(workspaceId),
    () =>
      simulationApi.get<SimulationIsolationPolicyListResponse>(
        `/api/v1/simulations/isolation-policies?workspace_id=${encodeURIComponent(workspaceId)}`,
      ),
    {
      enabled: Boolean(workspaceId),
    },
  );
}
