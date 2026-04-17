"use client";

import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { toast } from "@/lib/hooks/use-toast";
import { queryKeys, type Message, type PaginatedMessageResponse } from "@/types/conversations";
import { useAuthStore } from "@/store/auth-store";
import { useConversationStore } from "@/lib/stores/conversation-store";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface SendMessageVariables {
  conversationId: string;
  interactionId: string;
  content: string;
  optimisticId?: string;
  isMidProcessInjection?: boolean;
}

function appendOptimisticMessage(
  current:
    | InfiniteData<PaginatedMessageResponse<Message>, string | null>
    | undefined,
  message: Message,
) {
  if (!current) {
    return {
      pages: [{ items: [message], next_cursor: null }],
      pageParams: [null],
    };
  }

  const pages = [...current.pages];
  const lastPage = pages[pages.length - 1];
  if (!lastPage) {
    return current;
  }

  pages[pages.length - 1] = {
    ...lastPage,
    items: [...lastPage.items, message],
  };

  return { ...current, pages };
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  const isAgentProcessing = useConversationStore((state) => state.isAgentProcessing);
  const markOutboundMessageRetrying = useConversationStore(
    (state) => state.markOutboundMessageRetrying,
  );
  const realtimeConnectionDegraded = useConversationStore(
    (state) => state.realtimeConnectionDegraded,
  );
  const queueOutboundMessage = useConversationStore(
    (state) => state.queueOutboundMessage,
  );
  const removeOutboundMessage = useConversationStore(
    (state) => state.removeOutboundMessage,
  );
  const user = useAuthStore((state) => state.user);

  return {
    mutateAsync: async ({
      content,
      conversationId,
      interactionId,
      isMidProcessInjection,
      optimisticId: providedOptimisticId,
    }: SendMessageVariables) => {
      const midProcessInjection = isMidProcessInjection ?? isAgentProcessing;
      const optimisticId = providedOptimisticId ?? `optimistic-${Date.now()}`;
      const queryKey = queryKeys.messages(conversationId, null, interactionId);
      const previous = queryClient.getQueryData<
        InfiniteData<PaginatedMessageResponse<Message>, string | null>
      >(queryKey);
      const now = new Date().toISOString();

      const optimisticMessage: Message = {
        id: optimisticId,
        conversation_id: conversationId,
        interaction_id: interactionId,
        sender_type: "user",
        sender_id: user?.id ?? "current-user",
        sender_display_name: user?.displayName ?? "You",
        content,
        attachments: [],
        status: "streaming",
        is_mid_process_injection: midProcessInjection,
        branch_origin: null,
        created_at: now,
        updated_at: now,
      };

      if (!providedOptimisticId) {
        queryClient.setQueryData(queryKey, (current:
          | InfiniteData<PaginatedMessageResponse<Message>, string | null>
          | undefined) => appendOptimisticMessage(current, optimisticMessage));
      }

      if (realtimeConnectionDegraded && !providedOptimisticId) {
        queueOutboundMessage({
          id: optimisticId,
          content,
          conversationId,
          interactionId,
          isMidProcessInjection: midProcessInjection,
        });
        toast({
          title: "Message queued",
          description: "The message will be retried when the connection returns.",
        });
        return optimisticMessage;
      }

      try {
        const response = await api.post<Message>(
          `/api/v1/interactions/${interactionId}/messages`,
          {
            content,
            is_mid_process_injection: midProcessInjection,
          },
        );

        queryClient.setQueryData(queryKey, (
          current:
            | InfiniteData<PaginatedMessageResponse<Message>, string | null>
            | undefined,
        ) => {
          if (!current) {
            return {
              pages: [{ items: [response], next_cursor: null }],
              pageParams: [null],
            };
          }

          return {
            ...current,
            pages: current.pages.map((page) => ({
              ...page,
              items: page.items.map((item) =>
                item.id === optimisticId ? response : item,
              ),
            })),
          };
        });

        removeOutboundMessage(optimisticId);
        return response;
      } catch (error) {
        if (providedOptimisticId) {
          markOutboundMessageRetrying(optimisticId, false);
        }
        queryClient.setQueryData(queryKey, previous);
        toast({
          title: "Message failed",
          description: "The message could not be sent.",
          variant: "destructive",
        });
        throw error;
      }
    },
  };
}
