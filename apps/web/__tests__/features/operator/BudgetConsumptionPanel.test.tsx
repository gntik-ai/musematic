import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BudgetConsumptionPanel } from "@/components/features/operator/BudgetConsumptionPanel";
import { renderWithProviders } from "@/test-utils/render";
import { sampleBudgetStatus } from "@/__tests__/features/operator/test-helpers";

describe("BudgetConsumptionPanel", () => {
  it("renders four progress bars with threshold colors and final-value banner for completed executions", () => {
    renderWithProviders(
      <BudgetConsumptionPanel budget={sampleBudgetStatus} isLoading={false} />,
    );

    expect(
      screen.getByText("Execution completed — final values"),
    ).toBeInTheDocument();

    const progressBars = screen.getAllByRole("progressbar");
    expect(progressBars).toHaveLength(4);
    expect(progressBars[0]?.firstElementChild).toHaveClass("bg-blue-500");
    expect(progressBars[1]?.firstElementChild).toHaveClass("bg-yellow-500");
    expect(progressBars[2]?.firstElementChild).toHaveClass("bg-red-500");
    expect(
      screen.getByText("Tool invocations").parentElement?.querySelector("svg"),
    ).not.toBeNull();
  });
});
