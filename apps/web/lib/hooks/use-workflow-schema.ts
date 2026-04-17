"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import type { WorkflowSchema } from "@/types/workflows";

const workflowsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useWorkflowSchema() {
  return useAppQuery<WorkflowSchema>(
    workflowQueryKeys.schema(),
    () => workflowsApi.get("/api/v1/workflows/schema"),
    {
      staleTime: 60 * 60 * 1000,
    },
  );
}
