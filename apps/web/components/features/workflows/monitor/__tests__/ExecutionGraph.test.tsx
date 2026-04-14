import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExecutionGraph } from "@/components/features/workflows/monitor/ExecutionGraph";
import { renderWithProviders } from "@/test-utils/render";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { workflowFixtures } from "@/mocks/handlers/workflows";
import { normalizeWorkflowVersion } from "@/types/workflows";

vi.mock("@xyflow/react", () => {
  const ReactFlow = ({
    nodes,
    edges,
    nodeTypes,
    children,
  }: {
    nodes: Array<{ id: string; type?: string; data: Record<string, unknown> }>;
    edges: Array<unknown>;
    nodeTypes: Record<string, React.ComponentType<Record<string, unknown>>>;
    children?: React.ReactNode;
  }) => (
    <div data-testid="react-flow">
      <div data-testid="node-count">{nodes.length}</div>
      <div data-testid="edge-count">{edges.length}</div>
      {nodes.map((node) => {
        const Component = nodeTypes[node.type ?? "execution-step"];
        return Component ? <Component key={node.id} data={node.data} /> : null;
      })}
      {children}
    </div>
  );

  return {
    Background: () => <div data-testid="flow-background" />,
    Controls: () => <div data-testid="flow-controls" />,
    Handle: () => <div data-testid="flow-handle" />,
    MarkerType: { ArrowClosed: "arrow-closed" },
    MiniMap: () => <div data-testid="flow-minimap" />,
    Position: { Bottom: "bottom", Top: "top" },
    ReactFlow,
    ReactFlowProvider: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
  };
});

const compiledIr = normalizeWorkflowVersion(
  workflowFixtures.versionsByWorkflowId["workflow-1"]![1]!,
).compiledIr;

describe("ExecutionGraph", () => {
  beforeEach(() => {
    useExecutionMonitorStore.getState().reset();
    useExecutionMonitorStore.setState({
      executionId: "execution-1",
      executionStatus: "running",
      stepStatuses: {
        collect_context: "completed",
        evaluate_risk: "failed",
        approval_gate: "waiting_for_approval",
        finalize_case: "pending",
      },
    });
  });

  it("renders workflow nodes with execution state labels and selects a step on click", async () => {
    renderWithProviders(<ExecutionGraph compiledIr={compiledIr} />);

    expect(await screen.findByRole("img", { name: /Collect Context, Completed/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Evaluate Risk, Failed/i })).toBeInTheDocument();
    expect(screen.getByTestId("node-count")).toHaveTextContent("4");
    expect(screen.getByTestId("edge-count")).toHaveTextContent("3");

    fireEvent.click(screen.getByRole("img", { name: /Approval Gate, Awaiting approval/i }));

    expect(useExecutionMonitorStore.getState().selectedStepId).toBe("approval_gate");
  });

  it("supports keyboard navigation between nodes and selects with Enter", async () => {
    renderWithProviders(<ExecutionGraph compiledIr={compiledIr} />);

    const collectContext = await screen.findByRole("img", {
      name: /Collect Context, Completed/i,
    });
    collectContext.focus();

    fireEvent.keyDown(collectContext, { key: "ArrowRight" });

    const evaluateRisk = screen.getByRole("img", { name: /Evaluate Risk, Failed/i });
    expect(evaluateRisk).toHaveFocus();

    fireEvent.keyDown(evaluateRisk, { key: "Enter" });

    expect(useExecutionMonitorStore.getState().selectedStepId).toBe("evaluate_risk");
  });
});
