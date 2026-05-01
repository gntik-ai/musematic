"use client";

import type {
  WsChannel,
  WsConnectionState,
  WsEvent,
  WsEventHandler,
  WsMessage,
  WsUnsubscribeFn,
} from "@/types/websocket";

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000] as const;

export class WebSocketClient {
  private socket: WebSocket | null = null;
  private readonly subscriptions = new Map<WsChannel, Set<WsEventHandler>>();
  private readonly stateHandlers = new Set<(state: WsConnectionState) => void>();
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private state: WsConnectionState = "disconnected";

  constructor(private readonly url: string) {}

  get connectionState(): WsConnectionState {
    return this.state;
  }

  connect(): void {
    if (this.socket && (this.state === "connected" || this.state === "connecting")) {
      return;
    }

    this.setState(this.reconnectAttempt > 0 ? "reconnecting" : "connecting");
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setState("connected");
      for (const channel of this.subscriptions.keys()) {
        this.send(channel, "subscribe", {});
      }
    };

    this.socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as WsEvent;
      const handlers = this.subscriptions.get(message.channel);
      handlers?.forEach((handler) => {
        handler(message);
      });
    };

    this.socket.onerror = () => {
      this.setState("disconnected");
    };

    this.socket.onclose = () => {
      this.socket = null;
      this.setState("disconnected");
      this.scheduleReconnect();
    };
  }

  disconnect(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.reconnectAttempt = 0;
    this.socket?.close();
    this.socket = null;
    this.setState("disconnected");
  }

  subscribe<T = unknown>(channel: WsChannel, handler: WsEventHandler<T>): WsUnsubscribeFn {
    const currentHandlers = this.subscriptions.get(channel) ?? new Set<WsEventHandler>();
    currentHandlers.add(handler as WsEventHandler);
    this.subscriptions.set(channel, currentHandlers);

    if (this.connectionState === "connected") {
      this.send(channel, "subscribe", {});
    }

    return () => {
      const handlers = this.subscriptions.get(channel);
      handlers?.delete(handler as WsEventHandler);
      if (handlers && handlers.size === 0) {
        this.subscriptions.delete(channel);
      }
    };
  }

  observe<T = unknown>(channel: WsChannel, handler: WsEventHandler<T>): WsUnsubscribeFn {
    const currentHandlers = this.subscriptions.get(channel) ?? new Set<WsEventHandler>();
    currentHandlers.add(handler as WsEventHandler);
    this.subscriptions.set(channel, currentHandlers);

    return () => {
      const handlers = this.subscriptions.get(channel);
      handlers?.delete(handler as WsEventHandler);
      if (handlers && handlers.size === 0) {
        this.subscriptions.delete(channel);
      }
    };
  }

  send(channel: WsChannel, type: string, payload: unknown): void {
    if (!this.socket || this.connectionState !== "connected") {
      return;
    }

    const message: WsMessage = {
      channel,
      type,
      payload,
    };

    this.socket.send(JSON.stringify(message));
  }

  onStateChange(handler: (state: WsConnectionState) => void): WsUnsubscribeFn {
    this.stateHandlers.add(handler);
    handler(this.state);

    return () => {
      this.stateHandlers.delete(handler);
    };
  }

  onConnectionChange(handler: (isConnected: boolean) => void): WsUnsubscribeFn {
    return this.onStateChange((state) => {
      handler(state === "connected");
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return;
    }

    const delay = RECONNECT_DELAYS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS.length - 1)] ?? 30000;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectAttempt += 1;
      this.connect();
    }, delay);
  }

  private setState(state: WsConnectionState): void {
    this.state = state;
    this.stateHandlers.forEach((handler) => handler(state));
  }
}

export const wsClient = new WebSocketClient(
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws",
);
