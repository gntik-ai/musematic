import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkflowGraphPreview } from "@/components/features/workflows/editor/WorkflowGraphPreview";
import { renderWithProviders } from "@/test-utils/render";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";

vi.mock("@xyflow/react", () => {
  const ReactFlow = ({
    nodes,
    edges,
    children,
  }: {
    nodes: Array<{ id: string; data: { label: string } }>;
    edges: Array<unknown>;
    children?: React.ReactNode;
  }) => (
    <div data-testid="react-flow">
      <div data-testid="node-count">{nodes.length}</div>
      <div data-testid="edge-count">{edges.length}</div>
      {nodes.map((node) => (
        <div key={node.id}>{node.data.label}</div>
      ))}
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

describe("WorkflowGraphPreview", () => {
  beforeEach(() => {
    useWorkflowEditorStore.getState().reset();
  });

  it("renders nodes and edges from YAML content", async () => {
    useWorkflowEditorStore.setState((state) => ({
      ...state,
      yamlContent: [
        "name: Demo Workflow",
        "steps:",
        "  collect_context:",
        "    type: agent_task",
        "  evaluate_risk:",
        "    type: agent_task",
        "    dependencies: [collect_context]",
        "  approval_gate:",
        "    type: approval_gate",
        "    dependencies: [evaluate_risk]",
        "  finalize_case:",
        "    type: agent_task",
        "    dependencies: [approval_gate]",
      ].join("\n"),
      isDirty: true,
    }));

    renderWithProviders(<WorkflowGraphPreview />);

    expect(await screen.findByText("Collect Context")).toBeInTheDocument();
    expect(screen.getByText("Approval Gate")).toBeInTheDocument();
    expect(screen.getByText(/4 steps, 3 dependencies/i)).toBeInTheDocument();
    expect(screen.getByTestId("node-count")).toHaveTextContent("4");
    expect(screen.getByTestId("edge-count")).toHaveTextContent("3");

    await waitFor(() => {
      expect(useWorkflowEditorStore.getState().graphNodes).toHaveLength(4);
      expect(useWorkflowEditorStore.getState().graphEdges).toHaveLength(3);
      expect(useWorkflowEditorStore.getState().parseError).toBeNull();
    });
  });

  it("shows a parse error for circular dependencies", async () => {
    useWorkflowEditorStore.setState((state) => ({
      ...state,
      yamlContent: [
        "name: Loop Workflow",
        "steps:",
        "  first_step:",
        "    type: agent_task",
        "    dependencies: [second_step]",
        "  second_step:",
        "    type: agent_task",
        "    dependencies: [first_step]",
      ].join("\n"),
      isDirty: true,
    }));

    renderWithProviders(<WorkflowGraphPreview />);

    expect(
      await screen.findByText(/circular dependency detected/i),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(useWorkflowEditorStore.getState().parseError).toMatch(
        /Circular dependency detected/i,
      );
    });
  });
});
