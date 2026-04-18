"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import {
  simQueryKeys,
  type SimulationComparisonCreateInput,
  type SimulationComparisonReportResponse,
  type SimulationRunCreateInput,
  type SimulationRunResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildComparisonPayload(input: SimulationComparisonCreateInput) {
  return {
    secondary_run_id: input.secondaryRunId ?? null,
    production_baseline_period: input.productionBaselinePeriod ?? null,
    comparison_type: input.comparisonType,
  };
}

export function useSimulationMutations() {
  const queryClient = useQueryClient();

  const invalidateSimulationQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: simQueryKeys.root });
  };

  const createRun = useMutation({
    mutationFn: (payload: SimulationRunCreateInput) =>
      simulationApi.post<SimulationRunResponse>("/api/v1/simulations/", payload),
    onSuccess: invalidateSimulationQueries,
  });

  const cancelRun = useMutation({
    mutationFn: (runId: string) =>
      simulationApi.post<SimulationRunResponse>(
        `/api/v1/simulations/${encodeURIComponent(runId)}/cancel`,
      ),
    onSuccess: invalidateSimulationQueries,
  });

  const createComparison = useMutation({
    mutationFn: (payload: SimulationComparisonCreateInput) =>
      simulationApi.post<SimulationComparisonReportResponse>(
        `/api/v1/simulations/${encodeURIComponent(payload.primaryRunId)}/compare`,
        buildComparisonPayload(payload),
      ),
    onSuccess: invalidateSimulationQueries,
  });

  return {
    createRun,
    cancelRun,
    createComparison,
  };
}
