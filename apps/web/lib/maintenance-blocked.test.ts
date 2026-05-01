import { describe, expect, it, vi } from "vitest";
import {
  MAINTENANCE_BLOCKED_EVENT,
  MaintenanceBlockedError,
  emitMaintenanceBlocked,
  subscribeMaintenanceBlocked,
  type MaintenanceBlockedDetails,
} from "@/lib/maintenance-blocked";

describe("maintenance blocked events", () => {
  it("normalises maintenance details from the API envelope", () => {
    const error = new MaintenanceBlockedError("Writes are paused.", 503, {
      retry_after_seconds: 90,
      window_end_at: "2026-05-01T08:00:00.000Z",
    });

    expect(error.name).toBe("MaintenanceBlockedError");
    expect(error.code).toBe("platform.maintenance.blocked");
    expect(error.retryAfterSeconds).toBe(90);
    expect(error.windowEndAt).toBe("2026-05-01T08:00:00.000Z");

    const invalidDetails = {
      retry_after_seconds: "soon",
      window_end_at: 123,
    } as unknown as MaintenanceBlockedDetails;
    const fallback = new MaintenanceBlockedError("Writes are paused.", 503, invalidDetails);
    expect(fallback.retryAfterSeconds).toBeUndefined();
    expect(fallback.windowEndAt).toBeUndefined();
  });

  it("emits, filters, and unsubscribes maintenance blocked browser events", () => {
    const handler = vi.fn();
    const unsubscribe = subscribeMaintenanceBlocked(handler);
    const error = new MaintenanceBlockedError("Writes are paused.", 503);

    window.dispatchEvent(new Event(MAINTENANCE_BLOCKED_EVENT));
    window.dispatchEvent(new CustomEvent(MAINTENANCE_BLOCKED_EVENT, { detail: {} }));
    emitMaintenanceBlocked(error);

    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith(error);

    unsubscribe();
    emitMaintenanceBlocked(error);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("noops when browser globals are unavailable", () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: undefined,
    });

    try {
      const handler = vi.fn();
      const error = new MaintenanceBlockedError("Writes are paused.", 503);
      const unsubscribe = subscribeMaintenanceBlocked(handler);

      emitMaintenanceBlocked(error);
      unsubscribe();

      expect(handler).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: originalWindow,
      });
    }
  });
});
