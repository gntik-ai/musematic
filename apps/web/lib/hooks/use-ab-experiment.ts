"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { evalQueryKeys, type AbExperimentResponse } from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useAbExperiment(experimentId: string | null) {
  return useAppQuery<AbExperimentResponse>(
    evalQueryKeys.experiment(experimentId),
    () =>
      evaluationApi.get<AbExperimentResponse>(
        `/api/v1/evaluations/experiments/${encodeURIComponent(experimentId ?? "")}`,
      ),
    {
      enabled: Boolean(experimentId),
      refetchInterval: (query) =>
        query.state.data && ["completed", "failed"].includes(query.state.data.status)
          ? false
          : 3_000,
    },
  );
}
