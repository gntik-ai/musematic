import { http, HttpResponse } from "msw";
import type { TokenPair, UserProfile } from "@/types/auth";
import type { Workspace } from "@/types/workspace";

const mockUser: UserProfile = {
  id: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
  email: "alex@musematic.dev",
  displayName: "Alex Mercer",
  avatarUrl: null,
  roles: ["workspace_admin", "agent_operator", "analytics_viewer"],
  workspaceId: "workspace-1",
};

const mockTokenPair: TokenPair = {
  accessToken: "mock-access-token",
  refreshToken: "mock-refresh-token",
  expiresIn: 900,
};

const workspaces: Workspace[] = [
  {
    id: "workspace-1",
    name: "Signal Lab",
    slug: "signal-lab",
    description: "Primary operations workspace",
    memberCount: 18,
    createdAt: "2026-04-10T09:00:00.000Z",
  },
  {
    id: "workspace-2",
    name: "Trust Foundry",
    slug: "trust-foundry",
    description: "Safety and governance programs",
    memberCount: 11,
    createdAt: "2026-04-08T13:30:00.000Z",
  },
];

export const handlers = [
  http.post("*/api/v1/auth/login", async () =>
    HttpResponse.json({
      ...mockTokenPair,
      user: mockUser,
    }),
  ),
  http.post("*/api/v1/auth/refresh", async () => HttpResponse.json(mockTokenPair)),
  http.post("*/api/v1/auth/logout", async () => new HttpResponse(null, { status: 204 })),
  http.get("*/api/v1/workspaces", async () => HttpResponse.json({ items: workspaces })),
];

export { mockTokenPair, mockUser, workspaces };
