import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LockoutMessage } from "@/components/features/auth/login-form/LockoutMessage";
import { renderWithProviders } from "@/test-utils/render";

describe("LockoutMessage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-11T10:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the initial countdown and updates every second", () => {
    renderWithProviders(
      <LockoutMessage
        onExpired={vi.fn()}
        unlockAt={new Date(Date.now() + 60_000)}
      />,
    );

    expect(screen.getByText("1:00")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    expect(screen.getByText("59s")).toBeInTheDocument();
  });

  it("calls onExpired when the lockout ends", () => {
    const onExpired = vi.fn();

    renderWithProviders(
      <LockoutMessage
        onExpired={onExpired}
        unlockAt={new Date(Date.now() + 2_000)}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(onExpired).toHaveBeenCalledTimes(1);
  });
});
