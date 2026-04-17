import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLockoutCountdown } from "@/lib/hooks/use-lockout-countdown";

describe("use-lockout-countdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-11T10:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns the correct remaining time and format", () => {
    const { result } = renderHook(() =>
      useLockoutCountdown({
        unlockAt: new Date(Date.now() + 65_000),
        onExpired: vi.fn(),
      }),
    );

    expect(result.current.remainingSeconds).toBe(65);
    expect(result.current.remainingFormatted).toBe("1:05");
    expect(result.current.isExpired).toBe(false);
  });

  it("calls onExpired exactly once when the countdown finishes", () => {
    const onExpired = vi.fn();
    const unlockAt = new Date(Date.now() + 2_000);

    const { result } = renderHook(() =>
      useLockoutCountdown({
        unlockAt,
        onExpired,
      }),
    );

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.isExpired).toBe(true);
    expect(onExpired).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("cleans up the interval on unmount", () => {
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");
    const { unmount } = renderHook(() =>
      useLockoutCountdown({
        unlockAt: new Date(Date.now() + 5_000),
        onExpired: vi.fn(),
      }),
    );

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  it("handles a null unlock date as already expired", () => {
    const { result } = renderHook(() =>
      useLockoutCountdown({
        unlockAt: null,
        onExpired: vi.fn(),
      }),
    );

    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.remainingFormatted).toBe("0s");
    expect(result.current.isExpired).toBe(true);
  });
});
