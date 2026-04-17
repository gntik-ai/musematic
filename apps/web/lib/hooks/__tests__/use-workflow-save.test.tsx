import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  useCreateWorkflow,
  useUpdateWorkflow,
} from "@/lib/hooks/use-workflow-save";
import { workflowFixtures } from "@/mocks/handlers/workflows";

describe("useWorkflowSave", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a workflow and invalidates list and detail queries", async () => {
    const { client, Wrapper } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useCreateWorkflow(), {
      wrapper: Wrapper,
    });

    let createdWorkflow: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      createdWorkflow = await result.current.mutateAsync({
        workspaceId: "workspace-1",
        name: "Fraud Triage",
        description: "Workflow for exception handling",
        yamlContent: "name: Fraud Triage",
      });
    });

    expect(createdWorkflow!).toMatchObject({
      id: "workflow-4",
      name: "Fraud Triage",
      description: "Workflow for exception handling",
    });
    expect(workflowFixtures.definitions).toContainEqual(
      expect.objectContaining({
        id: "workflow-4",
        name: "Fraud Triage",
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["workflows"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.detail("workflow-4"),
    });
  });

  it("updates a workflow, creates a new version, and invalidates related queries", async () => {
    const { client, Wrapper } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUpdateWorkflow(), {
      wrapper: Wrapper,
    });

    let updatedWorkflow: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      updatedWorkflow = await result.current.mutateAsync({
        workflowId: "workflow-1",
        yamlContent: "name: KYC Onboarding\nversion: 3.0.0",
        description: "Updated KYC workflow",
      });
    });

    expect(updatedWorkflow!).toMatchObject({
      id: "workflow-1",
      currentVersionNumber: 3,
      description: "Updated KYC workflow",
    });
    expect(workflowFixtures.versionsByWorkflowId["workflow-1"]).toHaveLength(3);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["workflows"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.detail("workflow-1"),
    });
  });

  it("normalizes omitted descriptions to null when saving workflows", async () => {
    const { Wrapper } = createHookWrapper();
    const createHook = renderHook(() => useCreateWorkflow(), {
      wrapper: Wrapper,
    });
    const updateHook = renderHook(() => useUpdateWorkflow(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await createHook.result.current.mutateAsync({
        workspaceId: "workspace-1",
        name: "No Description Workflow",
        yamlContent: "name: No Description Workflow",
      });
      await updateHook.result.current.mutateAsync({
        workflowId: "workflow-2",
        yamlContent: "name: Campaign Health\nversion: 2.0.0",
      });
    });

    expect(workflowFixtures.definitions).toContainEqual(
      expect.objectContaining({
        name: "No Description Workflow",
        description: null,
      }),
    );
    expect(workflowFixtures.definitions.find((item) => item.id === "workflow-2")).toMatchObject({
      description: "Campaign Health managed in Workflow Studio",
    });
  });
});
