"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { marketplaceQueryKeys } from "@/lib/hooks/use-marketplace-search";
import type { RecommendationCarousel } from "@/lib/types/marketplace";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useRecommendations() {
  return useAppQuery(
    marketplaceQueryKeys.recommendations(),
    () =>
      marketplaceApi.get<RecommendationCarousel>(
        "/api/v1/marketplace/recommendations",
      ),
  );
}
