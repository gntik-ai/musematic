"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  normalizeWorkflowDefinition,
  type CreateWorkflowInput,
  type UpdateWorkflowInput,
  type WorkflowDefinitionResponse,
} from "@/types/workflows";

const workflowsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateWorkflowInput) => {
      const response = await workflowsApi.post<WorkflowDefinitionResponse>("/api/v1/workflows", {
        workspace_id: payload.workspaceId,
        name: payload.name,
        description: payload.description ?? null,
        yaml_content: payload.yamlContent,
      });

      return normalizeWorkflowDefinition(response);
    },
    onSuccess: async (workflow) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["workflows"] }),
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.detail(workflow.id),
        }),
      ]);
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: UpdateWorkflowInput) => {
      const response = await workflowsApi.patch<WorkflowDefinitionResponse>(
        `/api/v1/workflows/${encodeURIComponent(payload.workflowId)}`,
        {
          yaml_content: payload.yamlContent,
          description: payload.description ?? null,
        },
      );

      return normalizeWorkflowDefinition(response);
    },
    onSuccess: async (workflow) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["workflows"] }),
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.detail(workflow.id),
        }),
      ]);
    },
  });
}
