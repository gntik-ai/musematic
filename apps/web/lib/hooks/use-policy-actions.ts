"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import type { PolicyBinding } from "@/lib/types/trust-workbench";

interface AttachPolicyInput {
  policyId: string;
  agentId: string;
  agentRevisionId: string;
  policyVersionId?: string | null;
}

interface DetachPolicyInput {
  policyId: string;
  attachmentId: string;
  agentId: string;
}

interface PolicyAttachmentResponse {
  id: string;
  policyId: string;
  policyVersionId: string;
  targetType: string;
  targetId: string | null;
  isActive: boolean;
  createdAt: string;
}

interface RollbackContext {
  previousBindings: Array<[QueryKey, PolicyBinding[] | undefined]>;
}

export function useAttachPolicy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: AttachPolicyInput) =>
      trustWorkbenchApi.post<PolicyAttachmentResponse>(
        `/api/v1/policies/${encodeURIComponent(variables.policyId)}/attach`,
        {
          targetType: "agent_revision",
          targetId: variables.agentRevisionId,
          policyVersionId: variables.policyVersionId ?? null,
        },
      ),
    onSettled: async (_, __, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["effectivePolicies", variables.agentId],
      });
    },
  });
}

export function useDetachPolicy() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, DetachPolicyInput, RollbackContext>({
    mutationFn: async (variables) =>
      trustWorkbenchApi.delete<void>(
        `/api/v1/policies/${encodeURIComponent(variables.policyId)}/attach/${encodeURIComponent(variables.attachmentId)}`,
      ),
    onMutate: async (variables) => {
      const matching = queryClient.getQueriesData<PolicyBinding[]>({
        queryKey: ["effectivePolicies", variables.agentId],
      });

      await Promise.all(
        matching.map(async ([queryKey]) => {
          await queryClient.cancelQueries({ queryKey });
          queryClient.setQueryData<PolicyBinding[]>(
            queryKey,
            (current) =>
              current?.filter(
                (binding) => binding.attachmentId !== variables.attachmentId,
              ) ?? [],
          );
        }),
      );

      return { previousBindings: matching };
    },
    onError: (_, __, context) => {
      context?.previousBindings.forEach(([queryKey, bindings]) => {
        queryClient.setQueryData(queryKey, bindings);
      });
    },
    onSettled: async (_, __, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["effectivePolicies", variables.agentId],
      });
    },
  });
}
