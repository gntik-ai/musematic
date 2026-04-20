export type WsConnectionState =
  | "connecting"
  | "connected"
  | "disconnected"
  | "reconnecting";

export type WsChannel =
  | "alerts"
  | "governance-verdicts"
  | "warm-pool"
  | string;

export interface WsEvent<T = unknown> {
  channel: WsChannel;
  type: string;
  payload: T;
  timestamp: string;
}

export interface WsMessage {
  channel: WsChannel;
  type: string;
  payload: unknown;
}

export type WsEventHandler<T = unknown> = (event: WsEvent<T>) => void;
export type WsUnsubscribeFn = () => void;
