import { afterEach, describe, expect, it, vi } from "vitest";
import { log, registerClientErrorHandlers } from "@/lib/logging";

describe("structured frontend logging", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts client log events to the ingestion route", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null));

    log.error("client.failed", { user_id: "user-1", stack: "stack" });
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/log/client-error",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        keepalive: true,
      }),
    );
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body).toMatchObject({
      level: "error",
      service: "web",
      bounded_context: "frontend",
      message: "client.failed",
      user_id: "user-1",
      stack: "stack",
    });
  });

  it("registers global browser error handlers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null));
    const cleanup = registerClientErrorHandlers();

    window.dispatchEvent(new ErrorEvent("error", { message: "boom", error: new Error("boom") }));
    await Promise.resolve();
    cleanup();

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.message).toBe("boom");
    expect(body.level).toBe("error");
    expect(body.stack).toContain("boom");
  });
});
