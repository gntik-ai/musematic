import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomeDashboard } from "@/components/features/home/HomeDashboard";
import {
  useDashboardWebSocket,
  usePendingActions,
  useWorkspaceSummary,
} from "@/lib/hooks/use-home-data";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

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

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

vi.mock("@/components/features/home/QuickActions", () => ({
  QuickActions: () => <div data-testid="quick-actions" />,
}));

vi.mock("@/components/features/home/RecentActivity", () => ({
  RecentActivity: () => <div data-testid="recent-activity" />,
}));

vi.mock("@/components/features/home/PendingActions", () => ({
  PendingActions: () => <div data-testid="pending-actions" />,
}));

function DashboardProbe({ workspaceId }: { workspaceId: string }) {
  useDashboardWebSocket(workspaceId);
  useWorkspaceSummary(workspaceId, { isConnected: true });
  usePendingActions(workspaceId, { isConnected: true });
  return <div data-testid="dashboard-probe" />;
}

describe("HomeDashboard", () => {
  beforeEach(() => {
    wsMock.reset();
    push.mockReset();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "owner@musematic.dev",
        displayName: "Owner",
        avatarUrl: null,
        roles: ["workspace_admin"],
        workspaceId: "workspace-1",
        mfaEnrolled: true,
      },
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
    });
    useWorkspaceStore.getState().setCurrentWorkspace({
      id: "workspace-1",
      name: "Signal Lab",
      slug: "signal-lab",
      description: "Primary workspace",
      memberCount: 18,
      createdAt: "2026-04-10T09:00:00.000Z",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the workspace picker empty state when no workspace is selected", () => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
    useWorkspaceStore.setState({
      currentWorkspace: null,
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });

    renderWithProviders(<HomeDashboard />);

    expect(screen.getByText("Select a workspace")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Choose a workspace to load summary metrics, recent activity, and pending actions\./i,
      ),
    ).toBeInTheDocument();
  });

  it("falls back to the authenticated user's workspace id when the workspace store is empty", () => {
    useWorkspaceStore.setState({
      currentWorkspace: null,
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });

    renderWithProviders(<HomeDashboard />);

    expect(screen.getByRole("heading", { name: "Current workspace overview" })).toBeInTheDocument();
  });

  it("invalidates and refetches summary when an execution event arrives", async () => {
    let activeAgents = 12;
    let summaryCalls = 0;

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () => {
        summaryCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          active_agents: activeAgents,
          active_agents_change: 3,
          running_executions: 4,
          running_executions_change: 0,
          pending_approvals: 2,
          pending_approvals_change: -1,
          cost_current: 142_50,
          cost_previous: 130_20,
          period_label: "Apr 2026",
        });
      }),
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json({
          workspace_id: "workspace-1",
          items: [],
        }),
      ),
    );

    renderWithProviders(<HomeDashboard />);

    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(summaryCalls).toBe(1);

    activeAgents = 17;
    wsMock.emit("execution", "execution.completed", {
      workspace_id: "workspace-1",
    });

    await waitFor(() => {
      expect(screen.getByText("17")).toBeInTheDocument();
      expect(summaryCalls).toBeGreaterThan(1);
    });
  });

  it("shows the connection status banner and enables polling when disconnected", async () => {
    wsMock.setConnected(false);
    let summaryCalls = 0;
    const setIntervalSpy = vi.spyOn(window, "setInterval");

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () => {
        summaryCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          active_agents: 12,
          active_agents_change: 0,
          running_executions: 4,
          running_executions_change: 0,
          pending_approvals: 2,
          pending_approvals_change: 0,
          cost_current: 142_50,
          cost_previous: 142_50,
          period_label: "Apr 2026",
        });
      }),
    );

    renderWithProviders(<HomeDashboard />);

    expect(
      await screen.findByText("Live updates paused — reconnecting…"),
    ).toBeInTheDocument();
    await screen.findByText("Active Agents");
    expect(summaryCalls).toBe(1);
    expect(
      setIntervalSpy.mock.calls.some(([, delay]) => delay === 30_000),
    ).toBe(true);
  });

  it("hides the connection status banner and disables polling when connected", async () => {
    let summaryCalls = 0;
    const setIntervalSpy = vi.spyOn(window, "setInterval");

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () => {
        summaryCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          active_agents: 12,
          active_agents_change: 0,
          running_executions: 4,
          running_executions_change: 0,
          pending_approvals: 2,
          pending_approvals_change: 0,
          cost_current: 142_50,
          cost_previous: 142_50,
          period_label: "Apr 2026",
        });
      }),
    );

    renderWithProviders(<HomeDashboard />);

    await screen.findByText("Active Agents");
    expect(
      screen.queryByText("Live updates paused — reconnecting…"),
    ).not.toBeInTheDocument();
    expect(summaryCalls).toBe(1);
    expect(
      setIntervalSpy.mock.calls.some(([, delay]) => delay === 30_000),
    ).toBe(false);
  });

  it("invalidates pending actions and summary when interaction attention is requested", async () => {
    let summaryCalls = 0;
    let pendingCalls = 0;

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () => {
        summaryCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          active_agents: 12,
          active_agents_change: 0,
          running_executions: 4,
          running_executions_change: 0,
          pending_approvals: pendingCalls > 1 ? 3 : 2,
          pending_approvals_change: 1,
          cost_current: 142_50,
          cost_previous: 142_50,
          period_label: "Apr 2026",
        });
      }),
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", () => {
        pendingCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          total: pendingCalls > 1 ? 2 : 1,
          items: [],
        });
      }),
    );

    renderWithProviders(<DashboardProbe workspaceId="workspace-1" />);

    await waitFor(() => {
      expect(summaryCalls).toBe(1);
      expect(pendingCalls).toBe(1);
    });

    expect(summaryCalls).toBe(1);
    expect(pendingCalls).toBe(1);

    wsMock.emit("interaction", "interaction.attention.requested", {
      workspaceId: "workspace-1",
    });

    await waitFor(() => {
      expect(summaryCalls).toBeGreaterThan(1);
      expect(pendingCalls).toBeGreaterThan(1);
    });
  });

  it("ignores dashboard websocket events for a different workspace", async () => {
    let summaryCalls = 0;
    let pendingCalls = 0;

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () => {
        summaryCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          active_agents: 12,
          active_agents_change: 0,
          running_executions: 4,
          running_executions_change: 0,
          pending_approvals: 2,
          pending_approvals_change: 0,
          cost_current: 142_50,
          cost_previous: 142_50,
          period_label: "Apr 2026",
        });
      }),
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", () => {
        pendingCalls += 1;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          total: 1,
          items: [],
        });
      }),
    );

    renderWithProviders(<DashboardProbe workspaceId="workspace-1" />);

    await waitFor(() => {
      expect(summaryCalls).toBe(1);
      expect(pendingCalls).toBe(1);
    });

    expect(summaryCalls).toBe(1);
    expect(pendingCalls).toBe(1);

    wsMock.emit("workspace", "workspace.approval.created", {
      workspace_id: "workspace-2",
    });

    await waitFor(() => {
      expect(summaryCalls).toBe(1);
      expect(pendingCalls).toBe(1);
    });
  });
});
