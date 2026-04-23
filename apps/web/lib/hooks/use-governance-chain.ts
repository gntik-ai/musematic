"use client";

import { useQueryClient, useMutation } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { GovernanceChain } from "@/types/governance";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface WorkspaceGovernanceChainResponse {
  id: string;
  workspace_id: string;
  observer_fqns: string[];
  judge_fqns: string[];
  enforcer_fqns: string[];
  created_at: string;
}

function normalizeChain(payload: WorkspaceGovernanceChainResponse): GovernanceChain {
  return {
    workspaceId: payload.workspace_id,
    observerAgentFqn: payload.observer_fqns[0] ?? null,
    judgeAgentFqn: payload.judge_fqns[0] ?? null,
    enforcerAgentFqn: payload.enforcer_fqns[0] ?? null,
    updatedAt: payload.created_at,
    updatedBy: "system",
  };
}

export function useGovernanceChain(workspaceId: string | null | undefined) {
  const query = useAppQuery<GovernanceChain>(
    ["governance-chain", workspaceId ?? "none"],
    async () =>
      normalizeChain(
        await api.get<WorkspaceGovernanceChainResponse>(
          `/api/v1/workspaces/${workspaceId}/governance-chain`,
        ),
      ),
    { enabled: Boolean(workspaceId), staleTime: 300_000 },
  );

  return query;
}

export function useGovernanceChainMutations(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GovernanceChain) =>
      api.put<WorkspaceGovernanceChainResponse>(
        `/api/v1/workspaces/${workspaceId}/governance-chain`,
        {
          observer_fqns: payload.observerAgentFqn ? [payload.observerAgentFqn] : [],
          judge_fqns: payload.judgeAgentFqn ? [payload.judgeAgentFqn] : [],
          enforcer_fqns: payload.enforcerAgentFqn ? [payload.enforcerAgentFqn] : [],
          policy_binding_ids: [],
          verdict_to_action_mapping: {},
        },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["governance-chain", workspaceId ?? "none"],
      });
    },
  });
}
