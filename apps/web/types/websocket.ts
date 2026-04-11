export type WsConnectionState = "connecting" | "connected" | "disconnected" | "reconnecting";

export interface WsEvent<T = unknown> {
  channel: string;
  type: string;
  payload: T;
  timestamp: string;
}

export interface WsMessage {
  channel: string;
  type: string;
  payload: unknown;
}

export type WsEventHandler<T = unknown> = (event: WsEvent<T>) => void;
export type WsUnsubscribeFn = () => void;
