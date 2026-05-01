import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "@/lib/api";
import {
  MAINTENANCE_BLOCKED_EVENT,
  MaintenanceBlockedError,
} from "@/lib/maintenance-blocked";
import type { ApiError } from "@/types/api";
import { useAuthStore } from "@/store/auth-store";

const { refreshAccessToken } = vi.hoisted(() => ({
  refreshAccessToken: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  refreshAccessToken,
}));

describe("createApiClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    refreshAccessToken.mockReset();
    useAuthStore.setState({
      accessToken: "access-token",
      clearAuth: vi.fn(),
    } as never);
  });

  it("injects the bearer token into requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    const client = createApiClient("https://api.example.com");
    await client.get("/health");

    expect(fetchSpy).toHaveBeenCalledWith(
      "https://api.example.com/health",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
    const headers = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer access-token");
  });

  it("refreshes once after a 401 and retries the request", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }));

    refreshAccessToken.mockResolvedValue({
      accessToken: "refreshed",
      refreshToken: "refresh",
      expiresIn: 900,
    });

    const client = createApiClient("https://api.example.com");
    const response = await client.get<{ items: [] }>("/api/v1/workspaces");

    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(response).toEqual({ items: [] });
  });

  it("normalizes API error payloads into ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "validation_failed",
            message: "Invalid payload",
            details: [{ message: "Missing field", field: "email" }],
          },
        }),
        { status: 422 },
      ),
    );

    const client = createApiClient("https://api.example.com");

    await expect(client.post("/api/v1/auth/login", { email: "" })).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "validation_failed",
        status: 422,
      }),
    );
  });

  it("throws MaintenanceBlockedError for maintenance 503 envelopes", async () => {
    const listener = vi.fn();
    window.addEventListener(MAINTENANCE_BLOCKED_EVENT, listener);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "platform.maintenance.blocked",
            message: "Writes are blocked during maintenance.",
            details: {
              window_end_at: "2026-05-01T12:30:00.000Z",
              retry_after_seconds: 120,
            },
          },
        }),
        { status: 503 },
      ),
    );

    const client = createApiClient("https://api.example.com");

    await expect(client.post("/api/v1/workflows/trigger", {})).rejects.toEqual(
      expect.objectContaining<Partial<MaintenanceBlockedError>>({
        code: "platform.maintenance.blocked",
        status: 503,
        windowEndAt: "2026-05-01T12:30:00.000Z",
        retryAfterSeconds: 120,
      }),
    );
    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: expect.any(MaintenanceBlockedError),
      }),
    );
    window.removeEventListener(MAINTENANCE_BLOCKED_EVENT, listener);
  });

  it("keeps generic 503 responses as ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "service_unavailable",
            message: "Service unavailable",
          },
        }),
        { status: 503 },
      ),
    );

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/api/v1/reports")).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "service_unavailable",
        status: 503,
      }),
    );
  });

  it("returns undefined for 204 responses and supports PUT/PATCH/DELETE helpers", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));

    const client = createApiClient("https://api.example.com");

    await expect(client.put("/resource", { enabled: true })).resolves.toBeUndefined();
    await expect(client.patch("/resource", { enabled: false })).resolves.toBeUndefined();
    await expect(client.delete("/resource")).resolves.toBeUndefined();

    expect(fetchSpy).toHaveBeenNthCalledWith(
      1,
      "https://api.example.com/resource",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(fetchSpy).toHaveBeenNthCalledWith(
      2,
      "https://api.example.com/resource",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(fetchSpy).toHaveBeenNthCalledWith(
      3,
      "https://api.example.com/resource",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("normalizes non-JSON error responses as unknown errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("internal error", {
        status: 500,
        statusText: "Internal Server Error",
      }),
    );

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/broken")).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "unknown_error",
        status: 500,
      }),
    );
  });

  it("supports body-less POST requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    const client = createApiClient("https://api.example.com");
    await client.post("/ping");

    expect(fetchSpy).toHaveBeenCalledWith(
      "https://api.example.com/ping",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("clears auth when a refreshed request is still unauthorized", async () => {
    const clearAuth = vi.fn();
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    useAuthStore.setState({
      accessToken: "access-token",
      clearAuth,
    } as never);

    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));

    refreshAccessToken.mockResolvedValue({
      accessToken: "refreshed",
      refreshToken: "refresh",
      expiresIn: 900,
    });

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/secure")).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "unauthorized",
        status: 401,
      }),
    );

    expect(clearAuth).toHaveBeenCalledTimes(1);
    consoleErrorSpy.mockRestore();
  });

  it("retries transient network errors with exponential backoff", async () => {
    vi.useFakeTimers();

    vi.spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const client = createApiClient("https://api.example.com");
    const request = client.get<{ ok: boolean }>("/retry");

    await vi.advanceTimersByTimeAsync(1000);

    await expect(request).resolves.toEqual({ ok: true });
    vi.useRealTimers();
  });

  it("rethrows non-retriable failures without waiting", async () => {
    vi.useFakeTimers();

    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("boom"));

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/fatal")).rejects.toThrow("boom");
    vi.useRealTimers();
  });

  it("skips retry logic when skipRetry is enabled", async () => {
    vi.useFakeTimers();

    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/no-retry", { skipRetry: true })).rejects.toThrow(
      "network",
    );
    vi.useRealTimers();
  });

  it("skips auth headers when requested", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    const client = createApiClient("https://api.example.com");
    await client.get("/public", { skipAuth: true });

    const headers = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("Authorization")).toBeNull();
  });

  it("normalizes JSON payloads without an error envelope as unknown errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ message: "plain failure" }), {
        status: 500,
        statusText: "Internal Server Error",
      }),
    );

    const client = createApiClient("https://api.example.com");

    await expect(client.get("/json-without-envelope")).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "unknown_error",
        status: 500,
      }),
    );
  });
});
