"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { A2AAgentCard } from "@/types/contracts";

const a2aApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useA2aAgentCard(agentId: string) {
  const query = useAppQuery<A2AAgentCard>(
    ["a2a-card", agentId],
    async () => {
      const card = await a2aApi.get<Record<string, unknown>>("/.well-known/agent.json", {
        skipAuth: false,
      });
      return {
        card,
        lastPublishedAt: new Date().toISOString(),
      };
    },
    {
      enabled: Boolean(agentId),
      retry: false,
    },
  );

  return {
    ...query,
    card: query.data?.card ?? null,
  };
}
