import type { PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  type InfiniteData,
} from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import {
  appendBranchTabFromEvent,
  useConversationWs,
} from "@/lib/hooks/use-conversation-ws";
import { useGoalWs } from "@/lib/hooks/use-goal-ws";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import {
  queryKeys,
  type GoalMessage,
  type Message,
  type PaginatedMessageResponse,
  type WorkspaceGoal,
} from "@/types/conversations";

const {
  addStreamDeltaSpy,
  clearStreamSpy,
  wsState,
} = vi.hoisted(() => ({
  addStreamDeltaSpy: vi.fn(),
  clearStreamSpy: vi.fn(),
  wsState: {
    connectionHandler: null as ((isConnected: boolean) => void) | null,
    connectionState: "connected",
    subscriptions: new Map<string, (event: { payload: unknown }) => void>(),
  },
}));

vi.mock("@/lib/hooks/use-message-stream", () => ({
  addStreamDelta: addStreamDeltaSpy,
  clearStream: clearStreamSpy,
}));

vi.mock("@/lib/ws", () => ({
  wsClient: {
    get connectionState() {
      return wsState.connectionState;
    },
    subscribe: (channel: string, handler: (event: { payload: unknown }) => void) => {
      wsState.subscriptions.set(channel, handler);
      return () => {
        wsState.subscriptions.delete(channel);
      };
    },
    onConnectionChange: (handler: (isConnected: boolean) => void) => {
      wsState.connectionHandler = handler;
      handler(wsState.connectionState === "connected");
      return () => {
        if (wsState.connectionHandler === handler) {
          wsState.connectionHandler = null;
        }
      };
    },
  },
}));

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

