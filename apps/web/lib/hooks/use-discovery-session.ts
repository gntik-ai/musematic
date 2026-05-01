"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type {
  DiscoveryExperiment,
  DiscoveryHypothesis,
  DiscoveryHypothesisListResponse,
  DiscoverySession,
  ExperimentDesignInput,
} from "@/types/discovery";
import { discoveryQueryKeys } from "@/types/discovery";

const discoveryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function workspaceParams(workspaceId?: string | null) {
  return workspaceId ? `?${new URLSearchParams({ workspace_id: workspaceId })}` : "";
}

export function useDiscoverySession(sessionId: string, workspaceId?: string | null) {
  return useAppQuery<DiscoverySession>(
    discoveryQueryKeys.session(sessionId, workspaceId),
    () =>
      discoveryApi.get<DiscoverySession>(
        `/api/v1/discovery/sessions/${encodeURIComponent(sessionId)}${workspaceParams(workspaceId)}`,
      ),
    { enabled: Boolean(sessionId && workspaceId) },
  );
}

export function useDiscoveryHypotheses({
  sessionId,
  workspaceId,
  status,
  orderBy = "elo_desc",
}: {
  sessionId: string;
  workspaceId?: string | null;
  status?: string | null;
  orderBy?: "elo_desc" | "created_at";
}) {
  return useAppQuery<DiscoveryHypothesisListResponse>(
    discoveryQueryKeys.hypotheses(sessionId, workspaceId, status, orderBy),
    () => {
      const params = new URLSearchParams({
        workspace_id: workspaceId ?? "",
        order_by: orderBy,
        limit: "100",
      });
      if (status) {
        params.set("status", status);
      }
      return discoveryApi.get<DiscoveryHypothesisListResponse>(
        `/api/v1/discovery/sessions/${encodeURIComponent(sessionId)}/hypotheses?${params.toString()}`,
      );
    },
    { enabled: Boolean(sessionId && workspaceId) },
  );
}

export function useDiscoveryHypothesis(hypothesisId: string, workspaceId?: string | null) {
  return useAppQuery<DiscoveryHypothesis>(
    discoveryQueryKeys.hypothesis(hypothesisId, workspaceId),
    () =>
      discoveryApi.get<DiscoveryHypothesis>(
        `/api/v1/discovery/hypotheses/${encodeURIComponent(hypothesisId)}${workspaceParams(workspaceId)}`,
      ),
    { enabled: Boolean(hypothesisId && workspaceId) },
  );
}

export function useDiscoveryExperiments(sessionId: string, workspaceId?: string | null) {
  return useAppQuery<{ items: DiscoveryExperiment[] }>(
    discoveryQueryKeys.experiments(sessionId, workspaceId),
    () =>
      discoveryApi.get<{ items: DiscoveryExperiment[] }>(
        `/api/v1/discovery/sessions/${encodeURIComponent(sessionId)}/experiments${workspaceParams(workspaceId)}`,
      ),
    { enabled: Boolean(sessionId && workspaceId) },
  );
}

export function useLaunchDiscoveryExperiment(hypothesisId: string, workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload?: Partial<ExperimentDesignInput>) =>
      discoveryApi.post<DiscoveryExperiment>(
        `/api/v1/discovery/hypotheses/${encodeURIComponent(hypothesisId)}/experiment`,
        { workspace_id: payload?.workspace_id ?? workspaceId },
      ),
    onSuccess: (experiment) => {
      queryClient.setQueryData<{ items: DiscoveryExperiment[] }>(
        discoveryQueryKeys.experiments(experiment.session_id, workspaceId),
        (current) => ({
          items: [
            experiment,
            ...(current?.items ?? []).filter(
              (item) => item.experiment_id !== experiment.experiment_id,
            ),
          ],
        }),
      );
      void queryClient.invalidateQueries({
        queryKey: discoveryQueryKeys.experiments(experiment.session_id, workspaceId),
      });
    },
  });
}
