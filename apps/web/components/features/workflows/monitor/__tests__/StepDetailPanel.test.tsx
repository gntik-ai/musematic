import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { StepDetailPanel } from "@/components/features/workflows/monitor/StepDetailPanel";
import { renderWithProviders } from "@/test-utils/render";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { taskPlanFixtures } from "@/mocks/handlers/task-plan";
import { executionFixtures } from "@/mocks/handlers/executions";
import { server } from "@/vitest.setup";

function selectStep(stepId: string, status: "completed" | "waiting_for_approval" = "completed") {
  useExecutionMonitorStore.getState().reset();
  useExecutionMonitorStore.setState({
    executionId: "execution-1",
    executionStatus: "running",
    selectedStepId: stepId,
    activeDetailTab: "overview",
    stepStatuses: {
      [stepId]: status,
    },
  });
}

describe("StepDetailPanel", () => {
  beforeEach(() => {
    selectStep("evaluate_risk");
    const approvalGateDetail =
      executionFixtures.stepDetailsByExecutionId["execution-1"]?.approval_gate;
    executionFixtures.stepDetailsByExecutionId["execution-1"] = {
      ...executionFixtures.stepDetailsByExecutionId["execution-1"],
      approval_gate: {
        ...(approvalGateDetail ?? {
          step_id: "approval_gate",
          execution_id: "execution-1",
          status: "waiting_for_approval",
          inputs: { customer_id: "cust-123" },
          outputs: null,
          started_at: new Date("2026-04-13T09:03:00.000Z").toISOString(),
          completed_at: null,
          duration_ms: null,
          context_quality_score: null,
          error: null,
          token_usage: null,
        }),
        status: "waiting_for_approval",
        started_at: new Date("2026-04-13T09:03:00.000Z").toISOString(),
      },
    };
  });

  it("renders the overview tab and lazy-loads the task plan only when requested", async () => {
    let taskPlanCalls = 0;

    server.use(
      http.get("*/api/v1/executions/:executionId/task-plan/:stepId", ({ params }) => {
        taskPlanCalls += 1;
        return HttpResponse.json(
          taskPlanFixtures.plansByExecutionStep[
            `${String(params.executionId)}:${String(params.stepId)}`
          ],
        );
      }),
    );

    renderWithProviders(<StepDetailPanel executionId="execution-1" />);

    expect(await screen.findByText("Step detail")).toBeInTheDocument();
    expect(await screen.findByText("Inputs")).toBeInTheDocument();
    expect(taskPlanCalls).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: /Task Plan/i }));

    expect(await screen.findByText("Selected agent")).toBeInTheDocument();
    expect(taskPlanCalls).toBe(1);
  });

  it("shows approval actions for steps waiting for approval and closes on Escape", async () => {
    selectStep("approval_gate", "waiting_for_approval");

    renderWithProviders(<StepDetailPanel executionId="execution-1" />);

    expect(await screen.findByText("Approval required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().selectedStepId).toBeNull();
    });
  });
});
