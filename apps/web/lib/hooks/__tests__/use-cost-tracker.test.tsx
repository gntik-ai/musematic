import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useCostTracker } from "@/lib/hooks/use-cost-tracker";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { server } from "@/vitest.setup";

describe("useCostTracker", () => {
  beforeEach(() => {
    useExecutionMonitorStore.getState().reset();
    useExecutionMonitorStore.setState({
      totalTokens: 548,
      totalCostUsd: 0.0234,
    });
  });

  it("returns live totals from the execution monitor store and lazily loads a breakdown", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-1"), {
      wrapper: Wrapper,
    });

    expect(result.current.totalTokens).toBe(548);
    expect(result.current.totalCostUsd).toBe(0.0234);
    expect(result.current.costBreakdown).toEqual([]);

    await act(async () => {
      await result.current.expandedBreakdown();
    });

    await waitFor(() => {
      expect(result.current.breakdownQuery.isSuccess).toBe(true);
    });

    const breakdown = result.current.breakdownQuery.data;
    if (!breakdown) {
      throw new Error("Expected execution breakdown to be loaded");
    }

    expect(breakdown).toMatchObject({
      executionId: "execution-1",
      totalTokens: 708,
      totalCostUsd: 0.0314,
    });
    expect(breakdown.stepBreakdown[0]).toMatchObject({
      stepId: "evaluate_risk",
      stepName: "Evaluate Risk",
      costUsd: 0.0234,
      percentageOfTotal: expect.closeTo(74.522, 3),
    });
    expect(useExecutionMonitorStore.getState().costBreakdown[0]).toMatchObject({
      stepId: "evaluate_risk",
      totalTokens: 548,
    });
  });

  it("returns null without fetching analytics when no execution id is available", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker(null), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(result.current.expandedBreakdown()).resolves.toBeNull();
    });

    expect(result.current.breakdownQuery.fetchStatus).toBe("idle");
    expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([]);
  });

  it("assigns zero percentages when analytics returns no costed steps", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-missing"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(result.current.expandedBreakdown()).resolves.toMatchObject({
        executionId: "execution-missing",
        totalCostUsd: 0,
        stepBreakdown: [],
      });
    });

    expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([]);
  });

  it("keeps percentageOfTotal at zero when analytics rows have zero total cost", async () => {
    server.use(
      http.get("*/api/v1/analytics/usage", () =>
        HttpResponse.json({
          items: [
            {
              step_id: "zero-cost",
              step_name: "Zero Cost",
              input_tokens: 4,
              output_tokens: 2,
              total_tokens: 6,
              cost_usd: 0,
            },
          ],
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-zero"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(result.current.expandedBreakdown()).resolves.toMatchObject({
        executionId: "execution-zero",
        totalCostUsd: 0,
      });
    });

    expect(result.current.breakdownQuery.data?.stepBreakdown[0]).toMatchObject({
      stepId: "zero-cost",
      percentageOfTotal: 0,
    });
  });

  it("falls back to agent and model identifiers when step metadata is missing", async () => {
    server.use(
      http.get("*/api/v1/analytics/usage", () =>
        HttpResponse.json({
          items: [
            {
              agent_fqn: "trust/risk-evaluator",
              input_tokens: 4,
              output_tokens: 2,
              total_tokens: 6,
              cost_usd: 0.5,
            },
            {
              model_id: "gpt-5.4-mini",
              input_tokens: 1,
              output_tokens: 1,
              total_tokens: 2,
              cost_usd: 0.25,
            },
            {
              total_tokens: 0,
            },
            {
              step_name: "Missing Totals",
              cost_usd: 0.1,
            },
          ],
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-fallback"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.expandedBreakdown();
    });

    expect(result.current.breakdownQuery.data?.stepBreakdown).toEqual([
      expect.objectContaining({
        stepId: "trust/risk-evaluator",
        stepName: "trust/risk-evaluator",
      }),
      expect.objectContaining({
        stepId: "",
        stepName: "gpt-5.4-mini",
      }),
      expect.objectContaining({
        stepId: "",
        stepName: "Missing Totals",
        totalTokens: 0,
        costUsd: 0.1,
      }),
      expect.objectContaining({
        stepId: "",
        stepName: "Unknown step",
        inputTokens: 0,
        outputTokens: 0,
        totalTokens: 0,
        costUsd: 0,
      }),
    ]);
  });

  it("normalizes an analytics response without an items array", async () => {
    server.use(
      http.get("*/api/v1/analytics/usage", () =>
        HttpResponse.json({}),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-empty-items"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(result.current.expandedBreakdown()).resolves.toMatchObject({
        executionId: "execution-empty-items",
        totalInputTokens: 0,
        totalOutputTokens: 0,
        totalTokens: 0,
        totalCostUsd: 0,
        stepBreakdown: [],
      });
    });
  });

  it("returns null and preserves the existing breakdown when analytics refetch fails", async () => {
    useExecutionMonitorStore.setState({
      costBreakdown: [
        {
          stepId: "existing",
          stepName: "Existing",
          inputTokens: 1,
          outputTokens: 1,
          totalTokens: 2,
          costUsd: 0.01,
          percentageOfTotal: 100,
        },
      ],
    });
    server.use(
      http.get("*/api/v1/analytics/usage", () =>
        HttpResponse.json(
          {
            error: {
              code: "ANALYTICS_UNAVAILABLE",
              message: "Analytics service unavailable",
            },
          },
          { status: 503 },
        ),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useCostTracker("execution-error"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await expect(result.current.expandedBreakdown()).resolves.toBeNull();
    });

    expect(result.current.breakdownQuery.data).toBeUndefined();
    expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([
      expect.objectContaining({
        stepId: "existing",
      }),
    ]);
  });
});
