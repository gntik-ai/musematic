"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  evalQueryKeys,
  type ATEConfigListResponse,
  type ATERunResponse,
} from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useAteConfigs(workspaceId: string) {
  return useAppQuery<ATEConfigListResponse>(
    evalQueryKeys.ateConfigs(workspaceId),
    () => evaluationApi.get<ATEConfigListResponse>("/api/v1/evaluations/ate"),
    {
      enabled: Boolean(workspaceId),
    },
  );
}

export function useAteRun(ateRunId: string | null) {
  return useAppQuery<ATERunResponse>(
    evalQueryKeys.ateRun(ateRunId),
    () =>
      evaluationApi.get<ATERunResponse>(
        `/api/v1/evaluations/ate/runs/${encodeURIComponent(ateRunId ?? "")}`,
      ),
    {
      enabled: Boolean(ateRunId),
      refetchInterval: (query) =>
        query.state.data &&
        ["completed", "failed", "pre_check_failed"].includes(query.state.data.status)
          ? false
          : 3_000,
    },
  );
}
