import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TaskPlanViewer } from "@/components/features/workflows/monitor/TaskPlanViewer";
import { renderWithProviders } from "@/test-utils/render";
import { taskPlanFixtures } from "@/mocks/handlers/task-plan";
import { normalizeTaskPlanRecord } from "@/types/task-plan";

const taskPlan = normalizeTaskPlanRecord(
  taskPlanFixtures.plansByExecutionStep["execution-1:evaluate_risk"]!,
);

describe("TaskPlanViewer", () => {
  it("renders the selected agent, candidates, and parameter provenance", () => {
    renderWithProviders(<TaskPlanViewer taskPlan={taskPlan} />);

    expect(screen.getByText("Selected agent")).toBeInTheDocument();
    expect(screen.getAllByText("trust/risk-evaluator")).toHaveLength(2);
    expect(screen.getByText("96%")).toBeInTheDocument();
    expect(screen.getByText("execution_context")).toBeInTheDocument();
    expect(screen.getByText(/cust-123/)).toBeInTheDocument();
  });

  it("shows the empty state for non-agent steps", () => {
    renderWithProviders(<TaskPlanViewer taskPlan={null} />);

    expect(screen.getByText("No task plan available")).toBeInTheDocument();
  });
});
