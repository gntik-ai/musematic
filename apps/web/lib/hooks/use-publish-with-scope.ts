"use client";

/**
 * UPD-049 — TanStack Query mutation for the scope-aware publish flow.
 *
 * Endpoint: `POST /api/v1/registry/agents/{agent_id}/publish` per
 * `specs/099-marketplace-scope/contracts/publish-and-review-rest.md`.
 *
 * The path parameter is the agent UUID (not FQN); the existing
 * `usePublishAgent` hook in `use-agent-mutations.ts` predates UPD-049
 * and is kept intact for callers that don't need scope semantics.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type { PublishWithScopeRequest } from "@/lib/marketplace/types";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface UsePublishWithScopeInput {
  agentId: string;
  body: PublishWithScopeRequest;
}

export function usePublishWithScope() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: UsePublishWithScopeInput) =>
      api.post(`/api/v1/registry/agents/${input.agentId}/publish`, input.body),
    onSuccess: async (_data, input) => {
      // Invalidate the agent-management catalog and detail caches so the
      // UI picks up the new review_status / marketplace_scope.
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["agent-management", "catalog"],
        }),
        queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "agent-management" &&
            query.queryKey[1] === "detail",
        }),
        queryClient.invalidateQueries({
          queryKey: ["admin", "marketplace-review", "queue"],
        }),
      ]);
      void input;
    },
  });
}
