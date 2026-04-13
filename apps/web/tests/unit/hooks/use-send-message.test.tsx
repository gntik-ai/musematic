import type { PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { useSendMessage } from "@/lib/hooks/use-send-message";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { queryKeys } from "@/types/conversations";
import { useAuthStore } from "@/store/auth-store";

const { postSpy, toastSpy } = vi.hoisted(() => ({
  postSpy: vi.fn(),
  toastSpy: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  createApiClient: () => ({
    post: postSpy,
  }),
}));

vi.mock("@/lib/hooks/use-toast", () => ({
  toast: toastSpy,
}));

function createTestClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
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

describe("useSendMessage", () => {
  beforeEach(() => {
    postSpy.mockReset();
    toastSpy.mockReset();
    useConversationStore.getState().reset();
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "alex@example.com",
        displayName: "Alex Mercer",
        avatarUrl: null,
        roles: ["workspace_owner"],
        workspaceId: "workspace-1",
        mfaEnrolled: true,
      },
    });
  });

  it("queues optimistic messages when realtime connectivity is degraded", async () => {
    const client = createTestClient();
    useConversationStore.setState({
      ...useConversationStore.getState(),
      realtimeConnectionDegraded: true,
    });

    const { result } = renderHook(() => useSendMessage(), {
      wrapper: createWrapper(client),
    });

    await act(async () => {
      await result.current.mutateAsync({
        content: "Retry this when the socket returns",
        conversationId: "conversation-1",
        interactionId: "interaction-1",
      });
    });

    expect(postSpy).not.toHaveBeenCalled();
    expect(useConversationStore.getState().pendingOutboundMessages).toEqual([
      expect.objectContaining({
        content: "Retry this when the socket returns",
        conversationId: "conversation-1",
        interactionId: "interaction-1",
        retrying: false,
      }),
    ]);

    const messagePages = client.getQueryData<{
      pages: Array<{ items: Array<{ content: string }> }>;
    }>(queryKeys.messages("conversation-1", null, "interaction-1"));
    expect(messagePages?.pages[0]?.items[0]?.content).toBe(
      "Retry this when the socket returns",
    );
    expect(toastSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Message queued",
      }),
    );
  });
});
