"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  simQueryKeys,
  type SimulationComparisonReportResponse,
} from "@/types/simulation";

const simulationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useSimulationComparison(reportId: string | null) {
  return useAppQuery<SimulationComparisonReportResponse>(
    simQueryKeys.comparison(reportId),
    () =>
      simulationApi.get<SimulationComparisonReportResponse>(
        `/api/v1/simulations/comparisons/${encodeURIComponent(reportId ?? "")}`,
      ),
    {
      enabled: Boolean(reportId),
      refetchInterval: (query) =>
        query.state.data && ["completed", "failed"].includes(query.state.data.status)
          ? false
          : 3_000,
    },
  );
}
