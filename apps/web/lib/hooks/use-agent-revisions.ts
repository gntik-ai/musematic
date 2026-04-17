"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { agentManagementQueryKeys } from "@/lib/hooks/use-agents";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { AgentRevision, RevisionDiff } from "@/lib/types/agent-management";
import type { CursorPaginatedResponse } from "@/types/api";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface AgentRevisionListResponse {
  items: AgentRevision[];
  next_cursor: string | null;
}

function buildRevisionsPath(
  fqn: string,
  workspaceId: string,
  limit: number,
): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    limit: String(limit),
  });

  return `/api/v1/registry/agents/${encodeURIComponent(fqn)}/revisions?${searchParams.toString()}`;
}

export function useAgentRevisions(
  fqn: string | null | undefined,
  limit = 20,
  workspaceId?: string | null,
) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const resolvedWorkspaceId = workspaceId ?? currentWorkspaceId;

  return useAppQuery<CursorPaginatedResponse<AgentRevision>>(
    agentManagementQueryKeys.revisions(resolvedWorkspaceId, fqn ?? ""),
    async () => {
      const response = await registryApi.get<AgentRevisionListResponse>(
        buildRevisionsPath(fqn ?? "", resolvedWorkspaceId ?? "", limit),
      );

      return {
        items: response.items,
        nextCursor: response.next_cursor,
        prevCursor: null,
        total: response.items.length,
      };
    },
    {
      enabled: Boolean(fqn && resolvedWorkspaceId),
    },
  );
}

export function useRevisionDiff(
  fqn: string | null | undefined,
  base: number | null | undefined,
  compare: number | null | undefined,
) {
  return useAppQuery<RevisionDiff>(
    agentManagementQueryKeys.revisionDiff(fqn ?? "", base ?? null, compare ?? null),
    () =>
      registryApi.get<RevisionDiff>(
        `/api/v1/registry/agents/${encodeURIComponent(
          fqn ?? "",
        )}/revisions/${base}/diff/${compare}`,
      ),
    {
      enabled: Boolean(fqn && base != null && compare != null),
    },
  );
}
