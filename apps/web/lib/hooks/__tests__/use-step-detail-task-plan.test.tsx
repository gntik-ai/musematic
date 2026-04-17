import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useStepDetail } from "@/lib/hooks/use-step-detail";
import { useTaskPlan } from "@/lib/hooks/use-task-plan";

describe("useStepDetail and useTaskPlan", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("loads step detail when execution and step ids are available", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useStepDetail("execution-1", "evaluate_risk"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      executionId: "execution-1",
      stepId: "evaluate_risk",
      status: "running",
      tokenUsage: {
        totalTokens: 548,
      },
    });
  });

  it("keeps the step-detail query idle until a step is selected", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useStepDetail("execution-1", null), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("lazy-loads task plans only when the tab is enabled", async () => {
    const { Wrapper } = createHookWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useTaskPlan("execution-1", "evaluate_risk", enabled),
      {
        initialProps: { enabled: false },
        wrapper: Wrapper,
      },
    );

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();

    rerender({ enabled: true });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      executionId: "execution-1",
      stepId: "evaluate_risk",
      selectedAgentFqn: "trust/risk-evaluator",
    });
    expect(result.current.data?.candidateAgents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          fqn: "trust/risk-evaluator",
          isSelected: true,
        }),
      ]),
    );
  });

  it("keeps the task-plan query idle until both identifiers and the enabled flag are present", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useTaskPlan(null, undefined, true), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("requires both execution and step ids independently", () => {
    const { Wrapper } = createHookWrapper();
    const stepDetailHook = renderHook(
      () => useStepDetail(null, "evaluate_risk"),
      {
        wrapper: Wrapper,
      },
    );
    const taskPlanHook = renderHook(
      () => useTaskPlan("execution-1", null, true),
      {
        wrapper: Wrapper,
      },
    );

    expect(stepDetailHook.result.current.fetchStatus).toBe("idle");
    expect(taskPlanHook.result.current.fetchStatus).toBe("idle");
  });

  it("treats undefined identifiers the same as missing identifiers", () => {
    const { Wrapper } = createHookWrapper();
    const stepDetailHook = renderHook(
      () => useStepDetail(undefined, "evaluate_risk"),
      {
        wrapper: Wrapper,
      },
    );
    const taskPlanHook = renderHook(
      () => useTaskPlan("execution-1", undefined, true),
      {
        wrapper: Wrapper,
      },
    );

    expect(stepDetailHook.result.current.fetchStatus).toBe("idle");
    expect(taskPlanHook.result.current.fetchStatus).toBe("idle");
  });
});
