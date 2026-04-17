"use client";

import { useMemo } from "react";
import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery } from "@/lib/hooks/use-api";
import { queryKeys, type Message, type PaginatedMessageResponse } from "@/types/conversations";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface UseMessagesOptions {
  conversationId: string;
  interactionId: string | null | undefined;
  branchId?: string | null;
  limit?: number;
}

export function sortMessagesByCreatedAt(messages: Message[]) {
  return [...messages].sort(
    (left, right) =>
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime(),
  );
}

export function useMessages({
  conversationId,
  interactionId,
  branchId = null,
  limit = 50,
}: UseMessagesOptions) {
  const query = useAppInfiniteQuery<
    PaginatedMessageResponse<Message>,
    string | null
  >(
    queryKeys.messages(conversationId, branchId, interactionId),
    (cursor) => {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (cursor) {
        params.set("cursor", cursor);
      }

      const queryString = params.toString();
      if (branchId) {
        return api.get<PaginatedMessageResponse<Message>>(
          `/api/v1/conversations/${conversationId}/branches/${branchId}/messages?${queryString}`,
        );
      }

      return api.get<PaginatedMessageResponse<Message>>(
        `/api/v1/interactions/${interactionId}/messages?${queryString}`,
      );
    },
    {
      enabled: Boolean(conversationId) && Boolean(branchId || interactionId),
      getNextPageParam: (page) => page.next_cursor,
    },
  );

  const messages = useMemo(() => {
    const items = query.data?.pages.flatMap((page) => page.items) ?? [];
    return sortMessagesByCreatedAt(items);
  }, [query.data]);

  return {
    ...query,
    messages,
  };
}
