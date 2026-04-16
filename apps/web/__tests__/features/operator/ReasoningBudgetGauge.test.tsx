import { screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { ReasoningBudgetGauge } from "@/components/features/operator/ReasoningBudgetGauge";
import { renderWithProviders } from "@/test-utils/render";
import { sampleReasoningBudgetUtilization } from "@/__tests__/features/operator/test-helpers";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <div data-testid="responsive-container">{children}</div>,
  RadialBarChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  RadialBar: ({ fill }: { fill: string }) => <path data-testid="radial-bar" fill={fill} />,
}));

describe("ReasoningBudgetGauge", () => {
  it("renders critical utilization with destructive gauge tone and pressure label", () => {
    const { container } = renderWithProviders(
      <ReasoningBudgetGauge
        isLoading={false}
        utilization={sampleReasoningBudgetUtilization}
      />,
    );

    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("12 active executions")).toBeInTheDocument();
    expect(screen.getByText("Capacity pressure")).toBeInTheDocument();
    expect(
      container.querySelector('[fill="hsl(var(--destructive))"]'),
    ).not.toBeNull();
  });

  it("renders the unavailable state when the budget query fails", () => {
    renderWithProviders(
      <ReasoningBudgetGauge error isLoading={false} utilization={undefined} />,
    );

    expect(screen.getByText("Budget data unavailable")).toBeInTheDocument();
  });
});
