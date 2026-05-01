import { describe, expect, it } from "vitest";
import { mergePersistedAuthState, useAuthStore } from "@/store/auth-store";

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

  it("sets the full auth session in a single action", () => {
    useAuthStore.getState().setAuth({
      user: {
        id: "user-1",
        email: "alex@musematic.dev",
        displayName: "Alex",
        avatarUrl: null,
        roles: ["workspace_admin"],
        workspaceId: null,
        mfaEnrolled: false,
      },
      accessToken: "access",
      refreshToken: "refresh",
      expiresIn: 900,
    });

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe("access");
    expect(state.user?.mfaEnrolled).toBe(false);
  });

  it("clears auth state", () => {
    useAuthStore.getState().setUser({
      id: "user-1",
      email: "alex@musematic.dev",
      displayName: "Alex",
      avatarUrl: null,
      roles: ["workspace_admin"],
      workspaceId: null,
      mfaEnrolled: true,
    });

    useAuthStore.getState().clearAuth();

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("marks the session as authenticated when tokens are set without a user", () => {
    useAuthStore.getState().setTokens({
      accessToken: "access",
      refreshToken: "refresh",
      expiresIn: 900,
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("keeps the session authenticated when a user is set after tokens already exist", () => {
    useAuthStore.setState({
      accessToken: "access",
      refreshToken: "refresh",
      isAuthenticated: true,
    });

    useAuthStore.getState().setUser({
      id: "user-2",
      email: "owner@musematic.dev",
      displayName: "Owner",
      avatarUrl: null,
      roles: ["workspace_admin"],
      workspaceId: "workspace-1",
      mfaEnrolled: true,
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("updates the loading flag", () => {
    useAuthStore.getState().setLoading(true);
    expect(useAuthStore.getState().isLoading).toBe(true);
  });

  it("tracks persisted auth hydration separately from authentication", () => {
    useAuthStore.getState().setHasHydrated(false);
    expect(useAuthStore.getState().hasHydrated).toBe(false);

    useAuthStore.getState().setHasHydrated(true);
    expect(useAuthStore.getState().hasHydrated).toBe(true);

    useAuthStore.getState().clearAuth();
    expect(useAuthStore.getState().hasHydrated).toBe(true);
  });

  it("marks persisted auth as hydrated and authenticated in one merge", () => {
    const merged = mergePersistedAuthState(
      {
        refreshToken: "refresh",
        user: null,
      },
      {
        ...useAuthStore.getState(),
        accessToken: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
        hasHydrated: false,
      },
    );

    expect(merged.hasHydrated).toBe(true);
    expect(merged.isAuthenticated).toBe(true);
  });
});
