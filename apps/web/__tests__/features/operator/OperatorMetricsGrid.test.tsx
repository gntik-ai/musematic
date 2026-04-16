import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OperatorMetricsGrid } from "@/components/features/operator/OperatorMetricsGrid";
import { renderWithProviders } from "@/test-utils/render";
import { sampleOperatorMetrics } from "@/__tests__/features/operator/test-helpers";

describe("OperatorMetricsGrid", () => {
  it("renders the six cards, stale badges, and destructive emphasis for pending work", () => {
    renderWithProviders(
      <OperatorMetricsGrid
        isLoading={false}
        isStale
        metrics={sampleOperatorMetrics}
      />,
    );

    expect(screen.getByText("Active Executions")).toBeInTheDocument();
    expect(screen.getByText("Queued Steps")).toBeInTheDocument();
    expect(screen.getByText("Pending Approvals")).toBeInTheDocument();
    expect(screen.getByText("Recent Failures (1h)")).toBeInTheDocument();
    expect(screen.getByText("Avg Latency (p50)")).toBeInTheDocument();
    expect(screen.getByText("Fleet Health Score")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("41")).toBeInTheDocument();
    expect(screen.getByText("842")).toBeInTheDocument();
    expect(screen.getAllByText("Stale")).toHaveLength(6);

    const pendingCard = screen
      .getByText("Pending Approvals")
      .closest('[class*="border-destructive/30"]');
    const failuresCard = screen
      .getByText("Recent Failures (1h)")
      .closest('[class*="border-destructive/30"]');

    expect(pendingCard).not.toBeNull();
    expect(failuresCard).not.toBeNull();
  });

  it("renders loading skeletons while metrics are loading", () => {
    const { container } = renderWithProviders(
      <OperatorMetricsGrid isLoading metrics={undefined} />,
    );

    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(12);
  });
});
