import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  useExecution,
  useExecutionList,
  useExecutionState,
  useStartExecution,
} from "@/lib/hooks/use-execution-list";
import { executionFixtures } from "@/mocks/handlers/executions";

describe("useExecutionList", () => {
  it("loads paginated executions for a workflow", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useExecutionList("workflow-1", { limit: 1 }),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.pages[0]?.items).toEqual([
      expect.objectContaining({
        id: "execution-1",
        workflowId: "workflow-1",
      }),
    ]);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages[1]?.items).toEqual([
        expect.objectContaining({
          id: "execution-2",
          workflowId: "workflow-1",
        }),
      ]);
    });
  });

  it("starts an execution and invalidates execution queries for the workflow", async () => {
    const { client, Wrapper } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useStartExecution("workflow-1"), {
      wrapper: Wrapper,
    });

    let execution: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      execution = await result.current.mutateAsync({
        workflowVersionId: "workflow-1-version-2",
      });
    });

    expect(execution!).toMatchObject({
      workflowId: "workflow-1",
      workflowVersionId: "workflow-1-version-2",
      status: "queued",
    });
    expect(executionFixtures.executionsByWorkflowId["workflow-1"]?.[0]).toMatchObject({
      id: execution!.id,
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["executions", "list", "workflow-1"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.execution(execution!.id),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.executionState(execution!.id),
    });
  });

  it("loads execution details and state snapshots for a specific execution", async () => {
    const { Wrapper } = createHookWrapper();
    const detailHook = renderHook(() => useExecution("execution-1"), {
      wrapper: Wrapper,
    });
    const stateHook = renderHook(() => useExecutionState("execution-1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(detailHook.result.current.isSuccess).toBe(true);
      expect(stateHook.result.current.isSuccess).toBe(true);
    });

    expect(detailHook.result.current.data).toMatchObject({
      id: "execution-1",
      workflowId: "workflow-1",
      status: "running",
    });
    expect(stateHook.result.current.data).toMatchObject({
      executionId: "execution-1",
      status: "running",
      lastEventSequence: 4,
    });
  });

  it("keeps execution queries idle when required ids are missing", () => {
    const { Wrapper } = createHookWrapper();
    const listHook = renderHook(() => useExecutionList(null), {
      wrapper: Wrapper,
    });
    const disabledListHook = renderHook(
      () => useExecutionList("workflow-1", { enabled: false }),
      {
        wrapper: Wrapper,
      },
    );
    const detailHook = renderHook(() => useExecution(null), {
      wrapper: Wrapper,
    });
    const stateHook = renderHook(() => useExecutionState(undefined), {
      wrapper: Wrapper,
    });

    expect(listHook.result.current.fetchStatus).toBe("idle");
    expect(disabledListHook.result.current.fetchStatus).toBe("idle");
    expect(detailHook.result.current.fetchStatus).toBe("idle");
    expect(stateHook.result.current.fetchStatus).toBe("idle");
  });
});
