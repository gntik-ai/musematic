import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import {
  homeQueryKeys,
  useApproveMutation,
  useDashboardWebSocket,
  usePendingActions,
  useRecentActivity,
  useWebSocketStatus,
  useWorkspaceSummary,
} from "@/lib/hooks/use-home-data";
import { homeFixtures } from "@/mocks/handlers/home";
import { server } from "@/vitest.setup";

const wsMock = vi.hoisted(() => {
  const channelHandlers = new Map<
    string,
    Set<(event: { channel: string; type: string; payload: unknown; timestamp: string }) => void>
  >();
  const connectionHandlers = new Set<(isConnected: boolean) => void>();

  const mock = {
    connectionState: "connected" as "connected" | "disconnected",
    subscribe: vi.fn(
      (
        channel: string,
        handler: (event: {
          channel: string;
          type: string;
          payload: unknown;
          timestamp: string;
        }) => void,
      ) => {
        const handlers = channelHandlers.get(channel) ?? new Set();
        handlers.add(handler);
        channelHandlers.set(channel, handlers);
        return () => {
          handlers.delete(handler);
        };
      },
    ),
    onConnectionChange: vi.fn((handler: (isConnected: boolean) => void) => {
      connectionHandlers.add(handler);
      handler(mock.connectionState === "connected");
      return () => {
        connectionHandlers.delete(handler);
      };
    }),
    emit: (channel: string, type: string, payload: unknown) => {
      channelHandlers.get(channel)?.forEach((handler) =>
        handler({
          channel,
          type,
          payload,
          timestamp: new Date().toISOString(),
        }),
      );
    },
    setConnected: (isConnected: boolean) => {
      mock.connectionState = isConnected ? "connected" : "disconnected";
      connectionHandlers.forEach((handler) => handler(isConnected));
    },
    reset: () => {
      channelHandlers.clear();
      connectionHandlers.clear();
      mock.subscribe.mockClear();
      mock.onConnectionChange.mockClear();
      mock.connectionState = "connected";
    },
  };

  return mock;
});

vi.mock("@/lib/ws", () => ({
  wsClient: wsMock,
  WebSocketClient: class {},
}));

describe("useHomeData", () => {
  beforeEach(() => {
    wsMock.reset();
  });

  it("keeps dashboard queries idle until a workspace is selected", () => {
    const { Wrapper } = createHookWrapper();

    const summary = renderHook(() => useWorkspaceSummary(null, { isConnected: false }), {
      wrapper: Wrapper,
    });
    const activity = renderHook(() => useRecentActivity(undefined), {
      wrapper: Wrapper,
    });
    const pending = renderHook(() => usePendingActions(null), {
      wrapper: Wrapper,
    });

    expect(summary.result.current.fetchStatus).toBe("idle");
    expect(activity.result.current.fetchStatus).toBe("idle");
    expect(pending.result.current.fetchStatus).toBe("idle");
  });

  it("tracks websocket connection status changes", () => {
    const { Wrapper } = createHookWrapper();
    wsMock.setConnected(false);

    const { result } = renderHook(() => useWebSocketStatus(), {
      wrapper: Wrapper,
    });

    expect(result.current.isConnected).toBe(false);

    act(() => {
      wsMock.setConnected(true);
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("skips websocket subscriptions when there is no workspace id", () => {
    const { Wrapper } = createHookWrapper();

    renderHook(() => useDashboardWebSocket(null), {
      wrapper: Wrapper,
    });

    expect(wsMock.subscribe).not.toHaveBeenCalled();
  });

  it("invalidates dashboard queries for delivery failures and workspace approvals", async () => {
    const { Wrapper, client } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    renderHook(() => useDashboardWebSocket("workspace-1"), {
      wrapper: Wrapper,
    });

    act(() => {
      wsMock.emit("execution", "execution.failed", null);
      wsMock.emit("execution", "execution.requires_approval", {
        workspace_id: "workspace-1",
      });
      wsMock.emit("workspace", "workspace.approval.resolved", {
        workspaceId: "workspace-1",
      });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: homeQueryKeys.activity("workspace-1"),
      });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: homeQueryKeys.summary("workspace-1"),
      });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: homeQueryKeys.pendingActions("workspace-1"),
      });
    });
  });

  it("ignores execution and interaction events from a different workspace", async () => {
    const { Wrapper, client } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    renderHook(() => useDashboardWebSocket("workspace-1"), {
      wrapper: Wrapper,
    });

    act(() => {
      wsMock.emit("execution", "execution.failed", {
        workspace_id: "workspace-2",
      });
      wsMock.emit("interaction", "interaction.attention.requested", {
        workspaceId: "workspace-2",
      });
    });

    await waitFor(() => {
      expect(invalidateSpy).not.toHaveBeenCalled();
    });
  });

  it("supports DELETE pending-action mutations and invalidates related queries", async () => {
    server.use(
      http.delete("*/api/v1/workspaces/:workspaceId/approvals/:approvalId/reject", () =>
        HttpResponse.json({ deleted: true }),
      ),
    );

    const { Wrapper, client } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    client.setQueryData(
      homeQueryKeys.pendingActions("workspace-1"),
      homeFixtures.pendingByWorkspace["workspace-1"],
    );

    const { result } = renderHook(() => useApproveMutation("workspace-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        endpoint: "/api/v1/workspaces/workspace-1/approvals/approval-1/reject",
        method: "DELETE",
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: homeQueryKeys.pendingActions("workspace-1"),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: homeQueryKeys.summary("workspace-1"),
    });
  });

  it("does not attempt optimistic rollback when there is no cached pending action snapshot", async () => {
    server.use(
      http.post("*/api/v1/workspaces/:workspaceId/approvals/:approvalId/approve", () =>
        HttpResponse.json(
          {
            error: {
              code: "forbidden",
              message: "Missing permissions",
            },
          },
          { status: 403 },
        ),
      ),
    );

    const { Wrapper, client } = createHookWrapper();
    const setQueryDataSpy = vi.spyOn(client, "setQueryData");

    const { result } = renderHook(() => useApproveMutation("workspace-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          endpoint: "/api/v1/workspaces/workspace-1/approvals/approval-1/approve",
          method: "POST",
        }),
      ).rejects.toBeInstanceOf(Error);
    });

    expect(setQueryDataSpy).not.toHaveBeenCalled();
    expect(
      client.getQueryData(homeQueryKeys.pendingActions("workspace-1")),
    ).toBeUndefined();
  });
});
