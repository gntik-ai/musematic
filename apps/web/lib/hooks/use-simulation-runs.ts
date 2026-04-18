"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  simQueryKeys,
  type SimulationRunListResponse,
  type SimulationRunResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildSimulationRunsPath(workspaceId: string, cursor?: string): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
  });
  if (cursor) {
    searchParams.set("cursor", cursor);
  }
  return `/api/v1/simulations/?${searchParams.toString()}`;
}

function isTerminalStatus(status: SimulationRunResponse["status"]): boolean {
  return ["completed", "cancelled", "failed", "timeout"].includes(status);
}

export function useSimulationRuns(workspaceId: string, cursor?: string) {
  return useAppQuery<SimulationRunListResponse>(
    simQueryKeys.runs(workspaceId, cursor),
    () =>
      simulationApi.get<SimulationRunListResponse>(
        buildSimulationRunsPath(workspaceId, cursor),
      ),
    {
      enabled: Boolean(workspaceId),
    },
  );
}

export function useSimulationRun(runId: string) {
  return useAppQuery<SimulationRunResponse>(
    simQueryKeys.run(runId),
    () =>
      simulationApi.get<SimulationRunResponse>(
        `/api/v1/simulations/${encodeURIComponent(runId)}`,
      ),
    {
      enabled: Boolean(runId),
      refetchInterval: (query) =>
        query.state.data && isTerminalStatus(query.state.data.status) ? false : 3_000,
    },
  );
}
