"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { agentManagementQueryKeys } from "@/lib/hooks/use-agents";
import type { AgentHealthScore } from "@/lib/types/agent-management";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useAgentHealth(fqn: string | null | undefined) {
  return useAppQuery<AgentHealthScore>(
    agentManagementQueryKeys.health(fqn ?? ""),
    () =>
      registryApi.get<AgentHealthScore>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn ?? "")}/health`,
      ),
    {
      enabled: Boolean(fqn),
    },
  );
}
