import { beforeEach, describe, expect, it, vi } from "vitest";
import { refreshAccessToken } from "@/lib/auth";
import { useAuthStore } from "@/store/auth-store";

describe("refreshAccessToken", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: "refresh-token",
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("clears auth and throws when no refresh token is available", async () => {
    const clearAuthSpy = vi.spyOn(useAuthStore.getState(), "clearAuth");
    useAuthStore.setState({ refreshToken: null });

    await expect(refreshAccessToken()).rejects.toThrow("Missing refresh token");

    expect(clearAuthSpy).toHaveBeenCalledTimes(1);
  });

  it("normalizes and stores refreshed tokens", async () => {
    const setTokensSpy = vi.spyOn(useAuthStore.getState(), "setTokens");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "next-access",
          refresh_token: "next-refresh",
          expires_in: 1800,
        }),
        { status: 200 },
      ),
    );

    await expect(refreshAccessToken()).resolves.toEqual({
      accessToken: "next-access",
      refreshToken: "next-refresh",
      expiresIn: 1800,
    });
    expect(setTokensSpy).toHaveBeenCalledWith({
      accessToken: "next-access",
      refreshToken: "next-refresh",
      expiresIn: 1800,
    });
  });

  it("reuses an inflight refresh request", async () => {
    const deferred = {
      resolve: null as ((value: Response) => void) | null,
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          deferred.resolve = resolve;
        }),
    );

    const first = refreshAccessToken();
    const second = refreshAccessToken();

    expect(fetchSpy).toHaveBeenCalledTimes(1);

    if (!deferred.resolve) {
      throw new Error("Expected inflight refresh request");
    }

    deferred.resolve(
      new Response(
        JSON.stringify({
          access_token: "shared-access",
          refresh_token: "shared-refresh",
          expires_in: 900,
        }),
        { status: 200 },
      ),
    );

    await expect(first).resolves.toEqual({
      accessToken: "shared-access",
      refreshToken: "shared-refresh",
      expiresIn: 900,
    });
    await expect(second).resolves.toEqual({
      accessToken: "shared-access",
      refreshToken: "shared-refresh",
      expiresIn: 900,
    });
  });

  it("clears auth and fails when the refresh endpoint rejects the token", async () => {
    const clearAuthSpy = vi.spyOn(useAuthStore.getState(), "clearAuth");
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 401 }));

    await expect(refreshAccessToken()).rejects.toThrow(
      "Unable to refresh access token",
    );

    expect(clearAuthSpy).toHaveBeenCalledTimes(1);
    consoleErrorSpy.mockRestore();
  });
});
