import { beforeEach, describe, expect, it } from "vitest";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";

describe("workflow-editor-store", () => {
  beforeEach(() => {
    useWorkflowEditorStore.getState().reset();
  });

  it("marks the editor dirty when yaml content changes", () => {
    useWorkflowEditorStore.getState().setYamlContent("name: KYC Onboarding");

    expect(useWorkflowEditorStore.getState()).toMatchObject({
      yamlContent: "name: KYC Onboarding",
      isDirty: true,
    });
  });

  it("tracks validation, graph, parse, and saving state", () => {
    useWorkflowEditorStore.getState().setValidationErrors([
      {
        line: 3,
        column: 5,
        message: "Unknown step type",
        severity: "error",
        path: "steps.review.type",
      },
    ]);
    useWorkflowEditorStore.getState().setGraphState(
      [
        {
          id: "review",
          type: "step",
          position: { x: 80, y: 160 },
          data: {
            stepId: "review",
            label: "Review",
            stepType: "agent_task",
            agentFqn: "trust/risk-evaluator",
            hasValidationError: true,
          },
        },
      ],
      [
        {
          id: "edge-1",
          source: "collect",
          target: "review",
          type: "smoothstep",
        },
      ],
    );
    useWorkflowEditorStore.getState().setParseError("Invalid indentation");
    useWorkflowEditorStore.getState().setIsSaving(true);

    expect(useWorkflowEditorStore.getState()).toMatchObject({
      validationErrors: [
        expect.objectContaining({
          message: "Unknown step type",
        }),
      ],
      graphNodes: [
        expect.objectContaining({
          id: "review",
        }),
      ],
      graphEdges: [
        expect.objectContaining({
          id: "edge-1",
        }),
      ],
      parseError: "Invalid indentation",
      isSaving: true,
    });
  });

  it("marks a version as saved and can reset to the initial state", () => {
    useWorkflowEditorStore.getState().setYamlContent("name: Campaign Health");
    useWorkflowEditorStore.getState().setIsSaving(true);

    useWorkflowEditorStore.getState().markSaved("workflow-1-version-3");

    expect(useWorkflowEditorStore.getState()).toMatchObject({
      yamlContent: "name: Campaign Health",
      isDirty: false,
      isSaving: false,
      lastSavedVersionId: "workflow-1-version-3",
    });

    useWorkflowEditorStore.getState().reset();

    expect(useWorkflowEditorStore.getState()).toMatchObject({
      yamlContent: "",
      validationErrors: [],
      isDirty: false,
      isSaving: false,
      lastSavedVersionId: null,
      graphNodes: [],
      graphEdges: [],
      parseError: null,
    });
  });
});
