"use client";

import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery, useAppQuery } from "@/lib/hooks/use-api";
import type { FilterMetadata, MarketplaceSearchParams } from "@/lib/types/marketplace";
import type { PaginatedResponse } from "@/types/api";
import type { AgentCard } from "@/lib/types/marketplace";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const marketplaceQueryKeys = {
  search: (params: MarketplaceSearchParams) =>
    ["marketplace", "search", params] as const,
  agent: (namespace: string, name: string) =>
    ["marketplace", "agent", namespace, name] as const,
  reviews: (fqn: string, page?: number) =>
    page === undefined
      ? (["marketplace", "reviews", fqn] as const)
      : (["marketplace", "reviews", fqn, page] as const),
  recommendations: () => ["marketplace", "recommendations"] as const,
  analytics: (fqn: string, periodDays: number) =>
    ["marketplace", "analytics", fqn, periodDays] as const,
  filters: () => ["marketplace", "filters"] as const,
};

function buildSearchUrl(params: MarketplaceSearchParams, page: number): string {
  const searchParams = new URLSearchParams();

  if (params.q) {
    searchParams.set("q", params.q);
  }

  if (params.capabilities.length > 0) {
    searchParams.set("capabilities", params.capabilities.join(","));
  }

  if (params.maturityLevels.length > 0) {
    searchParams.set("maturityLevels", params.maturityLevels.join(","));
  }

  if (params.trustTiers.length > 0) {
    searchParams.set("trustTiers", params.trustTiers.join(","));
  }

  if (params.certificationStatuses.length > 0) {
    searchParams.set(
      "certificationStatuses",
      params.certificationStatuses.join(","),
    );
  }

  if (params.costTiers.length > 0) {
    searchParams.set("costTiers", params.costTiers.join(","));
  }

  if (params.tags.length > 0) {
    searchParams.set("tags", params.tags.join(","));
  }

  searchParams.set("sortBy", params.sortBy);
  searchParams.set("page", String(page));
  searchParams.set("pageSize", String(params.pageSize));

  return `/api/v1/marketplace/search?${searchParams.toString()}`;
}

export function useMarketplaceSearch(params: MarketplaceSearchParams) {
  return useAppInfiniteQuery<PaginatedResponse<AgentCard>, number>(
    marketplaceQueryKeys.search(params),
    (page) =>
      marketplaceApi.get<PaginatedResponse<AgentCard>>(
        buildSearchUrl(params, page ?? params.page),
      ),
    {
      initialCursor: params.page,
      getNextPageParam: (lastPage) =>
        lastPage.hasNext ? lastPage.page + 1 : undefined,
    },
  );
}

export function useMarketplaceFilterMetadata() {
  return useAppQuery(
    marketplaceQueryKeys.filters(),
    () => marketplaceApi.get<FilterMetadata>("/api/v1/marketplace/filters/metadata"),
  );
}
