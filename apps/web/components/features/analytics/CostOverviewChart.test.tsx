import type { ReactNode } from "react";
import type * as RechartsModule from "recharts";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CostOverviewChart } from "@/components/features/analytics/CostOverviewChart";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof RechartsModule>("recharts");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div style={{ height: 320, width: 640 }}>{children}</div>
    ),
  };
});

describe("CostOverviewChart", () => {
  it("cycles breakdown modes with keyboard arrows", () => {
    const onBreakdownChange = vi.fn();

    render(
      <CostOverviewChart
        breakdownMode="workspace"
        data={[
          { period: "Apr 10", workspace_total: 10 },
          { period: "Apr 11", workspace_total: 100 },
          { period: "Apr 12", workspace_total: 10 },
        ]}
        onBreakdownChange={onBreakdownChange}
        seriesKeys={["workspace_total"]}
      />,
    );

    fireEvent.keyDown(screen.getByRole("button", { name: "Workspace" }), {
      key: "ArrowRight",
    });

    expect(onBreakdownChange).toHaveBeenCalledWith("agent");
  });

  it("renders an empty state when no series data is present", () => {
    render(
      <CostOverviewChart
        breakdownMode="workspace"
        data={[]}
        onBreakdownChange={vi.fn()}
        seriesKeys={[]}
      />,
    );

    expect(screen.getByText("No cost data")).toBeInTheDocument();
  });
});
