"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import { normalizeStepDetail, type StepDetail } from "@/types/execution";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useStepDetail(
  executionId: string | null | undefined,
  stepId: string | null | undefined,
) {
  return useAppQuery<StepDetail>(
    workflowQueryKeys.stepDetail(executionId ?? "", stepId),
    async () => normalizeStepDetail(await executionsApi.get(
      `/api/v1/executions/${encodeURIComponent(executionId ?? "")}/steps/${encodeURIComponent(stepId ?? "")}`,
    )),
    {
      enabled: Boolean(executionId && stepId),
    },
  );
}
