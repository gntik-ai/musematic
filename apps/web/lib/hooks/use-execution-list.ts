"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery, useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  normalizeExecution,
  normalizeExecutionListResponse,
  normalizeExecutionState,
  type ExecutionListResponse,
  type ExecutionResponse,
  type Execution,
  type ExecutionStateResponse,
  type ExecutionState,
} from "@/types/execution";
import type { CursorPaginatedResponse } from "@/types/api";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildExecutionListPath(
  workflowId: string,
  cursor: string | null,
  limit: number,
): string {
  const searchParams = new URLSearchParams({
    workflow_id: workflowId,
    limit: String(limit),
  });

  if (cursor) {
    searchParams.set("cursor", cursor);
  }

  return `/api/v1/executions?${searchParams.toString()}`;
}

export interface UseExecutionListOptions {
  limit?: number;
  enabled?: boolean;
}

export interface StartExecutionInput {
  workflowVersionId: string;
}

export function useExecutionList(
  workflowId: string | null | undefined,
  options: UseExecutionListOptions = {},
) {
  const limit = options.limit ?? 20;
  const enabled = (options.enabled ?? true) && Boolean(workflowId);

  return useAppInfiniteQuery<CursorPaginatedResponse<Execution>, string | null>(
    workflowQueryKeys.executions(workflowId, limit),
    async (cursor) => {
      const response = await executionsApi.get<ExecutionListResponse>(
        buildExecutionListPath(workflowId ?? "", cursor ?? null, limit),
      );
      return normalizeExecutionListResponse(response);
    },
    {
      enabled,
      initialCursor: null,
      getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    },
  );
}

export function useExecution(executionId: string | null | undefined) {
  return useAppQuery(
    workflowQueryKeys.execution(executionId ?? ""),
    async () => normalizeExecution(await executionsApi.get<ExecutionResponse>(
      `/api/v1/executions/${encodeURIComponent(executionId ?? "")}`,
    )),
    {
      enabled: Boolean(executionId),
    },
  );
}

export function useExecutionState(executionId: string | null | undefined) {
  return useAppQuery<ExecutionState>(
    workflowQueryKeys.executionState(executionId ?? ""),
    async () => normalizeExecutionState(await executionsApi.get<ExecutionStateResponse>(
      `/api/v1/executions/${encodeURIComponent(executionId ?? "")}/state`,
    )),
    {
      enabled: Boolean(executionId),
    },
  );
}

export function useStartExecution(workflowId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ workflowVersionId }: StartExecutionInput) =>
      normalizeExecution(
        await executionsApi.post<ExecutionResponse>("/api/v1/executions", {
          workflow_version_id: workflowVersionId,
          trigger_type: "manual",
        }),
      ),
    onSuccess: async (execution) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["executions", "list", workflowId],
        }),
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.execution(execution.id),
        }),
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.executionState(execution.id),
        }),
      ]);
    },
  });
}
