"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { queryKeys, type ConversationBranch } from "@/types/conversations";
import { useConversationStore } from "@/lib/stores/conversation-store";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface CreateBranchVariables {
  conversationId: string;
  originating_message_id: string;
  name: string;
  description?: string | undefined;
}

interface MergeBranchVariables {
  conversationId: string;
  branchId: string;
  message_ids: string[];
}

export function useCreateBranch() {
  const queryClient = useQueryClient();
  const addBranchTab = useConversationStore((state) => state.addBranchTab);

  return {
    mutateAsync: async (variables: CreateBranchVariables) => {
      const branch = await api.post<ConversationBranch>(
        `/api/v1/conversations/${variables.conversationId}/branches`,
        variables,
      );
      addBranchTab(branch);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.conversation(variables.conversationId),
      });
      return branch;
    },
  };
}

export function useMergeBranch() {
  const queryClient = useQueryClient();

  return {
    mutateAsync: async ({
      branchId,
      conversationId,
      message_ids,
    }: MergeBranchVariables) => {
      const response = await api.post<{ success: boolean }>(
        `/api/v1/conversations/${conversationId}/branches/${branchId}/merge`,
        { message_ids },
      );

      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["messages", conversationId],
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.conversation(conversationId),
        }),
      ]);

      return response;
    },
  };
}
