"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { marketplaceQueryKeys } from "@/lib/hooks/use-marketplace-search";
import type { AgentDetail } from "@/lib/types/marketplace";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useAgentDetail(namespace: string, name: string) {
  return useAppQuery(
    marketplaceQueryKeys.agent(namespace, name),
    () =>
      marketplaceApi.get<AgentDetail>(
        `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
      ),
    {
      enabled: Boolean(namespace) && Boolean(name),
    },
  );
}
