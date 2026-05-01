"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  simQueryKeys,
  type ScenarioRunInput,
  type ScenarioRunSummary,
  type SimulationScenario,
  type SimulationScenarioInput,
  type SimulationScenarioListResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function scenariosPath(workspaceId: string, cursor?: string) {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (cursor) {
    params.set("cursor", cursor);
  }
  return `/api/v1/simulations/scenarios?${params.toString()}`;
}

export function useScenarios(workspaceId: string, cursor?: string) {
  return useAppQuery<SimulationScenarioListResponse>(
    simQueryKeys.scenarios(workspaceId, cursor),
    () => simulationApi.get<SimulationScenarioListResponse>(scenariosPath(workspaceId, cursor)),
    { enabled: Boolean(workspaceId) },
  );
}

export function useScenario(id: string, workspaceId?: string | null) {
  return useAppQuery<SimulationScenario>(
    simQueryKeys.scenario(id),
    () => {
      const params = workspaceId ? `?${new URLSearchParams({ workspace_id: workspaceId })}` : "";
      return simulationApi.get<SimulationScenario>(
        `/api/v1/simulations/scenarios/${encodeURIComponent(id)}${params}`,
      );
    },
    { enabled: Boolean(id) },
  );
}

export function useCreateScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SimulationScenarioInput) =>
      simulationApi.post<SimulationScenario>("/api/v1/simulations/scenarios", payload),
    onSuccess: (scenario) => {
      void queryClient.invalidateQueries({ queryKey: simQueryKeys.scenarios(scenario.workspace_id) });
    },
  });
}

export function useUpdateScenario(id: string, workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<SimulationScenarioInput>) =>
      simulationApi.put<SimulationScenario>(
        `/api/v1/simulations/scenarios/${encodeURIComponent(id)}?${new URLSearchParams({ workspace_id: workspaceId })}`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: simQueryKeys.scenario(id) });
      void queryClient.invalidateQueries({ queryKey: simQueryKeys.scenarios(workspaceId) });
    },
  });
}

export function useArchiveScenario(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      simulationApi.delete<SimulationScenario>(
        `/api/v1/simulations/scenarios/${encodeURIComponent(id)}?${new URLSearchParams({ workspace_id: workspaceId })}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: simQueryKeys.scenarios(workspaceId) });
    },
  });
}

export function useRunScenario(id: string, workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ScenarioRunInput) =>
      simulationApi.post<ScenarioRunSummary>(
        `/api/v1/simulations/scenarios/${encodeURIComponent(id)}/run?${new URLSearchParams({ workspace_id: workspaceId })}`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: simQueryKeys.runs(workspaceId) });
    },
  });
}