describe("conversation websocket hooks", () => {
  beforeEach(() => {
    addStreamDeltaSpy.mockReset();
    clearStreamSpy.mockReset();
    wsState.connectionHandler = null;
    wsState.connectionState = "connected";
    wsState.subscriptions.clear();
    useConversationStore.getState().reset();
  });

  it("applies realtime conversation events to the cache and store", () => {
    const fixtures = getConversationFixtures();
    const client = createTestClient();
    const wrapper = createWrapper(client);
    const invalidateQueriesSpy = vi.spyOn(client, "invalidateQueries");

    client.setQueryData(queryKeys.conversation("conversation-1"), fixtures.conversations[0]);
    client.setQueryData(
      queryKeys.messages("conversation-1", null, "interaction-1"),
      {
        pages: [
          {
            items: fixtures.interactionMessages["interaction-1"] ?? [],
            next_cursor: null,
          },
        ],
        pageParams: [null],
      } satisfies InfiniteData<PaginatedMessageResponse<Message>, string | null>,
    );

    useConversationStore.setState({
      ...useConversationStore.getState(),
      activeBranchId: null,
      activeInteractionId: "interaction-1",
      autoScrollEnabled: false,
    });

    const { result } = renderHook(() => useConversationWs("conversation-1"), {
      wrapper,
    });
    expect(result.current.isConnected).toBe(true);

    const handler = wsState.subscriptions.get("conversation:conversation-1");
    expect(handler).toBeTypeOf("function");
    if (!handler) {
      throw new Error("Expected conversation subscription");
    }

    act(() => {
      handler({
        payload: {
          agent_fqn: "finance-ops:analyzer",
          event_type: "typing.started",
          interaction_id: "interaction-1",
        },
      });
    });
    expect(useConversationStore.getState().isAgentProcessing).toBe(true);

    act(() => {
      handler({
        payload: {
          event_type: "typing.stopped",
          interaction_id: "interaction-1",
        },
      });
    });
    expect(useConversationStore.getState().isAgentProcessing).toBe(false);

    useConversationStore.setState({
      ...useConversationStore.getState(),
      unreadInteractionIds: ["interaction-1"],
    });

    const createdMessage = {
      ...(fixtures.interactionMessages["interaction-2"]?.[0] as Message),
      id: "message-live",
      interaction_id: "interaction-2",
    };

    act(() => {
      handler({
        payload: {
          event_type: "message.created",
          message: createdMessage,
        },
      });
    });

    expect(useConversationStore.getState().pendingMessageCount).toBe(1);
    expect(useConversationStore.getState().unreadInteractionIds).toContain("interaction-2");

    act(() => {
      handler({
        payload: {
          event_type: "message.created",
          message: {
            ...(fixtures.interactionMessages["interaction-1"]?.[0] as Message),
            id: "message-1",
            content: "Updated first message",
          },
        },
      });
    });
    expect(useConversationStore.getState().unreadInteractionIds).not.toContain("interaction-1");

    act(() => {
      handler({
        payload: {
          delta: "partial update",
          event_type: "message.streamed",
          interaction_id: "interaction-1",
          message_id: "message-live",
        },
      });
    });
    expect(addStreamDeltaSpy).toHaveBeenCalledWith("message-live", "partial update");

    act(() => {
      handler({
        payload: {
          event_type: "message.completed",
          message: {
            ...createdMessage,
            content: "final content",
          },
        },
      });
    });
    expect(clearStreamSpy).toHaveBeenCalledWith("message-live");
    expect(useConversationStore.getState().isAgentProcessing).toBe(false);

    act(() => {
      handler({
        payload: {
          event_type: "interaction.state_changed",
          interaction: {
            ...fixtures.conversations[0]?.interactions[0],
            id: "interaction-1",
            state: "completed",
          },
        },
      });
    });
    expect(
      client.getQueryData<{ interactions: Array<{ state: string }> }>(
        queryKeys.conversation("conversation-1"),
      )?.interactions[0]?.state,
    ).toBe("completed");

    act(() => {
      handler({
        payload: {
          branch: {
            ...fixtures.conversations[0]?.branches[0],
            id: "branch-live",
            name: "Fresh branch",
          },
          event_type: "branch.created",
        },
      });
    });
    expect(useConversationStore.getState().branchTabs).toEqual([
      { id: "branch-live", interactionId: null, name: "Fresh branch" },
    ]);
    expect(useConversationStore.getState().unreadBranchIds).toContain("branch-live");

    act(() => {
      handler({
        payload: {
          branch_id: "branch-live",
          event_type: "branch.merged",
          merged_message_ids: ["message-live"],
        },
      });
    });

    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.conversation("conversation-1"),
    });
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: ["messages", "conversation-1"],
    });
  });

  it("tracks degraded websocket state and refreshes on reconnect", () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);
    const invalidateQueriesSpy = vi.spyOn(client, "invalidateQueries");

    wsState.connectionState = "connected";
    renderHook(() => useConversationWs("conversation-1"), { wrapper });

    act(() => {
      wsState.connectionHandler?.(false);
    });
    expect(useConversationStore.getState().realtimeConnectionDegraded).toBe(true);

    act(() => {
      wsState.connectionHandler?.(true);
    });
    expect(useConversationStore.getState().realtimeConnectionDegraded).toBe(false);
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.conversation("conversation-1"),
    });
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: ["messages", "conversation-1"],
    });
  });

  it("handles unknown conversation events and helper-driven branch tab updates", () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);
    wsState.connectionState = "disconnected";

    const { result } = renderHook(() => useConversationWs(null), { wrapper });
    expect(result.current.isConnected).toBe(false);

    renderHook(() => useConversationWs("conversation-1"), { wrapper });
    const handler = wsState.subscriptions.get("conversation:conversation-1");
    if (!handler) {
      throw new Error("Expected conversation subscription");
    }

    act(() => {
      handler({ payload: { event_type: "unsupported" } });
    });

    appendBranchTabFromEvent(useConversationStore.getState().addBranchTab, {
      id: "branch-helper",
      conversation_id: "conversation-1",
      name: "Helper branch",
      description: null,
      originating_message_id: "message-1",
      status: "active",
      created_at: "2026-04-12T10:00:00.000Z",
    });

    expect(useConversationStore.getState().branchTabs).toContainEqual({
      id: "branch-helper",
      interactionId: null,
      name: "Helper branch",
    });
  });

  it("applies goal events to cached goal lists and messages", () => {
    const fixtures = getConversationFixtures();
    const client = createTestClient();
    const wrapper = createWrapper(client);

    client.setQueryData(queryKeys.goals("workspace-1"), {
      items: fixtures.workspaceGoals["workspace-1"] as WorkspaceGoal[],
    });
    client.setQueryData(
      queryKeys.goalMessages("goal-1"),
      {
        pages: [
          {
            items: fixtures.goalMessages["goal-1"] ?? [],
            next_cursor: null,
          },
        ],
        pageParams: [null],
      } satisfies InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>,
    );
    useConversationStore.setState({
      ...useConversationStore.getState(),
      selectedGoalId: "goal-1",
    });

    renderHook(() => useGoalWs("workspace-1"), { wrapper });

    const handler = wsState.subscriptions.get("workspace:workspace-1");
    expect(handler).toBeTypeOf("function");
    if (!handler) {
      throw new Error("Expected workspace subscription");
    }

    act(() => {
      handler({
        payload: {
          event_type: "goal.message_created",
          message: {
            id: "goal-message-live",
            goal_id: "goal-1",
            sender_type: "agent",
            sender_id: "finance-ops:analyzer",
            sender_display_name: "Finance Analyzer",
            agent_fqn: "finance-ops:analyzer",
            content: "Live goal update",
            originating_interaction_id: "interaction-1",
            created_at: "2026-04-12T10:05:00.000Z",
          },
        },
      });
    });

    const updatedMessages = client.getQueryData<
      InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>
    >(queryKeys.goalMessages("goal-1"));
    expect(updatedMessages?.pages[0]?.items.at(-1)?.id).toBe("goal-message-live");

    act(() => {
      handler({
        payload: {
          event_type: "goal.state_changed",
          goal: {
            ...(fixtures.workspaceGoals["workspace-1"]?.[0] as WorkspaceGoal),
            id: "goal-1",
            status: "completed",
          },
        },
      });
    });

    expect(
      client.getQueryData<{ items: WorkspaceGoal[] }>(queryKeys.goals("workspace-1"))?.items[0]
        ?.status,
    ).toBe("completed");
    expect(useConversationStore.getState().selectedGoalId).toBe("goal-1");
  });

  it("gracefully ignores empty goal caches and unsupported events", () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);

    renderHook(() => useGoalWs(null), { wrapper });
    expect(wsState.subscriptions.has("workspace:null")).toBe(false);

    client.setQueryData(queryKeys.goalMessages("goal-1"), {
      pages: [],
      pageParams: [],
    } satisfies InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>);

    renderHook(() => useGoalWs("workspace-1"), { wrapper });
    const handler = wsState.subscriptions.get("workspace:workspace-1");
    if (!handler) {
      throw new Error("Expected workspace subscription");
    }

    act(() => {
      handler({
        payload: {
          event_type: "goal.message_created",
          message: {
            id: "goal-message-empty",
            goal_id: "goal-1",
            sender_type: "agent",
            sender_id: "agent-1",
            sender_display_name: "Agent",
            agent_fqn: "agent:one",
            content: "noop",
            originating_interaction_id: null,
            created_at: "2026-04-12T10:00:00.000Z",
          },
        },
      });
      handler({
        payload: {
          event_type: "goal.state_changed",
          goal: {
            id: "goal-1",
            workspace_id: "workspace-1",
            title: "Goal",
            description: null,
            status: "paused",
            created_at: "2026-04-12T10:00:00.000Z",
          },
        },
      });
      handler({
        payload: {
          event_type: "goal.unsupported",
        },
      });
    });

    expect(
      client.getQueryData<InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>>(
        queryKeys.goalMessages("goal-1"),
      )?.pages,
    ).toEqual([]);
    expect(client.getQueryData(queryKeys.goals("workspace-1"))).toBeUndefined();
  });

  it("creates goal message pages when no cache exists yet", () => {
    const client = createTestClient();
    const wrapper = createWrapper(client);

    renderHook(() => useGoalWs("workspace-1"), { wrapper });
    const handler = wsState.subscriptions.get("workspace:workspace-1");
    if (!handler) {
      throw new Error("Expected workspace subscription");
    }

    act(() => {
      handler({
        payload: {
          event_type: "goal.message_created",
          message: {
            id: "goal-message-new",
            goal_id: "goal-2",
            sender_type: "system",
            sender_id: "system",
            sender_display_name: "System",
            agent_fqn: null,
            content: "Queued state change",
            originating_interaction_id: null,
            created_at: "2026-04-12T10:00:00.000Z",
          },
        },
      });
    });

    expect(
      client.getQueryData<InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>>(
        queryKeys.goalMessages("goal-2"),
      )?.pages[0]?.items[0]?.id,
    ).toBe("goal-message-new");
  });
});
