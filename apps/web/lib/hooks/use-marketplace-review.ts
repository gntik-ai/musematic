"use client";

/**
 * UPD-049 — TanStack Query hooks for the platform-staff marketplace
 * review queue (US1).
 *
 * Endpoints under `/api/v1/admin/marketplace-review/*` per
 * `specs/099-marketplace-scope/contracts/admin-marketplace-review-rest.md`.
 *
 * All mutations invalidate the queue on success so the UI reflects
 * the row's new state without an explicit refetch.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type {
  ReviewApprovalRequest,
  ReviewQueueResponse,
  ReviewRejectionRequest,
} from "@/lib/marketplace/types";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const marketplaceReviewKeys = {
  queue: (filter?: ReviewQueueFilter) =>
    ["admin", "marketplace-review", "queue", filter ?? {}] as const,
};

export interface ReviewQueueFilter {
  claimedBy?: string;
  unclaimedOnly?: boolean;
  cursor?: string | null;
  limit?: number;
}

function queuePath(filter: ReviewQueueFilter | undefined): string {
  const params = new URLSearchParams();
  if (filter?.claimedBy) params.set("claimed_by", filter.claimedBy);
  if (filter?.unclaimedOnly) params.set("unclaimed", "true");
  if (filter?.cursor) params.set("cursor", filter.cursor);
  if (filter?.limit) params.set("limit", String(filter.limit));
  const query = params.toString();
  return `/api/v1/admin/marketplace-review/queue${query ? `?${query}` : ""}`;
}

export function useReviewQueue(filter?: ReviewQueueFilter) {
  return useAppQuery<ReviewQueueResponse>(
    marketplaceReviewKeys.queue(filter),
    () => adminApi.get<ReviewQueueResponse>(queuePath(filter)),
  );
}

function invalidateQueue(client: ReturnType<typeof useQueryClient>) {
  client.invalidateQueries({
    queryKey: ["admin", "marketplace-review", "queue"],
  });
}

export function useClaimReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) =>
      adminApi.post(`/api/v1/admin/marketplace-review/${agentId}/claim`, {}),
    onSuccess: () => invalidateQueue(client),
  });
}

export function useReleaseReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) =>
      adminApi.post(`/api/v1/admin/marketplace-review/${agentId}/release`, {}),
    onSuccess: () => invalidateQueue(client),
  });
}

export function useApproveReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { agentId: string; body: ReviewApprovalRequest }) =>
      adminApi.post(
        `/api/v1/admin/marketplace-review/${input.agentId}/approve`,
        input.body,
      ),
    onSuccess: () => invalidateQueue(client),
  });
}

export function useRejectReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { agentId: string; body: ReviewRejectionRequest }) =>
      adminApi.post(
        `/api/v1/admin/marketplace-review/${input.agentId}/reject`,
        input.body,
      ),
    onSuccess: () => invalidateQueue(client),
  });
}
