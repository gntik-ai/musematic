import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { CostTracker } from "@/components/features/workflows/monitor/CostTracker";
import { renderWithProviders } from "@/test-utils/render";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";

describe("CostTracker", () => {
  beforeEach(() => {
    useExecutionMonitorStore.getState().reset();
  });

  it("shows an empty state until token usage exists", () => {
    renderWithProviders(<CostTracker executionId="execution-1" />);

    expect(screen.getByText("No cost data yet")).toBeInTheDocument();
  });

  it("updates totals reactively and renders the fetched step breakdown", async () => {
    useExecutionMonitorStore.setState({
      executionId: "execution-1",
      totalTokens: 120,
      totalCostUsd: 0.008,
      costBreakdown: [],
    });

    renderWithProviders(<CostTracker executionId="execution-1" />);

    expect(screen.getByText("120 tokens")).toBeInTheDocument();

    act(() => {
      useExecutionMonitorStore.getState().accumulateCost(548, 0.0234);
    });

    expect(screen.getByText("668 tokens")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Expand breakdown/i }));

    expect(await screen.findByText("Evaluate Risk")).toBeInTheDocument();
    expect(screen.getByText("Collect Context")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByText("Evaluate Risk").closest("div.rounded-2xl"),
      ).toHaveClass("bg-yellow-50");
    });
  });
});
