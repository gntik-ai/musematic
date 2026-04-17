import { beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketClient } from "@/lib/ws";

class MockSocket {
  public onopen: (() => void) | null = null;
  public onmessage: ((event: { data: string }) => void) | null = null;
  public onclose: (() => void) | null = null;
  public onerror: (() => void) | null = null;
  public sent: string[] = [];

  close() {
    this.onclose?.();
  }

  send(data: string) {
    this.sent.push(data);
  }
}

describe("WebSocketClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
    const socket = new MockSocket();
    vi.stubGlobal(
      "WebSocket",
      vi.fn(() => socket),
    );
  });

  it("registers subscriptions and unsubscribes cleanly", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    const handler = vi.fn();

    const unsubscribe = client.subscribe("runtime.lifecycle", handler);
    unsubscribe();

    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onopen?.();
    socket.onmessage?.({
      data: JSON.stringify({
        channel: "runtime.lifecycle",
        type: "snapshot",
        payload: { ok: true },
        timestamp: new Date().toISOString(),
      }),
    });

    expect(handler).not.toHaveBeenCalled();
  });

  it("replays existing subscriptions when the socket opens", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");

    client.subscribe("runtime.lifecycle", vi.fn());
    client.connect();

    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onopen?.();

    expect(socket.sent[0]).toContain('"type":"subscribe"');
  });

  it("dispatches inbound messages and subscribes immediately when already connected", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    const handler = vi.fn();

    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onopen?.();

    client.subscribe("runtime.lifecycle", handler);
    socket.onmessage?.({
      data: JSON.stringify({
        channel: "runtime.lifecycle",
        type: "snapshot",
        payload: { ok: true },
        timestamp: new Date().toISOString(),
      }),
    });

    expect(socket.sent.at(-1)).toContain('"type":"subscribe"');
    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: "runtime.lifecycle",
        type: "snapshot",
      }),
    );
  });

  it("sends messages once connected", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onopen?.();

    client.send("runtime.lifecycle", "subscribe", { workspaceId: "workspace-1" });

    expect(socket.sent[0]).toContain('"channel":"runtime.lifecycle"');
  });

  it("schedules reconnects with backoff", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onclose?.();

    expect(client.connectionState).toBe("disconnected");
    vi.advanceTimersByTime(1000);
    expect((WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
  });

  it("does not queue a second reconnect timer while one is already pending", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    client.connect();

    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onclose?.();
    socket.onclose?.();

    vi.advanceTimersByTime(1000);

    expect((WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
  });

  it("notifies state listeners and connection listeners", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");
    const stateHandler = vi.fn();
    const connectedHandler = vi.fn();

    const unsubscribeState = client.onStateChange(stateHandler);
    const unsubscribeConnected = client.onConnectionChange(connectedHandler);

    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onopen?.();
    socket.onerror?.();

    expect(stateHandler).toHaveBeenCalledWith("disconnected");
    expect(stateHandler).toHaveBeenCalledWith("connecting");
    expect(stateHandler).toHaveBeenCalledWith("connected");
    expect(connectedHandler).toHaveBeenCalledWith(false);
    expect(connectedHandler).toHaveBeenCalledWith(true);

    unsubscribeState();
    unsubscribeConnected();
  });

  it("does not send when disconnected and clears pending reconnects on disconnect", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");

    client.send("runtime.lifecycle", "subscribe", {});
    client.connect();
    const socket = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.results[0]?.value as MockSocket;
    socket.onclose?.();

    client.disconnect();
    vi.advanceTimersByTime(1000);

    expect(socket.sent).toHaveLength(0);
    expect((WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it("does not open a second socket while already connecting", () => {
    const client = new WebSocketClient("ws://localhost:8000/ws");

    client.connect();
    client.connect();

    expect((WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });
});
