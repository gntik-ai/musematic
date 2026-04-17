"use client";

import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery } from "@/lib/hooks/use-api";
import { useWorkspaceStore } from "@/store/workspace-store";
import {
  normalizeWorkflowListResponse,
  type WorkflowDefinition,
  type WorkflowListResponse,
} from "@/types/workflows";
import type { CursorPaginatedResponse } from "@/types/api";

const workflowsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const workflowQueryKeys = {
  list: (workspaceId: string | null | undefined, limit: number) =>
    ["workflows", "list", workspaceId ?? "none", limit] as const,
  detail: (workflowId: string, versionId?: string | null) =>
    ["workflows", "detail", workflowId, versionId ?? "current"] as const,
  schema: () => ["workflows", "schema"] as const,
  executions: (workflowId: string | null | undefined, limit: number) =>
    ["executions", "list", workflowId ?? "none", limit] as const,
  execution: (executionId: string) => ["executions", "detail", executionId] as const,
  executionState: (executionId: string) =>
    ["executions", "state", executionId] as const,
  journal: (
    executionId: string,
    filters: Record<string, string | number | null | undefined>,
  ) => ["executions", "journal", executionId, filters] as const,
  stepDetail: (executionId: string, stepId: string | null | undefined) =>
    ["executions", "step-detail", executionId, stepId ?? "none"] as const,
  reasoningTrace: (executionId: string, stepId: string | null | undefined) =>
    ["executions", "reasoning-trace", executionId, stepId ?? "none"] as const,
  taskPlan: (executionId: string, stepId: string | null | undefined) =>
    ["executions", "task-plan", executionId, stepId ?? "none"] as const,
  analyticsUsage: (executionId: string | null | undefined) =>
    ["analytics", "usage", executionId ?? "none"] as const,
};

export interface UseWorkflowListOptions {
  workspaceId?: string | null;
  limit?: number;
  enabled?: boolean;
}

function buildWorkflowListPath(
  workspaceId: string,
  cursor: string | null,
  limit: number,
): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    limit: String(limit),
  });

  if (cursor) {
    searchParams.set("cursor", cursor);
  }

  return `/api/v1/workflows?${searchParams.toString()}`;
}

export function useWorkflowList(options: UseWorkflowListOptions = {}) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const workspaceId = options.workspaceId ?? currentWorkspaceId;
  const limit = options.limit ?? 20;
  const enabled = (options.enabled ?? true) && Boolean(workspaceId);

  return useAppInfiniteQuery<CursorPaginatedResponse<WorkflowDefinition>, string | null>(
    workflowQueryKeys.list(workspaceId, limit),
    async (cursor) => {
      const response = await workflowsApi.get<WorkflowListResponse>(
        buildWorkflowListPath(workspaceId ?? "", cursor ?? null, limit),
      );
      return normalizeWorkflowListResponse(response);
    },
    {
      enabled,
      initialCursor: null,
      getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    },
  );
}
