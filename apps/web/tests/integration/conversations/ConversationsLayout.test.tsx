import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConversationsLayout from "@/app/(main)/conversations/layout";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { renderWithProviders } from "@/test-utils/render";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const { connectionState, mutateAsyncSpy } = vi.hoisted(() => ({
  connectionState: { isConnected: false },
  mutateAsyncSpy: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/hooks/use-conversation-ws", () => ({
  useConversationWs: () => connectionState,
}));

vi.mock("@/lib/hooks/use-send-message", () => ({
  useSendMessage: () => ({
    mutateAsync: mutateAsyncSpy,
  }),
}));

vi.mock("@/lib/hooks/use-goal-ws", () => ({
  useGoalWs: vi.fn(),
}));

vi.mock("@/components/features/goals/GoalFeed", () => ({
  GoalFeed: () => <div>Goal feed</div>,
}));

describe("ConversationsLayout", () => {
  beforeEach(() => {
    connectionState.isConnected = false;
    mutateAsyncSpy.mockClear();
    useConversationStore.getState().reset();
    useWorkspaceStore.setState({
      currentWorkspace: null,
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });
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
    useConversationStore.setState({
      ...useConversationStore.getState(),
      pendingOutboundMessages: [
        {
          id: "optimistic-1",
          content: "Queued guidance",
          conversationId: "conversation-1",
          interactionId: "interaction-1",
          isMidProcessInjection: false,
          retrying: false,
        },
      ],
    });
  });

  it("flushes queued messages after a reconnect transition", async () => {
    const view = renderWithProviders(
      <ConversationsLayout>
        <div>Conversation content</div>
      </ConversationsLayout>,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/reconnecting/i);

    connectionState.isConnected = true;
    view.rerender(
      <ConversationsLayout>
        <div>Conversation content</div>
      </ConversationsLayout>,
    );

    await waitFor(() => {
      expect(mutateAsyncSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          content: "Queued guidance",
          conversationId: "conversation-1",
          interactionId: "interaction-1",
          optimisticId: "optimistic-1",
        }),
      );
    });

    expect(
      useConversationStore.getState().pendingOutboundMessages[0]?.retrying,
    ).toBe(true);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
