"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { agentManagementQueryKeys } from "@/lib/hooks/use-agents";
import type { AgentNamespaceSummary } from "@/lib/types/agent-management";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface NamespaceListResponse {
  items: AgentNamespaceSummary[];
}

export function useNamespaces(workspaceId: string | null | undefined) {
  return useAppQuery<AgentNamespaceSummary[]>(
    agentManagementQueryKeys.namespaces(workspaceId),
    async () => {
      const searchParams = new URLSearchParams({
        workspace_id: workspaceId ?? "",
      });
      const response = await registryApi.get<NamespaceListResponse>(
        `/api/v1/registry/namespaces?${searchParams.toString()}`,
      );
      return response.items;
    },
    {
      enabled: Boolean(workspaceId),
    },
  );
}
