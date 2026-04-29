"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  appendTagLabelFilters,
  EMPTY_TAG_LABEL_FILTERS,
  type TagLabelFilters,
} from "@/lib/tagging/filter-query";
import {
  evalQueryKeys,
  type EvaluationRunListResponse,
  type EvaluationRunResponse,
} from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function buildEvalRunsPath(
  workspaceId: string,
  evalSetId: string | undefined,
  filters: TagLabelFilters,
): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
  });

  if (evalSetId) {
    searchParams.set("eval_set_id", evalSetId);
  }
  appendTagLabelFilters(searchParams, filters);

  return `/api/v1/evaluations/runs?${searchParams.toString()}`;
}

function runRefetchInterval(run: EvaluationRunResponse | undefined): false | number {
  return run && ["completed", "failed"].includes(run.status) ? false : 3_000;
}

export function useEvalRuns(
  workspaceId: string,
  evalSetId?: string,
  filters: TagLabelFilters = EMPTY_TAG_LABEL_FILTERS,
) {
  return useAppQuery<EvaluationRunListResponse>(
    evalQueryKeys.runs(workspaceId, evalSetId, filters),
    () =>
      evaluationApi.get<EvaluationRunListResponse>(
        buildEvalRunsPath(workspaceId, evalSetId, filters),
      ),
    {
      enabled: Boolean(workspaceId),
    },
  );
}

export function useEvalRun(runId: string) {
  return useAppQuery<EvaluationRunResponse>(
    evalQueryKeys.run(runId),
    () =>
      evaluationApi.get<EvaluationRunResponse>(
        `/api/v1/evaluations/runs/${encodeURIComponent(runId)}`,
      ),
    {
      enabled: Boolean(runId),
      refetchInterval: (query) => runRefetchInterval(query.state.data),
    },
  );
}
