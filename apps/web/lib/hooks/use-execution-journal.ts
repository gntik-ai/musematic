"use client";

import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  normalizeExecutionJournalPage,
  type ExecutionEventType,
  type ExecutionJournalResponse,
  type ExecutionJournalPage,
} from "@/types/execution";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface ExecutionJournalFilters {
  sinceSequence?: number;
  eventType?: ExecutionEventType;
  stepId?: string | null;
  limit?: number;
  enabled?: boolean;
}

function buildExecutionJournalPath(
  executionId: string,
  offset: number,
  filters: ExecutionJournalFilters,
): string {
  const searchParams = new URLSearchParams({
    limit: String(filters.limit ?? 50),
    offset: String(offset),
  });

  if (filters.sinceSequence !== undefined) {
    searchParams.set("since_sequence", String(filters.sinceSequence));
  }

  if (filters.eventType) {
    searchParams.set("event_type", filters.eventType);
  }

  if (filters.stepId) {
    searchParams.set("step_id", filters.stepId);
  }

  return `/api/v1/executions/${encodeURIComponent(executionId)}/journal?${searchParams.toString()}`;
}

export function useExecutionJournal(
  executionId: string | null | undefined,
  filters: ExecutionJournalFilters = {},
) {
  const limit = filters.limit ?? 50;
  const enabled = (filters.enabled ?? true) && Boolean(executionId);

  return useAppInfiniteQuery<ExecutionJournalPage, number>(
    workflowQueryKeys.journal(executionId ?? "", {
      sinceSequence: filters.sinceSequence ?? null,
      eventType: filters.eventType ?? null,
      stepId: filters.stepId ?? null,
      limit,
    }),
    async (offset) => {
      const response = await executionsApi.get<ExecutionJournalResponse>(
        buildExecutionJournalPath(executionId ?? "", offset ?? 0, {
          ...filters,
          limit,
        }),
      );
      return normalizeExecutionJournalPage(response, offset ?? 0, limit);
    },
    {
      enabled,
      initialCursor: 0,
      getNextPageParam: (lastPage) => lastPage.nextOffset ?? undefined,
    },
  );
}
