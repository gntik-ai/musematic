import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TrajectoryViz } from "@/components/features/execution/trajectory-viz";
import { renderWithProviders } from "@/test-utils/render";

vi.mock("@/lib/hooks/use-execution-trajectory", () => ({
  useExecutionTrajectory: () => ({
    data: [
      {
        index: 1,
        toolOrAgentFqn: "risk:triage-lead",
        startedAt: "2026-04-13T09:00:00.000Z",
        durationMs: 320,
        tokenUsage: { prompt: 0, completion: 24 },
        efficiencyScore: "high",
        summary: "First trajectory step.",
      },
      {
        index: 2,
        toolOrAgentFqn: "Agent no longer exists",
        startedAt: "2026-04-13T09:00:12.000Z",
        durationMs: 180,
        tokenUsage: { prompt: 0, completion: 18 },
        efficiencyScore: "unscored",
        summary: "Fallback step.",
      },
    ],
    isLoading: false,
  }),
}));

describe("TrajectoryViz", () => {
  it("renders trajectory rows with efficiency badges and highlights the anchored step", () => {
    renderWithProviders(
      <TrajectoryViz anchorStepIndex={2} executionId="execution-1" />,
    );

    expect(screen.getByText("risk:triage-lead")).toBeInTheDocument();
    expect(screen.getByText("High efficiency")).toBeInTheDocument();
    expect(screen.getByText("Unscored")).toBeInTheDocument();
    expect(screen.getByTestId("trajectory-step-highlight-2")).toBeInTheDocument();
  });
});
