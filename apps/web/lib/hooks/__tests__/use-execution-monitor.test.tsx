import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import type { WsConnectionState, WsEvent } from "@/types/websocket";
import { server } from "@/vitest.setup";

const wsMocks = vi.hoisted(() => ({
  unsubscribeChannelMock: vi.fn(),
  unsubscribeStateMock: vi.fn(),
  subscribeMock: vi.fn(),
  onStateChangeMock: vi.fn(),
  channelHandler: null as ((event: WsEvent<Record<string, unknown>>) => void) | null,
  stateHandler: null as ((state: WsConnectionState) => void) | null,
}));

vi.mock("@/lib/ws", () => ({
  wsClient: {
    subscribe: wsMocks.subscribeMock,
    onStateChange: wsMocks.onStateChangeMock,
  },
}));

import { useExecutionMonitor } from "@/lib/hooks/use-execution-monitor";

describe("useExecutionMonitor", () => {
  beforeEach(() => {
    wsMocks.channelHandler = null;
    wsMocks.stateHandler = null;
    wsMocks.subscribeMock.mockReset();
    wsMocks.onStateChangeMock.mockReset();
    wsMocks.unsubscribeChannelMock.mockReset();
    wsMocks.unsubscribeStateMock.mockReset();

    wsMocks.subscribeMock.mockImplementation(
      (_channel: string, handler: (event: WsEvent<Record<string, unknown>>) => void) => {
        wsMocks.channelHandler = handler;
        return wsMocks.unsubscribeChannelMock;
      },
    );
    wsMocks.onStateChangeMock.mockImplementation((handler: (state: WsConnectionState) => void) => {
      wsMocks.stateHandler = handler;
      return wsMocks.unsubscribeStateMock;
    });

    useExecutionMonitorStore.getState().reset();
  });

  it("reconciles execution state and reacts to websocket events", async () => {
    const { client, Wrapper } = createHookWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { unmount } = renderHook(() => useExecutionMonitor("execution-1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-1");
    });

    expect(wsMocks.subscribeMock).toHaveBeenCalledWith(
      "execution:execution-1",
      expect.any(Function),
    );
    expect(wsMocks.onStateChangeMock).toHaveBeenCalledWith(expect.any(Function));

    act(() => {
      wsMocks.stateHandler?.("connected");
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().wsConnectionStatus).toBe(
        "connected",
      );
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "budget.threshold",
        payload: {
          current_value: 548,
          cost_usd: 0.0234,
          step_id: "evaluate_risk",
        },
        timestamp: "2026-04-13T09:00:00.000Z",
      });
    });

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      totalTokens: 548,
      totalCostUsd: 0.0234,
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "step.state_changed",
        payload: {
          step_id: "evaluate_risk",
          new_status: "completed",
          sequence: 6,
        },
        timestamp: "2026-04-13T09:01:00.000Z",
      });
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([
        expect.objectContaining({
          stepId: "evaluate_risk",
          totalTokens: 548,
          costUsd: 0.0234,
        }),
      ]);
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "event.appended",
        payload: {
          event: {
            id: "execution-1-evt-99",
            execution_id: "execution-1",
            sequence: 99,
            event_type: "STEP_COMPLETED",
            step_id: "evaluate_risk",
            agent_fqn: "trust/risk-evaluator",
            payload: {},
            created_at: "2026-04-13T09:02:00.000Z",
          },
        },
        timestamp: "2026-04-13T09:02:00.000Z",
      });
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().lastEventSequence).toBe(99);
    });

    act(() => {
      wsMocks.stateHandler?.("disconnected");
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().wsConnectionStatus).toBe(
        "disconnected",
      );
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      predicate: expect.any(Function),
    });
    const predicates = invalidateSpy.mock.calls
      .map(([options]) => options?.predicate)
      .filter((predicate): predicate is NonNullable<typeof predicate> => Boolean(predicate));
    const journalPredicate = predicates.find(
      (predicate) =>
        predicate({
          queryKey: ["executions", "journal", "execution-1"],
        } as never) &&
        !predicate({
          queryKey: ["executions", "list", "execution-1"],
        } as never),
    );
    const executionPredicate = predicates[predicates.length - 1];
    if (!executionPredicate) {
      throw new Error("Expected execution predicate to be registered");
    }

    expect(journalPredicate).toBeDefined();
    expect(
      journalPredicate?.({
        queryKey: ["executions", "journal", "execution-1"],
      } as never),
    ).toBe(true);
    expect(
      journalPredicate?.({
        queryKey: ["executions", "journal", "execution-2"],
      } as never),
    ).toBe(false);
    expect(
      journalPredicate?.({
        queryKey: ["executions", "list", "execution-1"],
      } as never),
    ).toBe(false);
    expect(
      journalPredicate?.({
        queryKey: "executions",
      } as never),
    ).toBe(false);
    expect(
      executionPredicate({
        queryKey: ["executions", "detail", "execution-1"],
      } as never),
    ).toBe(true);
    expect(
      executionPredicate({
        queryKey: ["executions", "detail", "execution-2"],
      } as never),
    ).toBe(false);
    expect(
      executionPredicate({
        queryKey: "executions",
      } as never),
    ).toBe(false);

    unmount();

    expect(wsMocks.unsubscribeChannelMock).toHaveBeenCalled();
    expect(wsMocks.unsubscribeStateMock).toHaveBeenCalled();
  });

  it("does nothing until an execution id is provided", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useExecutionMonitor(null), {
      wrapper: Wrapper,
    });

    expect(result.current.wsConnectionStatus).toBe("disconnected");
    expect(wsMocks.subscribeMock).not.toHaveBeenCalled();
    expect(wsMocks.onStateChangeMock).not.toHaveBeenCalled();
  });

  it("handles alternate websocket payload shapes and ignores empty events", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/steps/:stepId", ({ params }) =>
        HttpResponse.json({
          execution_id: String(params.executionId),
          step_id: String(params.stepId),
          status: "pending",
          inputs: {},
          outputs: null,
          started_at: null,
          completed_at: null,
          duration_ms: null,
          context_quality_score: null,
          error: null,
          token_usage: null,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    renderHook(() => useExecutionMonitor("execution-2"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-2");
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-2",
        type: "event.appended",
        payload: {},
        timestamp: "2026-04-13T09:00:00.000Z",
      });
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-2",
        type: "execution.status_changed",
        payload: {
          new_status: "failed",
          event_sequence: 7,
          createdAt: "2026-04-13T09:01:00.000Z",
        },
        timestamp: "2026-04-13T09:01:00.000Z",
      });
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-2",
        type: "step.state_changed",
        payload: {
          stepId: "review_case",
          newStatus: "completed",
          tokens: 12,
          estimated_cost_usd: 0.001,
        },
        timestamp: "2026-04-13T09:02:00.000Z",
      });
    });

    act(() => {
      wsMocks.stateHandler?.("reconnecting");
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState()).toMatchObject({
        executionStatus: "failed",
        wsConnectionStatus: "reconnecting",
        lastEventSequence: 8,
      });
    });
    expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([]);
  });

  it("supports additional synthetic event types and ignores zero-cost thresholds", async () => {
    const { Wrapper } = createHookWrapper();
    renderHook(() => useExecutionMonitor("execution-1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-1");
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "budget.threshold",
        payload: {
          tokens: 0,
          estimated_cost_usd: 0,
        },
        timestamp: "2026-04-13T09:00:00.000Z",
      });
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "approval.requested",
        payload: {
          id: "approval-evt-1",
          event_sequence: 11,
          stepId: "approval_gate",
          occurred_at: "2026-04-13T09:01:00.000Z",
        },
        timestamp: "2026-04-13T09:01:00.000Z",
      });
      wsMocks.channelHandler?.({
        channel: "execution:execution-1",
        type: "hot_change.applied",
        payload: {
          sequence: 12,
        },
        timestamp: "2026-04-13T09:02:00.000Z",
      });
    });

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      totalTokens: 0,
      totalCostUsd: 0,
      lastEventSequence: 12,
      stepStatuses: expect.objectContaining({
        approval_gate: "waiting_for_approval",
      }),
    });
  });

  it("swallows step-detail enrichment failures and ignores non-completed step updates", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/steps/:stepId", () =>
        HttpResponse.json(
          {
            error: {
              code: "STEP_LOOKUP_FAILED",
              message: "Step detail unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    const { Wrapper } = createHookWrapper();
    renderHook(() => useExecutionMonitor("execution-3"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-3");
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-3",
        type: "step.state_changed",
        payload: {
          step_id: "review_case",
          new_status: "running",
          sequence: 3,
        },
        timestamp: "2026-04-13T09:00:00.000Z",
      });
      wsMocks.channelHandler?.({
        channel: "execution:execution-3",
        type: "event.appended",
        payload: {
          event: {
            id: "execution-3-evt-4",
            execution_id: "execution-3",
            sequence: 4,
            event_type: "STEP_COMPLETED",
            step_id: "review_case",
            agent_fqn: "trust/reviewer",
            payload: {},
            created_at: "2026-04-13T09:01:00.000Z",
          },
        },
        timestamp: "2026-04-13T09:01:00.000Z",
      });
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().lastEventSequence).toBe(4);
    });

    expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([]);
  });

  it("ignores websocket event types that do not map to execution events", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/state", ({ params }) =>
        HttpResponse.json({
          execution_id: String(params.executionId),
          status: "running",
          completed_step_ids: [],
          active_step_ids: [],
          pending_step_ids: [],
          failed_step_ids: [],
          skipped_step_ids: [],
          waiting_for_approval_step_ids: [],
          step_results: {},
          updated_at: "2026-04-13T09:00:00.000Z",
          last_event_sequence: 0,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    renderHook(() => useExecutionMonitor("execution-5"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-5");
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-5",
        type: "unknown.event",
        payload: {
          sequence: 99,
        },
        timestamp: "2026-04-13T09:00:00.000Z",
      });
    });

    expect(useExecutionMonitorStore.getState().lastEventSequence).toBe(0);
  });

  it("uses total_tokens fallback payloads and records zero-percent step costs when no total cost exists yet", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/state", ({ params }) =>
        HttpResponse.json({
          execution_id: String(params.executionId),
          status: "running",
          completed_step_ids: [],
          active_step_ids: [],
          pending_step_ids: [],
          failed_step_ids: [],
          skipped_step_ids: [],
          waiting_for_approval_step_ids: [],
          step_results: {},
          updated_at: "2026-04-13T09:00:00.000Z",
          last_event_sequence: 0,
        }),
      ),
      http.get("*/api/v1/executions/:executionId/steps/:stepId", ({ params }) =>
        HttpResponse.json({
          execution_id: String(params.executionId),
          step_id: String(params.stepId),
          status: "completed",
          inputs: {},
          outputs: null,
          started_at: "2026-04-13T09:00:00.000Z",
          completed_at: "2026-04-13T09:01:00.000Z",
          duration_ms: 1000,
          context_quality_score: null,
          error: null,
          token_usage: {
            input_tokens: 7,
            output_tokens: 4,
            total_tokens: 11,
            estimated_cost_usd: 0.0025,
          },
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    renderHook(() => useExecutionMonitor("execution-4"), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionId).toBe("execution-4");
    });

    act(() => {
      wsMocks.channelHandler?.({
        channel: "execution:execution-4",
        type: "budget.threshold",
        payload: {
          total_tokens: 11,
        },
        timestamp: "2026-04-13T09:00:00.000Z",
      });
      wsMocks.channelHandler?.({
        channel: "execution:execution-4",
        type: "budget.threshold",
        payload: {},
        timestamp: "2026-04-13T09:00:30.000Z",
      });
      useExecutionMonitorStore.setState({
        totalTokens: 0,
        totalCostUsd: 0,
      });
      wsMocks.channelHandler?.({
        channel: "execution:execution-4",
        type: "step.state_changed",
        payload: {
          step_id: "review_case",
          new_status: "completed",
          sequence: 5,
        },
        timestamp: "2026-04-13T09:01:00.000Z",
      });
    });

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().costBreakdown).toEqual([
        expect.objectContaining({
          stepId: "review_case",
          totalTokens: 11,
          costUsd: 0.0025,
          percentageOfTotal: 0,
        }),
      ]);
    });
  });
});
