import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EditorToolbar } from "@/components/features/workflows/editor/EditorToolbar";
import { renderWithProviders } from "@/test-utils/render";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";
import { workflowFixtures } from "@/mocks/handlers/workflows";
import { useWorkspaceStore } from "@/store/workspace-store";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("EditorToolbar", () => {
  beforeEach(() => {
    pushMock.mockReset();
    useWorkflowEditorStore.getState().reset();
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: "workspace-1",
        name: "Workspace One",
        slug: "workspace-one",
        description: null,
        memberCount: 5,
        createdAt: "2026-04-13T08:00:00.000Z",
      },
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });
  });

  it("disables the save button when the editor is clean", () => {
    useWorkflowEditorStore.setState((state) => ({
      ...state,
      yamlContent: "name: Demo",
      isDirty: false,
    }));

    renderWithProviders(<EditorToolbar />);

    expect(
      screen.getByRole("button", { name: /create workflow/i }),
    ).toBeDisabled();
  });

  it("creates a workflow and redirects to the editor page", async () => {
    const user = userEvent.setup();

    useWorkflowEditorStore.setState((state) => ({
      ...state,
      yamlContent: [
        "name: Incident Review",
        "description: Handles the full incident review process",
        "steps:",
        "  collect_context:",
        "    type: agent_task",
      ].join("\n"),
      isDirty: true,
    }));

    renderWithProviders(<EditorToolbar />);

    await user.click(screen.getByRole("button", { name: /create workflow/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/workflow-editor-monitor/workflow-4");
    });

    expect(workflowFixtures.definitions).toHaveLength(4);
    expect(useWorkflowEditorStore.getState().isDirty).toBe(false);
  });
});
