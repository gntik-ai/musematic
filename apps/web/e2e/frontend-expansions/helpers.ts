import type { Page, Route } from "@playwright/test";

export const workspaceFixture = {
  id: "workspace-1",
  name: "Risk Ops",
  slug: "risk-ops",
  description: "Primary risk workspace",
  memberCount: 8,
  createdAt: "2026-04-10T09:00:00.000Z",
} as const;

interface AuthStateOptions {
  roles?: string[];
  workspaceId?: string;
  userId?: string;
  email?: string;
  displayName?: string;
}

declare global {
  interface Window {
    __emitFrontendWsEvent?: (message: {
      channel: string;
      type: string;
      payload: unknown;
      timestamp?: string;
    }) => void;
    __disconnectFrontendWs?: () => void;
  }
}

export async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

export async function installFrontendState(
  page: Page,
  options: AuthStateOptions = {},
) {
  const {
    roles = ["platform_admin", "workspace_admin", "agent_operator", "analytics_viewer"],
    workspaceId = workspaceFixture.id,
    userId = "user-1",
    email = "operator@musematic.dev",
    displayName = "Operator",
  } = options;

  await page.addInitScript(
    ({ roles, workspaceId, userId, email, displayName, workspace }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: userId,
              email,
              displayName,
              avatarUrl: null,
              roles,
              workspaceId,
              mfaEnrolled: true,
            },
            accessToken: "mock-access-token",
            refreshToken: "mock-refresh-token",
            isAuthenticated: true,
            isLoading: false,
          },
          version: 0,
        }),
      );

      window.localStorage.setItem(
        "workspace-storage",
        JSON.stringify({
          state: {
            currentWorkspace: workspace,
            workspaceList: [workspace],
            sidebarCollapsed: false,
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    {
      roles,
      workspaceId,
      userId,
      email,
      displayName,
      workspace: workspaceFixture,
    },
  );
}

export async function installFrontendWs(page: Page) {
  await page.addInitScript(() => {
    const sockets: MockWebSocket[] = [];

    class MockWebSocket extends EventTarget {
      static OPEN = 1;
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor() {
        super();
        sockets.push(this);
        window.setTimeout(() => {
          const event = new Event("open");
          this.onopen?.(event);
          this.dispatchEvent(event);
        }, 0);
      }

      close() {
        this.readyState = 3;
        const event = new CloseEvent("close");
        this.onclose?.(event);
        this.dispatchEvent(event);
      }

      send() {}
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });

    window.__emitFrontendWsEvent = (message) => {
      sockets.forEach((socket) => {
        if (socket.readyState !== MockWebSocket.OPEN) {
          return;
        }
        const event = new MessageEvent("message", {
          data: JSON.stringify(message),
        });
        socket.onmessage?.(event);
        socket.dispatchEvent(event);
      });
    };

    window.__disconnectFrontendWs = () => {
      sockets.splice(0).forEach((socket) => socket.close());
    };
  });
}

export async function mockCommonAppApi(
  page: Page,
  options: { unreadCount?: number; alerts?: Array<Record<string, unknown>> } = {},
) {
  const { unreadCount = 0, alerts = [] } = options;

  await page.route("**/api/v1/workspaces", async (route) => {
    await fulfillJson(route, { items: [workspaceFixture] });
  });

  await page.route("**/me/alerts?**", async (route) => {
    await fulfillJson(route, {
      items: alerts,
      total_unread: unreadCount,
    });
  });

  await page.route("**/me/alerts/unread-count", async (route) => {
    await fulfillJson(route, { count: unreadCount });
  });
}

export async function emitFrontendWsEvent(
  page: Page,
  message: {
    channel: string;
    type: string;
    payload: unknown;
    timestamp?: string;
  },
) {
  await page.evaluate((payload) => {
    window.__emitFrontendWsEvent?.(payload);
  }, message);
}

export async function disconnectFrontendWs(page: Page) {
  await page.evaluate(() => {
    window.__disconnectFrontendWs?.();
  });
}
