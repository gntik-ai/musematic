import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MaintenanceBlockedActionModal } from "@/components/features/platform-status/MaintenanceBlockedActionModal";
import { MaintenanceBlockedError } from "@/lib/maintenance-blocked";
import { renderWithProviders } from "@/test-utils/render";

describe("MaintenanceBlockedActionModal", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders window end time and a disabled retry action without a raw 503 message", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-01T13:29:30.000Z"));

    const error = new MaintenanceBlockedError("Writes are blocked.", 503, {
      window_end_at: "2026-05-01T13:30:00.000Z",
    });

    renderWithProviders(
      <MaintenanceBlockedActionModal
        error={error}
        open
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Maintenance is in progress")).toBeInTheDocument();
    expect(screen.getByText(/try again after/i)).toBeInTheDocument();
    expect(screen.queryByText(/503/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry after/i })).toBeDisabled();
  });
});
