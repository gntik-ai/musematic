"use client";

import { ApiError } from "@/types/api";

export const MAINTENANCE_BLOCKED_EVENT = "platform:maintenance-blocked";

export interface MaintenanceBlockedDetails {
  window_end_at?: string;
  retry_after_seconds?: number;
  [key: string]: unknown;
}

export class MaintenanceBlockedError extends ApiError {
  public readonly windowEndAt: string | undefined;
  public readonly retryAfterSeconds: number | undefined;

  constructor(
    message: string,
    status: number,
    details: MaintenanceBlockedDetails = {},
  ) {
    super("platform.maintenance.blocked", message, status, undefined, {
      code: "platform.maintenance.blocked",
      message,
      details,
    });
    this.name = "MaintenanceBlockedError";
    this.windowEndAt =
      typeof details.window_end_at === "string" ? details.window_end_at : undefined;
    this.retryAfterSeconds =
      typeof details.retry_after_seconds === "number"
        ? details.retry_after_seconds
        : undefined;
  }
}

export function emitMaintenanceBlocked(error: MaintenanceBlockedError): void {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent<MaintenanceBlockedError>(MAINTENANCE_BLOCKED_EVENT, {
      detail: error,
    }),
  );
}

export function subscribeMaintenanceBlocked(
  handler: (error: MaintenanceBlockedError) => void,
): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const listener = (event: Event) => {
    if (event instanceof CustomEvent && event.detail instanceof MaintenanceBlockedError) {
      handler(event.detail);
    }
  };
  window.addEventListener(MAINTENANCE_BLOCKED_EVENT, listener);
  return () => window.removeEventListener(MAINTENANCE_BLOCKED_EVENT, listener);
}
