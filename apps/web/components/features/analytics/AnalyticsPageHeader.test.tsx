import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsPageHeader } from "@/components/features/analytics/AnalyticsPageHeader";
import type { AnalyticsDateRange } from "@/types/analytics";

const dateRange: AnalyticsDateRange = {
  from: new Date("2026-04-01T00:00:00.000Z"),
  to: new Date("2026-04-30T23:59:59.999Z"),
  preset: "30d",
};

describe("AnalyticsPageHeader", () => {
  it("fires export when the export button is clicked", async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();

    render(
      <AnalyticsPageHeader
        dateRange={dateRange}
        isExporting={false}
        onDateRangeChange={vi.fn()}
        onExport={onExport}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Export analytics data as CSV" }));

    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("applies a custom range from the popover inputs", async () => {
    const user = userEvent.setup();
    const onDateRangeChange = vi.fn();

    render(
      <AnalyticsPageHeader
        dateRange={dateRange}
        isExporting={false}
        onDateRangeChange={onDateRangeChange}
        onExport={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Custom" }));

    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-03-01" },
    });
    fireEvent.change(screen.getByLabelText("To"), {
      target: { value: "2026-03-15" },
    });

    await user.click(screen.getByRole("button", { name: "Apply range" }));

    expect(onDateRangeChange).toHaveBeenCalledWith({
      from: new Date("2026-03-01T00:00:00.000Z"),
      to: new Date("2026-03-15T23:59:59.999Z"),
      preset: "custom",
    });
  });
});
