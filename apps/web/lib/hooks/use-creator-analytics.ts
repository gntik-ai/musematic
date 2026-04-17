"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { marketplaceQueryKeys } from "@/lib/hooks/use-marketplace-search";
import { splitAgentFqn, type CreatorAnalytics } from "@/lib/types/marketplace";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useCreatorAnalytics(fqn: string, periodDays = 30) {
  const { namespace, localName } = splitAgentFqn(fqn);

  return useAppQuery(
    marketplaceQueryKeys.analytics(fqn, periodDays),
    () =>
      marketplaceApi.get<CreatorAnalytics>(
        `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}/analytics?periodDays=${periodDays}`,
      ),
    {
      enabled: Boolean(fqn),
    },
  );
}
