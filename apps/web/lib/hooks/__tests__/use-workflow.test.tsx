import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useWorkflow } from "@/lib/hooks/use-workflow";

describe("useWorkflow", () => {
  it("loads a workflow with its current version when no version id is provided", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useWorkflow("workflow-1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      workflow: {
        id: "workflow-1",
        currentVersionId: "workflow-1-version-2",
        name: "KYC Onboarding",
      },
      version: {
        id: "workflow-1-version-2",
        versionNumber: 2,
      },
    });
  });

  it("loads an explicit workflow version and stays idle without a workflow id", async () => {
    const { Wrapper } = createHookWrapper();
    const versionedHook = renderHook(
      () => useWorkflow("workflow-1", "workflow-1-version-1"),
      {
        wrapper: Wrapper,
      },
    );
    const disabledHook = renderHook(() => useWorkflow(null), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(versionedHook.result.current.isSuccess).toBe(true);
    });

    expect(versionedHook.result.current.data).toMatchObject({
      version: {
        id: "workflow-1-version-1",
        versionNumber: 1,
      },
    });
    expect(disabledHook.result.current.fetchStatus).toBe("idle");
  });

  it("treats an explicit null version id the same as the current version", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useWorkflow("workflow-1", null), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.version).toMatchObject({
      id: "workflow-1-version-2",
      versionNumber: 2,
    });
  });
});
