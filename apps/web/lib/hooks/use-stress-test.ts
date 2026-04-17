"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys, getCurrentWorkspaceId } from "@/lib/hooks/use-fleets";
import type { StressTestProgress } from "@/lib/types/fleet";

interface TriggerStressTestInput {
  fleetId: string;
  durationMinutes: number;
  loadLevel: "low" | "medium" | "high";
  workspaceId?: string | null;
}

interface TriggerStressTestResponse {
  simulation_run_id: string;
  status: "provisioning" | "running";
}

interface CancelStressTestInput {
  runId: string;
}

interface CancelStressTestResponse {
  status: "cancelled";
}

export function useTriggerStressTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      fleetId,
      durationMinutes,
      loadLevel,
      workspaceId,
    }: TriggerStressTestInput) => {
      const resolvedWorkspaceId = getCurrentWorkspaceId(workspaceId);
      if (!resolvedWorkspaceId) {
        throw new Error("A workspace is required to trigger a stress test.");
      }

      return fleetApi.post<TriggerStressTestResponse>("/api/v1/simulation/runs", {
        fleet_id: fleetId,
        workspace_id: resolvedWorkspaceId,
        duration_minutes: durationMinutes,
        load_level: loadLevel,
        type: "stress_test",
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({
        queryKey: fleetQueryKeys.stressTestProgress(data.simulation_run_id),
      });
    },
  });
}

export function useStressTestProgress(runId: string | null | undefined) {
  return useAppQuery<StressTestProgress>(
    fleetQueryKeys.stressTestProgress(runId),
    () =>
      fleetApi.get<StressTestProgress>(
        `/api/v1/simulation/runs/${encodeURIComponent(runId ?? "")}`,
      ),
    {
      enabled: Boolean(runId),
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        return status === "completed" || status === "cancelled" || status === "failed"
          ? false
          : 3_000;
      },
    },
  );
}

export function useCancelStressTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId }: CancelStressTestInput) =>
      fleetApi.post<CancelStressTestResponse>(
        `/api/v1/simulation/runs/${encodeURIComponent(runId)}/cancel`,
      ),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({
        queryKey: fleetQueryKeys.stressTestProgress(variables.runId),
      });
    },
  });
}

