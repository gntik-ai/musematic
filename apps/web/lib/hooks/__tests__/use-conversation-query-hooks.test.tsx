import type { PropsWithChildren } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { useConversation, useInteraction } from "@/lib/hooks/use-conversation";
import { sortMessagesByCreatedAt, useMessages } from "@/lib/hooks/use-messages";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { queryKeys, type Message } from "@/types/conversations";

function createTestClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 0,
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function createWrapper(client: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <ThemeProvider>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </ThemeProvider>
    );
  };
}

describe("conversation query hooks", () => {
  beforeEach(() => {
    const client = createTestClient();
    client.clear();
  });

  it("fetches a conversation only when an id is provided", async () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);

    const disabled = renderHook(() => useConversation(null), { wrapper });
    expect(disabled.result.current.data).toBeUndefined();
    expect(disabled.result.current.fetchStatus).toBe("idle");

    const enabled = renderHook(() => useConversation("conversation-1"), { wrapper });
    await waitFor(() => {
      expect(enabled.result.current.isSuccess).toBe(true);
      expect(enabled.result.current.data?.id).toBe("conversation-1");
    }, { timeout: 3000 });
    expect(enabled.result.current.data?.interactions).toHaveLength(2);
  });

  it("reads interactions from the query cache", async () => {
    const fixtures = getConversationFixtures();
    const client = createTestClient();
    const wrapper = createWrapper(client);

    client.setQueryData(queryKeys.conversation("conversation-1"), fixtures.conversations[0]);

    const found = renderHook(() => useInteraction("interaction-2"), { wrapper });
    expect(found.result.current?.id).toBe("interaction-2");

    const missing = renderHook(() => useInteraction("missing"), { wrapper });
    expect(missing.result.current).toBeNull();

    const disabled = renderHook(() => useInteraction(null), { wrapper });
    expect(disabled.result.current).toBeNull();
  });

  it("loads interaction and branch messages and sorts them chronologically", async () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);

    const interactionMessages = renderHook(
      () =>
        useMessages({
          conversationId: "conversation-1",
          interactionId: "interaction-1",
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(interactionMessages.result.current.messages).toHaveLength(3);
    });
    expect(interactionMessages.result.current.messages.map((message) => message.id)).toEqual([
      "message-1",
      "message-2",
      "message-3",
    ]);

    const branchMessages = renderHook(
      () =>
        useMessages({
          branchId: "branch-1",
          conversationId: "conversation-1",
          interactionId: "interaction-1",
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(branchMessages.result.current.messages).toHaveLength(2);
    });
    expect(branchMessages.result.current.messages.map((message) => message.id)).toEqual([
      "branch-message-1",
      "branch-message-2",
    ]);
  });

  it("sorts messages by created_at ascending", () => {
    const unsorted = [
      { id: "message-2", created_at: "2026-04-12T10:02:00.000Z" },
      { id: "message-1", created_at: "2026-04-12T10:01:00.000Z" },
      { id: "message-3", created_at: "2026-04-12T10:03:00.000Z" },
    ] as Message[];

    expect(sortMessagesByCreatedAt(unsorted).map((message) => message.id)).toEqual([
      "message-1",
      "message-2",
      "message-3",
    ]);
  });
});
