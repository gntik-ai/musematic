import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SelfCorrectionChart } from "@/components/features/workflows/monitor/SelfCorrectionChart";
import { renderWithProviders } from "@/test-utils/render";
import type { SelfCorrectionLoop } from "@/types/reasoning";

vi.mock("recharts", () => ({
  CartesianGrid: () => <div data-testid="chart-grid" />,
  Line: () => <div data-testid="chart-line" />,
  LineChart: ({
    children,
    data,
    onClick,
  }: {
    children?: React.ReactNode;
    data: Array<Record<string, unknown>>;
    onClick?: (state: { activePayload?: Array<{ payload: Record<string, unknown> }> }) => void;
  }) => (
    <button
      data-testid="line-chart"
      onClick={() => {
        onClick?.({ activePayload: [{ payload: data[0] ?? {} }] });
      }}
      type="button"
    >
      {children}
    </button>
  ),
  ReferenceLine: ({ label }: { label: string }) => <div>{label}</div>,
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => <div data-testid="chart-tooltip" />,
  XAxis: () => <div data-testid="chart-x-axis" />,
  YAxis: () => <div data-testid="chart-y-axis" />,
}));

function buildLoop(finalStatus: SelfCorrectionLoop["finalStatus"]): SelfCorrectionLoop {
  return {
    loopId: "loop-1",
    executionId: "execution-1",
    stepId: "evaluate_risk",
    finalStatus,
    startedAt: new Date("2026-04-13T09:02:00.000Z").toISOString(),
    completedAt: new Date("2026-04-13T09:03:00.000Z").toISOString(),
    budgetConsumed: {
      tokens: 820,
      costUsd: 0.06,
      rounds: 2,
    },
    iterations: [
      {
        iterationNumber: 1,
        qualityScore: 0.61,
        delta: 0.11,
        status: "continue",
        tokenCost: 250,
        durationMs: 1000,
        thoughts: "Re-score the risk factors.",
      },
      {
        iterationNumber: 2,
        qualityScore: 0.82,
        delta: 0.21,
        status: finalStatus === "converged" ? "converged" : "budget_exceeded",
        tokenCost: 320,
        durationMs: 1200,
        thoughts: "Confidence improved after policy reconciliation.",
      },
    ],
  };
}

describe("SelfCorrectionChart", () => {
  it("shows the converged reference label and exposes point selection", () => {
    const handleSelect = vi.fn();

    renderWithProviders(
      <SelfCorrectionChart
        loop={buildLoop("converged")}
        onSelectIteration={handleSelect}
      />,
    );

    expect(screen.getByText("Converged")).toBeInTheDocument();
    expect(screen.getByText("Iteration 2")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("line-chart"));

    expect(handleSelect).toHaveBeenCalledWith(1);
  });

  it("shows the budget limit reference label when the loop exhausts its budget", () => {
    renderWithProviders(<SelfCorrectionChart loop={buildLoop("budget_exceeded")} />);

    expect(screen.getByText("Budget limit")).toBeInTheDocument();
  });

  it("shows the empty state when no loop iterations exist", () => {
    renderWithProviders(<SelfCorrectionChart loop={null} />);

    expect(screen.getByText("No self-correction iterations for this step")).toBeInTheDocument();
  });
});
