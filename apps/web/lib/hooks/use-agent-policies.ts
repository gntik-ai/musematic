"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { agentManagementQueryKeys } from "@/lib/hooks/use-agents";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { AgentPolicySummary } from "@/lib/types/agent-management";

const policyApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface AgentPolicyListResponse {
  items: AgentPolicySummary[];
}

export function useAgentPolicies(
  fqn: string | null | undefined,
  workspaceId?: string | null,
) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const resolvedWorkspaceId = workspaceId ?? currentWorkspaceId;

  return useAppQuery<AgentPolicyListResponse>(
    agentManagementQueryKeys.policies(resolvedWorkspaceId, fqn ?? ""),
    () => {
      const searchParams = new URLSearchParams({
        agent_fqn: fqn ?? "",
        workspace_id: resolvedWorkspaceId ?? "",
      });

      return policyApi.get<AgentPolicyListResponse>(
        `/api/v1/policies?${searchParams.toString()}`,
      );
    },
    {
      enabled: Boolean(fqn && resolvedWorkspaceId),
    },
  );
}
