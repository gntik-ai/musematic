import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  useApprovalDecision,
  useCancelExecution,
  useInjectVariable,
  usePauseExecution,
  useResumeExecution,
  useRetryStep,
  useSkipStep,
} from "@/lib/hooks/use-execution-controls";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { server } from "@/vitest.setup";

function seedExecutionMonitorState() {
  useExecutionMonitorStore.getState().reset();
  useExecutionMonitorStore.setState({
    executionId: "execution-1",
    executionStatus: "running",
    stepStatuses: {
      evaluate_risk: "failed",
      approval_gate: "waiting_for_approval",
      finalize_case: "pending",
    },
  });
}

describe("useExecutionControls", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    seedExecutionMonitorState();
  });

  it("applies the pause action optimistically and invalidates execution queries on success", async () => {
    let unblockRequest = () => {};
    const requestBlocked = new Promise<void>((resolve) => {
      unblockRequest = () => {
        resolve();
      };
    });

    server.use(
      http.post("*/api/v1/executions/:executionId/pause", async () => {
        await requestBlocked;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { client, Wrapper } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => usePauseExecution("execution-1"), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate(undefined);
    });

    expect(useExecutionMonitorStore.getState().executionStatus).toBe("paused");

    unblockRequest();

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.execution("execution-1"),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: workflowQueryKeys.executionState("execution-1"),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["executions", "journal", "execution-1"],
    });
  });

  it("resumes an execution optimistically", async () => {
    useExecutionMonitorStore.setState({ executionStatus: "paused" });

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useResumeExecution("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync(undefined);
    });

    expect(useExecutionMonitorStore.getState().executionStatus).toBe("running");
  });

  it("restores the previous snapshot when cancel fails", async () => {
    server.use(
      http.post("*/api/v1/executions/:executionId/cancel", () =>
        HttpResponse.json(
          {
            error: {
              code: "EXECUTION_CANCEL_FAILED",
              message: "Unable to cancel execution",
            },
          },
          { status: 500 },
        ),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCancelExecution("execution-1"), {
      wrapper: Wrapper,
    });

    await expect(
      result.current.mutateAsync({ reason: "Operator requested stop" }),
    ).rejects.toMatchObject({
      code: "EXECUTION_CANCEL_FAILED",
      status: 500,
    });
    expect(useExecutionMonitorStore.getState().executionStatus).toBe("running");
  });

  it("cancels an execution optimistically when no reason is provided", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCancelExecution("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({});
    });

    expect(useExecutionMonitorStore.getState().executionStatus).toBe("canceled");
  });

  it("updates step state when retrying and skipping a step", async () => {
    const { Wrapper } = createHookWrapper();
    const retryHook = renderHook(() => useRetryStep("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await retryHook.result.current.mutateAsync({ stepId: "evaluate_risk" });
    });

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      executionStatus: "running",
      stepStatuses: expect.objectContaining({
        evaluate_risk: "running",
      }),
    });

    const skipHook = renderHook(() => useSkipStep("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await skipHook.result.current.mutateAsync({
        stepId: "finalize_case",
        reason: "Step no longer required",
      });
    });

    expect(useExecutionMonitorStore.getState().stepStatuses.finalize_case).toBe(
      "skipped",
    );
  });

  it("restores step state when a retry mutation fails", async () => {
    server.use(
      http.post("*/api/v1/executions/:executionId/steps/:stepId/retry", () =>
        HttpResponse.json(
          {
            error: {
              code: "STEP_RETRY_FAILED",
              message: "Retry rejected",
            },
          },
          { status: 409 },
        ),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useRetryStep("execution-1"), {
      wrapper: Wrapper,
    });

    await expect(
      result.current.mutateAsync({ stepId: "evaluate_risk" }),
    ).rejects.toMatchObject({
      code: "STEP_RETRY_FAILED",
      status: 409,
    });

    expect(useExecutionMonitorStore.getState().stepStatuses.evaluate_risk).toBe(
      "failed",
    );
  });

  it("sends inject-variable payloads without mutating monitor state", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/executions/:executionId/hot-change", async ({ request }) => {
        requestBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useInjectVariable("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        variableName: "risk_threshold",
        value: 0.9,
        reason: "Escalated by operator",
      });
    });

    expect(requestBody).toEqual({
      variable_name: "risk_threshold",
      value: 0.9,
      reason: "Escalated by operator",
    });
    expect(useExecutionMonitorStore.getState().executionStatus).toBe("running");
  });

  it("applies approval decisions to the selected step", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useApprovalDecision("execution-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        stepId: "approval_gate",
        decision: "rejected",
        comment: "Policy exception not approved",
      });
    });

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      executionStatus: "running",
      stepStatuses: expect.objectContaining({
        approval_gate: "failed",
      }),
    });

    await act(async () => {
      await result.current.mutateAsync({
        stepId: "approval_gate",
        decision: "approved",
      });
    });

    expect(useExecutionMonitorStore.getState().stepStatuses.approval_gate).toBe(
      "completed",
    );
  });
});
