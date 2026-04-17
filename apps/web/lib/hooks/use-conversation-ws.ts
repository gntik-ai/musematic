"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { wsClient } from "@/lib/ws";
import {
  useConversationStore,
} from "@/lib/stores/conversation-store";
import {
  addStreamDelta,
  clearStream,
} from "@/lib/hooks/use-message-stream";
import {
  queryKeys,
  type Conversation,
  type ConversationBranch,
  type ConversationEventPayload,
  type Interaction,
  type Message,
  type PaginatedMessageResponse,
} from "@/types/conversations";

function createEmptyMessagePages(message: Message): InfiniteData<PaginatedMessageResponse<Message>, string | null> {
  return {
    pages: [{ items: [message], next_cursor: null }],
    pageParams: [null],
  };
}

function appendMessage(
  current:
    | InfiniteData<PaginatedMessageResponse<Message>, string | null>
    | undefined,
  message: Message,
) {
  if (!current) {
    return createEmptyMessagePages(message);
  }

  const pages = [...current.pages];
  const lastPage = pages[pages.length - 1];
  if (!lastPage) {
    return createEmptyMessagePages(message);
  }

  const hasMessage = pages.some((page) =>
    page.items.some((item) => item.id === message.id),
  );
  if (hasMessage) {
    return replaceMessage(current, message);
  }

  pages[pages.length - 1] = {
    ...lastPage,
    items: [...lastPage.items, message],
  };

  return {
    ...current,
    pages,
  };
}

function replaceMessage(
  current:
    | InfiniteData<PaginatedMessageResponse<Message>, string | null>
    | undefined,
  message: Message,
) {
  if (!current) {
    return createEmptyMessagePages(message);
  }

  return {
    ...current,
    pages: current.pages.map((page) => ({
      ...page,
      items: page.items.map((item) => (item.id === message.id ? message : item)),
    })),
  };
}

function updateInteraction(
  conversation: Conversation | undefined,
  interaction: Interaction,
) {
  if (!conversation) {
    return conversation;
  }

  return {
    ...conversation,
    interactions: conversation.interactions.map((item) =>
      item.id === interaction.id ? { ...item, ...interaction } : item,
    ),
  };
}

export function useConversationWs(conversationId: string | null | undefined) {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(
    wsClient.connectionState === "connected",
  );
  const previousConnectionState = useRef(isConnected);
  const activeBranchId = useConversationStore((state) => state.activeBranchId);
  const activeInteractionId = useConversationStore((state) => state.activeInteractionId);
  const autoScrollEnabled = useConversationStore((state) => state.autoScrollEnabled);
  const addBranchTab = useConversationStore((state) => state.addBranchTab);
  const clearInteractionUnread = useConversationStore(
    (state) => state.clearInteractionUnread,
  );
  const incrementPending = useConversationStore((state) => state.incrementPending);
  const markBranchUnread = useConversationStore((state) => state.markBranchUnread);
  const markInteractionUnread = useConversationStore(
    (state) => state.markInteractionUnread,
  );
  const setRealtimeConnectionDegraded = useConversationStore(
    (state) => state.setRealtimeConnectionDegraded,
  );
  const setAgentProcessing = useConversationStore((state) => state.setAgentProcessing);

  const channel = useMemo(
    () => (conversationId ? `conversation:${conversationId}` : null),
    [conversationId],
  );

  useEffect(() => wsClient.onConnectionChange(setIsConnected), []);

  useEffect(() => {
    const wasConnected = previousConnectionState.current;
    previousConnectionState.current = isConnected;

    setRealtimeConnectionDegraded(wasConnected && !isConnected);

    if (!conversationId || wasConnected || !isConnected) {
      return;
    }

    void Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversation(conversationId),
      }),
      queryClient.invalidateQueries({
        queryKey: ["messages", conversationId],
      }),
    ]);
  }, [conversationId, isConnected, queryClient, setRealtimeConnectionDegraded]);

  useEffect(() => {
    if (!conversationId || !channel) {
      return undefined;
    }

    const unsubscribe = wsClient.subscribe(channel, (event) => {
      const payload = event.payload as ConversationEventPayload;

      switch (payload.event_type) {
        case "typing.started":
          setAgentProcessing(true, payload.interaction_id);
          return;
        case "typing.stopped":
          setAgentProcessing(false, null);
          return;
        case "message.created": {
          queryClient.setQueryData(
            queryKeys.messages(
              conversationId,
              null,
              payload.message.interaction_id,
            ),
            (
              current:
                | InfiniteData<PaginatedMessageResponse<Message>, string | null>
                | undefined,
            ) => appendMessage(current, payload.message),
          );

          if (!autoScrollEnabled) {
            incrementPending();
          }

          if (payload.message.interaction_id !== activeInteractionId || activeBranchId !== null) {
            markInteractionUnread(payload.message.interaction_id);
          } else {
            clearInteractionUnread(payload.message.interaction_id);
          }

          return;
        }
        case "message.streamed":
          addStreamDelta(payload.message_id, payload.delta);
          return;
        case "message.completed":
          queryClient.setQueryData(
            queryKeys.messages(
              conversationId,
              null,
              payload.message.interaction_id,
            ),
            (
              current:
                | InfiniteData<PaginatedMessageResponse<Message>, string | null>
                | undefined,
            ) => replaceMessage(current, payload.message),
          );
          clearStream(payload.message.id);
          setAgentProcessing(false, null);
          return;
        case "interaction.state_changed":
          queryClient.setQueryData(
            queryKeys.conversation(conversationId),
            (current: Conversation | undefined) =>
              updateInteraction(current, payload.interaction),
          );
          return;
        case "branch.created":
          addBranchTab(payload.branch);
          queryClient.invalidateQueries({
            queryKey: queryKeys.conversation(conversationId),
          });
          if (activeBranchId !== payload.branch.id) {
            markBranchUnread(payload.branch.id);
          }
          return;
        case "branch.merged":
          queryClient.invalidateQueries({
            queryKey: ["messages", conversationId],
          });
          return;
        default:
          return;
      }
    });

    return () => {
      unsubscribe();
    };
  }, [
    activeBranchId,
    activeInteractionId,
    addBranchTab,
    autoScrollEnabled,
    channel,
    clearInteractionUnread,
    conversationId,
    incrementPending,
    markBranchUnread,
    markInteractionUnread,
    queryClient,
    setAgentProcessing,
  ]);

  return { isConnected };
}

export function appendBranchTabFromEvent(
  addBranchTab: (branch: ConversationBranch) => void,
  branch: ConversationBranch,
) {
  addBranchTab(branch);
}
