import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BudgetUtilizationBar } from "@/components/features/analytics/BudgetUtilizationBar";

describe("BudgetUtilizationBar", () => {
  it("shows the configured budget percentage", () => {
    render(
      <BudgetUtilizationBar
        allocatedBudgetUsd={200}
        currentSpendUsd={150}
        workspaceName="Core Workspace"
      />,
    );

    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("$150.00 of $200.00")).toBeInTheDocument();
  });

  it("shows the no budget configured message when no budget is present", () => {
    render(
      <BudgetUtilizationBar
        allocatedBudgetUsd={null}
        currentSpendUsd={42}
        workspaceName="Core Workspace"
      />,
    );

    expect(screen.getByText("No budget configured")).toBeInTheDocument();
  });
});
