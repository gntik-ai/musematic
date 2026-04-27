import { afterEach, describe, expect, it, vi } from "vitest";
import { log, registerClientErrorHandlers } from "@/lib/logging";

describe("structured frontend logging", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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

  it("emits every browser log level and preserves supplied client fields", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null));

    log.debug("client.debug");
    log.info("client.info", { url: "https://example.test/manual", user_agent: "agent/1" });
    log.warn("client.warn");
    log.fatal("client.fatal");
    await Promise.resolve();

    const bodies = fetchMock.mock.calls.map((call) => JSON.parse(String(call[1]?.body)));
    expect(bodies.map((body) => body.level)).toEqual(["debug", "info", "warn", "fatal"]);
    expect(bodies[1]).toMatchObject({
      url: "https://example.test/manual",
      user_agent: "agent/1",
    });
  });

  it("does not surface client logging delivery failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

    log.warn("client.delivery_failed");
    await Promise.resolve();

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
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

  it("logs fallback browser errors without non-error stack payloads", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null));
    const cleanup = registerClientErrorHandlers();

    window.dispatchEvent(new ErrorEvent("error", { message: "", error: "plain" }));
    await Promise.resolve();
    cleanup();

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.message).toBe("client.error");
    expect(body.stack).toBeUndefined();
  });

  it("logs unhandled rejection errors and primitive reasons", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null));
    const cleanup = registerClientErrorHandlers();

    const errorEvent = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(errorEvent, "reason", { value: new Error("async boom") });
    window.dispatchEvent(errorEvent);

    const primitiveEvent = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(primitiveEvent, "reason", { value: "bad promise" });
    window.dispatchEvent(primitiveEvent);

    await Promise.resolve();
    cleanup();

    const bodies = fetchMock.mock.calls.map((call) => JSON.parse(String(call[1]?.body)));
    expect(bodies[0]).toMatchObject({ message: "async boom", level: "error" });
    expect(bodies[0].stack).toContain("async boom");
    expect(bodies[1]).toMatchObject({
      message: "client.unhandled_rejection",
      stack: "bad promise",
    });
  });

  it("falls back to stdout when no browser window exists", () => {
    const consoleMock = vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.stubGlobal("window", undefined);

    const cleanup = registerClientErrorHandlers();
    log.info("server.rendered");
    cleanup();

    const payload = JSON.parse(String(consoleMock.mock.calls[0]?.[0]));
    expect(payload).toMatchObject({
      level: "info",
      service: "web",
      bounded_context: "frontend",
      message: "server.rendered",
    });
  });
});
