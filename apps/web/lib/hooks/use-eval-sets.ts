"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  DEFAULT_EVAL_LIST_FILTERS,
  evalQueryKeys,
  type EvalListFilters,
  type EvalSetListResponse,
  type EvalSetResponse,
} from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildEvalSetsPath(workspaceId: string, filters: EvalListFilters): string {
  const resolvedFilters = {
    ...DEFAULT_EVAL_LIST_FILTERS,
    ...filters,
  };
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    page: String(resolvedFilters.page),
  });

  if (resolvedFilters.status !== "all") {
    searchParams.set("status", resolvedFilters.status);
  }
  if (resolvedFilters.search.trim().length > 0) {
    searchParams.set("search", resolvedFilters.search.trim());
  }

  return `/api/v1/evaluations/eval-sets?${searchParams.toString()}`;
}

export function useEvalSets(
  workspaceId: string,
  filters: EvalListFilters,
) {
  return useAppQuery<EvalSetListResponse>(
    evalQueryKeys.evalSets(workspaceId, filters),
    () => evaluationApi.get<EvalSetListResponse>(buildEvalSetsPath(workspaceId, filters)),
    {
      enabled: Boolean(workspaceId),
      staleTime: 30_000,
    },
  );
}

export function useEvalSet(evalSetId: string) {
  return useAppQuery<EvalSetResponse>(
    evalQueryKeys.evalSet(evalSetId),
    () =>
      evaluationApi.get<EvalSetResponse>(
        `/api/v1/evaluations/eval-sets/${encodeURIComponent(evalSetId)}`,
      ),
    {
      enabled: Boolean(evalSetId),
    },
  );
}
