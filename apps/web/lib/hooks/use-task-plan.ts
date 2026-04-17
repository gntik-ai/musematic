"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  normalizeTaskPlanRecord,
  type TaskPlanRecord,
} from "@/types/task-plan";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useTaskPlan(
  executionId: string | null | undefined,
  stepId: string | null | undefined,
  enabled = false,
) {
  return useAppQuery<TaskPlanRecord>(
    workflowQueryKeys.taskPlan(executionId ?? "", stepId),
    async () => normalizeTaskPlanRecord(await executionsApi.get(
      `/api/v1/executions/${encodeURIComponent(executionId ?? "")}/task-plan/${encodeURIComponent(stepId ?? "")}`,
    )),
    {
      enabled: Boolean(executionId && stepId && enabled),
    },
  );
}
