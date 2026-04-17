import { beforeEach, describe, expect, it } from "vitest";
import {
  useExecutionMonitorStore,
} from "@/lib/stores/execution-monitor-store";
import type { ExecutionEvent, ExecutionState } from "@/types/execution";

function buildExecutionState(): ExecutionState {
  return {
    executionId: "execution-1",
    status: "running",
    completedStepIds: ["collect_context"],
    activeStepIds: ["evaluate_risk"],
    pendingStepIds: ["approval_gate"],
    failedStepIds: [],
    skippedStepIds: [],
    waitingForApprovalStepIds: [],
    stepResults: {
      collect_context: {
        stepId: "collect_context",
        status: "completed",
        startedAt: "2026-04-13T09:00:00.000Z",
        completedAt: "2026-04-13T09:01:00.000Z",
        durationMs: 60_000,
        error: null,
        retryCount: 0,
      },
      evaluate_risk: {
        stepId: "evaluate_risk",
        status: "running",
        startedAt: "2026-04-13T09:01:00.000Z",
        completedAt: null,
        durationMs: null,
        error: null,
        retryCount: 0,
      },
      approval_gate: {
        stepId: "approval_gate",
        status: "pending",
        startedAt: null,
        completedAt: null,
        durationMs: null,
        error: null,
        retryCount: 0,
      },
    },
    lastEventSequence: 7,
    updatedAt: "2026-04-13T09:02:00.000Z",
  };
}

describe("execution-monitor-store", () => {
  beforeEach(() => {
    useExecutionMonitorStore.getState().reset();
  });

  it("hydrates the monitor state from an execution snapshot", () => {
    useExecutionMonitorStore.getState().setExecutionState(buildExecutionState());

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      executionId: "execution-1",
      executionStatus: "running",
      stepStatuses: {
        collect_context: "completed",
        evaluate_risk: "running",
        approval_gate: "pending",
      },
      lastEventSequence: 7,
    });
  });

  it("applies execution and step events without decreasing the sequence", () => {
    useExecutionMonitorStore.getState().setExecutionState(buildExecutionState());

    const stepEvent: ExecutionEvent = {
      id: "evt-8",
      executionId: "execution-1",
      sequence: 8,
      eventType: "STEP_WAITING_FOR_APPROVAL",
      stepId: "approval_gate",
      agentFqn: null,
      payload: {},
      createdAt: "2026-04-13T09:03:00.000Z",
    };
    const executionEvent: ExecutionEvent = {
      id: "evt-6",
      executionId: "execution-1",
      sequence: 6,
      eventType: "EXECUTION_PAUSED",
      stepId: null,
      agentFqn: null,
      payload: {},
      createdAt: "2026-04-13T09:03:10.000Z",
    };

    useExecutionMonitorStore.getState().applyEvent(stepEvent);
    useExecutionMonitorStore.getState().applyEvent(executionEvent);

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      executionStatus: "paused",
      stepStatuses: expect.objectContaining({
        approval_gate: "waiting_for_approval",
      }),
      lastEventSequence: 8,
    });
  });

  it("tracks detail selection, websocket status, cumulative cost, and reset", () => {
    useExecutionMonitorStore.getState().selectStep("evaluate_risk");
    useExecutionMonitorStore.getState().setDetailTab("reasoning");
    useExecutionMonitorStore.getState().setWsStatus("connected");
    useExecutionMonitorStore.getState().accumulateCost(321, 0.0123456);
    useExecutionMonitorStore.getState().accumulateCost(99, 0.0000049);

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      selectedStepId: "evaluate_risk",
      activeDetailTab: "reasoning",
      wsConnectionStatus: "connected",
      totalTokens: 420,
      totalCostUsd: 0.012351,
    });

    useExecutionMonitorStore.getState().reset();

    expect(useExecutionMonitorStore.getState()).toMatchObject({
      executionId: null,
      executionStatus: null,
      stepStatuses: {},
      lastEventSequence: 0,
      selectedStepId: null,
      activeDetailTab: "overview",
      totalTokens: 0,
      totalCostUsd: 0,
      wsConnectionStatus: "disconnected",
    });
  });
});
