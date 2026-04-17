"use client";

import { create } from "zustand";
import type {
  ExecutionCostEntry,
  ExecutionEvent,
  ExecutionState,
  ExecutionStatus,
  StepStatus,
} from "@/types/execution";
import { deriveStepStatuses } from "@/types/execution";
import type { WsConnectionState } from "@/types/websocket";

export type ExecutionMonitorDetailTab =
  | "overview"
  | "reasoning"
  | "self-correction"
  | "task-plan";

export interface ExecutionMonitorStoreState {
  executionId: string | null;
  executionStatus: ExecutionStatus | null;
  stepStatuses: Record<string, StepStatus>;
  lastEventSequence: number;
  selectedStepId: string | null;
  activeDetailTab: ExecutionMonitorDetailTab;
  totalTokens: number;
  totalCostUsd: number;
  costBreakdown: ExecutionCostEntry[];
  wsConnectionStatus: WsConnectionState;
  setExecutionState: (state: ExecutionState) => void;
  applyEvent: (event: ExecutionEvent) => void;
  selectStep: (stepId: string | null) => void;
  setDetailTab: (tab: ExecutionMonitorDetailTab) => void;
  setWsStatus: (status: WsConnectionState) => void;
  accumulateCost: (tokens: number, costUsd: number) => void;
  setCostBreakdown: (entries: ExecutionCostEntry[]) => void;
  upsertStepCost: (entry: ExecutionCostEntry) => void;
  reset: () => void;
}

const initialState = {
  executionId: null,
  executionStatus: null,
  stepStatuses: {},
  lastEventSequence: 0,
  selectedStepId: null,
  activeDetailTab: "overview" as ExecutionMonitorDetailTab,
  totalTokens: 0,
  totalCostUsd: 0,
  costBreakdown: [],
  wsConnectionStatus: "disconnected" as WsConnectionState,
} satisfies Omit<
  ExecutionMonitorStoreState,
  | "setExecutionState"
  | "applyEvent"
  | "selectStep"
  | "setDetailTab"
  | "setWsStatus"
  | "accumulateCost"
  | "setCostBreakdown"
  | "upsertStepCost"
  | "reset"
>;

function updateStepStatusForEvent(
  current: Record<string, StepStatus>,
  event: ExecutionEvent,
): Record<string, StepStatus> {
  const stepId = event.stepId ?? (event.payload.step_id as string | undefined);
  const next = { ...current };

  if (!stepId) {
    return next;
  }

  if (event.eventType === "step.state_changed") {
    const newStatus = event.payload.new_status;
    if (typeof newStatus === "string") {
      next[stepId] = newStatus as StepStatus;
    }
    return next;
  }

  switch (event.eventType) {
    case "STEP_RUNTIME_STARTED":
    case "STEP_DISPATCHED":
    case "STEP_RETRIED":
      next[stepId] = "running";
      break;
    case "STEP_COMPLETED":
    case "STEP_APPROVED":
      next[stepId] = "completed";
      break;
    case "STEP_FAILED":
    case "STEP_REJECTED":
      next[stepId] = "failed";
      break;
    case "STEP_SKIPPED":
      next[stepId] = "skipped";
      break;
    case "STEP_WAITING_FOR_APPROVAL":
    case "approval.requested":
      next[stepId] = "waiting_for_approval";
      break;
    default:
      break;
  }

  return next;
}

function updateExecutionStatusForEvent(
  currentStatus: ExecutionStatus | null,
  event: ExecutionEvent,
): ExecutionStatus | null {
  if (event.eventType === "execution.status_changed") {
    const newStatus = event.payload.new_status;
    return typeof newStatus === "string"
      ? (newStatus as ExecutionStatus)
      : currentStatus;
  }

  switch (event.eventType) {
    case "EXECUTION_CREATED":
    case "EXECUTION_STARTED":
      return "running";
    case "EXECUTION_PAUSED":
      return "paused";
    case "EXECUTION_RESUMED":
      return "running";
    case "EXECUTION_COMPLETED":
      return "completed";
    case "EXECUTION_FAILED":
      return "failed";
    case "EXECUTION_CANCELED":
      return "canceled";
    default:
      return currentStatus;
  }
}

export const useExecutionMonitorStore = create<ExecutionMonitorStoreState>()(
  (set) => ({
    ...initialState,
    setExecutionState: (state) =>
      set(() => ({
        executionId: state.executionId,
        executionStatus: state.status,
        stepStatuses: deriveStepStatuses(state),
        lastEventSequence: state.lastEventSequence,
      })),
    applyEvent: (event) =>
      set((state) => ({
        executionStatus: updateExecutionStatusForEvent(state.executionStatus, event),
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
        stepStatuses: updateStepStatusForEvent(state.stepStatuses, event),
      })),
    selectStep: (selectedStepId) => set(() => ({ selectedStepId })),
    setDetailTab: (activeDetailTab) => set(() => ({ activeDetailTab })),
    setWsStatus: (wsConnectionStatus) => set(() => ({ wsConnectionStatus })),
    accumulateCost: (tokens, costUsd) =>
      set((state) => ({
        totalTokens: state.totalTokens + tokens,
        totalCostUsd: Number((state.totalCostUsd + costUsd).toFixed(6)),
      })),
    setCostBreakdown: (costBreakdown) => set(() => ({ costBreakdown })),
    upsertStepCost: (entry) =>
      set((state) => {
        const nextBreakdown = state.costBreakdown
          .filter((current) => current.stepId !== entry.stepId)
          .concat(entry)
          .sort((left, right) => right.costUsd - left.costUsd);

        return {
          costBreakdown: nextBreakdown.map((current) => ({
            ...current,
            percentageOfTotal:
              state.totalCostUsd > 0
                ? (current.costUsd / state.totalCostUsd) * 100
                : current.percentageOfTotal,
          })),
        };
      }),
    reset: () => set(() => ({ ...initialState })),
  }),
);
