import type { ReactNode } from "react";
import type * as RechartsModule from "recharts";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DriftChart } from "@/components/features/analytics/DriftChart";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof RechartsModule>("recharts");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div style={{ height: 220, width: 640 }}>{children}</div>
    ),
  };
});

describe("DriftChart", () => {
  it("renders an empty state when there is no chart data", () => {
    render(
      <DriftChart
        agentFqn="platform.agent"
        data={[]}
      />,
    );

    expect(
      screen.getByText("No drift markers have been recorded for this agent."),
    ).toBeInTheDocument();
  });

  it("renders the heading and chart region when data exists", () => {
    render(
      <DriftChart
        agentFqn="platform.agent"
        data={[
          { period: "Apr 10", value: 0.9, baseline: 0.88, isAnomaly: false },
          { period: "Apr 11", value: 0.6, baseline: 0.88, isAnomaly: true },
        ]}
      />,
    );

    expect(screen.getByText("platform.agent")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Drift chart for platform.agent" }),
    ).toBeInTheDocument();
  });
});
