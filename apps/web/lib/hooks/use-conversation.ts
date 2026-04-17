"use client";

import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { queryKeys, type Conversation, type ConversationResponse, type Interaction } from "@/types/conversations";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useConversation(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.conversation(conversationId ?? "unknown"),
    queryFn: () =>
      api.get<ConversationResponse>(`/api/v1/conversations/${conversationId}`),
    staleTime: 30_000,
    enabled: Boolean(conversationId),
  });
}

export function useInteraction(interactionId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMemo(() => {
    if (!interactionId) {
      return null;
    }

    const conversations = queryClient
      .getQueryCache()
      .findAll({ queryKey: ["conversation"] })
      .map((query) => query.state.data as Conversation | undefined)
      .filter(Boolean);

    for (const conversation of conversations) {
      const interaction = conversation?.interactions.find(
        (item) => item.id === interactionId,
      );
      if (interaction) {
        return interaction as Interaction;
      }
    }

    return null;
  }, [interactionId, queryClient]);
}
