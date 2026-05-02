"use client";

/**
 * UPD-049 — TanStack Query mutation for the fork operation (US5).
 *
 * Endpoint: `POST /api/v1/registry/agents/{source_id}/fork` per
 * `specs/099-marketplace-scope/contracts/fork-rest.md`.
 */

import { useMutation } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type { ForkAgentRequest, ForkAgentResponse } from "@/lib/marketplace/types";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useForkAgent() {
  return useMutation<
    ForkAgentResponse,
    unknown,
    { sourceId: string; body: ForkAgentRequest }
  >({
    mutationFn: async ({ sourceId, body }) =>
      api.post<ForkAgentResponse>(
        `/api/v1/registry/agents/${sourceId}/fork`,
        body,
      ),
  });
}
