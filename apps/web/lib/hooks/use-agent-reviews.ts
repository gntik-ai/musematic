"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { marketplaceQueryKeys } from "@/lib/hooks/use-marketplace-search";
import { splitAgentFqn, type AgentReview, type ReviewSubmission } from "@/lib/types/marketplace";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { PaginatedResponse } from "@/types/api";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildReviewsPath(fqn: string): string {
  const { namespace, localName } = splitAgentFqn(fqn);
  return `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}/reviews`;
}

export function useAgentReviews(fqn: string, page = 1) {
  return useAppQuery(
    marketplaceQueryKeys.reviews(fqn, page),
    () =>
      marketplaceApi.get<PaginatedResponse<AgentReview>>(
        `${buildReviewsPath(fqn)}?page=${page}&pageSize=10`,
      ),
    {
      enabled: Boolean(fqn),
    },
  );
}

export function useSubmitReview(fqn: string) {
  const queryClient = useQueryClient();
  const { namespace, localName } = splitAgentFqn(fqn);

  return useMutation({
    mutationFn: (payload: ReviewSubmission) =>
      marketplaceApi.post<AgentReview>(
        `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}/reviews`,
        payload,
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: marketplaceQueryKeys.reviews(fqn),
        }),
        queryClient.invalidateQueries({
          queryKey: marketplaceQueryKeys.agent(namespace, localName),
        }),
      ]);
    },
  });
}

export function useEditReview(fqn: string) {
  const queryClient = useQueryClient();
  const { namespace, localName } = splitAgentFqn(fqn);

  return useMutation({
    mutationFn: ({
      reviewId,
      payload,
    }: {
      reviewId: string;
      payload: ReviewSubmission;
    }) =>
      marketplaceApi.patch<AgentReview>(
        `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}/reviews/${encodeURIComponent(reviewId)}`,
        payload,
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: marketplaceQueryKeys.reviews(fqn),
        }),
        queryClient.invalidateQueries({
          queryKey: marketplaceQueryKeys.agent(namespace, localName),
        }),
      ]);
    },
  });
}
