"use client";

import { useQueryClient, useMutation } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { VisibilityGrant } from "@/types/governance";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface VisibilityGrantResponse {
  workspace_id: string;
  visibility_agents: string[];
  visibility_tools: string[];
  updated_at: string;
}

function normalizeGrants(payload: VisibilityGrantResponse): VisibilityGrant[] {
  return payload.visibility_agents.map((pattern) => ({
    id: `${payload.workspace_id}:${pattern}`,
    workspaceId: payload.workspace_id,
    pattern,
    createdBy: "system",
    createdAt: payload.updated_at,
  }));
}

export function useVisibilityGrants(workspaceId: string | null | undefined) {
  const query = useAppQuery<VisibilityGrant[]>(
    ["visibility-grants", workspaceId ?? "none"],
    async () =>
      normalizeGrants(
        await api.get<VisibilityGrantResponse>(
          `/api/v1/workspaces/${workspaceId}/visibility`,
        ),
      ),
    { enabled: Boolean(workspaceId) },
  );

  return {
    ...query,
    grants: query.data ?? [],
  };
}

export function useVisibilityGrantMutations(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (patterns: string[]) =>
      api.put<VisibilityGrantResponse>(
        `/api/v1/workspaces/${workspaceId}/visibility`,
        {
          visibility_agents: patterns,
          visibility_tools: [],
        },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["visibility-grants", workspaceId ?? "none"],
      });
    },
  });
}
