import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExecutionDrilldown } from "@/components/features/operator/ExecutionDrilldown";
import { renderWithProviders } from "@/test-utils/render";

const { replaceSpy } = vi.hoisted(() => ({
  replaceSpy: vi.fn(),
}));

let searchParams = new URLSearchParams("");

vi.mock("next/navigation", () => ({
  usePathname: () => "/operator/executions/execution-1",
  useRouter: () => ({
    replace: replaceSpy,
  }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/hooks/use-execution-drill-down", () => ({
  useExecutionDetail: () => ({
    data: {
      id: "execution-1",
      workflowName: "Risk workflow",
      agentFqn: "risk:triage-lead",
      status: "running",
      elapsedMs: 145000,
    },
    isLoading: false,
  }),
}));

vi.mock("@/components/features/execution/trajectory-viz", () => ({
  TrajectoryViz: ({ anchorStepIndex }: { anchorStepIndex?: number }) => (
    <div data-testid="trajectory-viz">anchor:{anchorStepIndex ?? "none"}</div>
  ),
}));

vi.mock("@/components/features/execution/checkpoint-list", () => ({
  CheckpointList: () => <div data-testid="checkpoint-list">checkpoints</div>,
}));

vi.mock("@/components/features/execution/debate-transcript", () => ({
  DebateTranscript: () => <div data-testid="debate-transcript">debate</div>,
}));

vi.mock("@/components/features/execution/react-cycle-viewer", () => ({
  ReactCycleViewer: () => <div data-testid="react-cycle-viewer">react</div>,
}));

describe("ExecutionDrilldown", () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    searchParams = new URLSearchParams("");
  });

  it("defaults to the trajectory tab and forwards the step anchor", () => {
    searchParams = new URLSearchParams("step=75");

    renderWithProviders(<ExecutionDrilldown executionId="execution-1" />);

    expect(screen.getByTestId("trajectory-viz")).toHaveTextContent("anchor:75");
    expect(screen.queryByTestId("checkpoint-list")).not.toBeInTheDocument();
  });

  it("updates the URL when switching tabs", () => {
    searchParams = new URLSearchParams("step=75");

    renderWithProviders(<ExecutionDrilldown executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Debate" }));

    expect(replaceSpy).toHaveBeenCalledWith(
      "/operator/executions/execution-1?step=75&tab=debate",
    );
  });

  it("renders the checkpoints panel when the tab is present in the URL", () => {
    searchParams = new URLSearchParams("tab=checkpoints");

    renderWithProviders(<ExecutionDrilldown executionId="execution-1" />);

    expect(screen.getByTestId("checkpoint-list")).toBeInTheDocument();
    expect(screen.queryByTestId("trajectory-viz")).not.toBeInTheDocument();
  });
});
