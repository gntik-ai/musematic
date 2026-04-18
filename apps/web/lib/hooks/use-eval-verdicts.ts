"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  evalQueryKeys,
  type BenchmarkCaseListResponse,
  type JudgeVerdictListResponse,
} from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function appendPage(searchParams: URLSearchParams, page?: number): void {
  if (page && page > 0) {
    searchParams.set("page", String(page));
  }
}

export function useEvalSetCases(evalSetId: string, page = 1) {
  return useAppQuery<BenchmarkCaseListResponse>(
    evalQueryKeys.cases(evalSetId, page),
    () => {
      const searchParams = new URLSearchParams();
      appendPage(searchParams, page);
      const suffix = searchParams.toString();
      return evaluationApi.get<BenchmarkCaseListResponse>(
        `/api/v1/evaluations/eval-sets/${encodeURIComponent(evalSetId)}/cases${suffix ? `?${suffix}` : ""}`,
      );
    },
    {
      enabled: Boolean(evalSetId),
    },
  );
}

export function useEvalRunVerdicts(runId: string, page = 1) {
  return useAppQuery<JudgeVerdictListResponse>(
    evalQueryKeys.verdicts(runId, page),
    () => {
      const searchParams = new URLSearchParams();
      appendPage(searchParams, page);
      const suffix = searchParams.toString();
      return evaluationApi.get<JudgeVerdictListResponse>(
        `/api/v1/evaluations/runs/${encodeURIComponent(runId)}/verdicts${suffix ? `?${suffix}` : ""}`,
      );
    },
    {
      enabled: Boolean(runId),
    },
  );
}
