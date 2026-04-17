"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  normalizeWorkflowDefinition,
  normalizeWorkflowVersion,
  type WorkflowDefinition,
  type WorkflowDefinitionResponse,
  type WorkflowVersionResponse,
  type WorkflowVersion,
} from "@/types/workflows";

const workflowsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface WorkflowDetailResult {
  workflow: WorkflowDefinition;
  version: WorkflowVersion;
}

export function useWorkflow(
  workflowId: string | null | undefined,
  versionId?: string | null,
) {
  return useAppQuery(
    workflowQueryKeys.detail(workflowId ?? "", versionId),
    async (): Promise<WorkflowDetailResult> => {
      const workflowResponse = await workflowsApi.get<WorkflowDefinitionResponse>(
        `/api/v1/workflows/${encodeURIComponent(workflowId ?? "")}`,
      );
      const workflow = normalizeWorkflowDefinition(workflowResponse);
      const resolvedVersionId = versionId ?? workflow.currentVersionId;
      const versionResponse = await workflowsApi.get<WorkflowVersionResponse>(
        `/api/v1/workflows/${encodeURIComponent(workflow.id)}/versions/${encodeURIComponent(resolvedVersionId)}`,
      );

      return {
        workflow,
        version: normalizeWorkflowVersion(versionResponse),
      };
    },
    {
      enabled: Boolean(workflowId),
    },
  );
}
