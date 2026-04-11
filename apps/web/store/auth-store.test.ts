import { describe, expect, it } from "vitest";
import { useAuthStore } from "@/store/auth-store";

describe("auth-store", () => {
  it("persists only the refresh token", () => {
    useAuthStore.getState().setTokens({
      accessToken: "access",
      refreshToken: "refresh",
      expiresIn: 900,
    });

    const persisted = localStorage.getItem("auth-storage");
    expect(persisted).toContain("refresh");
    expect(persisted).not.toContain("access");
  });

  it("clears auth state", () => {
    useAuthStore.getState().setUser({
      id: "user-1",
      email: "alex@musematic.dev",
      displayName: "Alex",
      avatarUrl: null,
      roles: ["workspace_admin"],
      workspaceId: null,
    });

    useAuthStore.getState().clearAuth();

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
