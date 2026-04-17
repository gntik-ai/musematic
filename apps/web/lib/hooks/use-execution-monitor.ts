"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { wsClient } from "@/lib/ws";
import {
  normalizeExecutionEvent,
  normalizeExecutionState,
  normalizeStepDetail,
  type ExecutionEvent,
  type ExecutionEventResponse,
  type ExecutionStateResponse,
  type StepDetailResponse,
} from "@/types/execution";
import type { WsEvent } from "@/types/websocket";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

type ExecutionWsPayload =
  | Record<string, unknown>
  | {
      event?: ExecutionEventResponse;
      [key: string]: unknown;
    };

function createSyntheticExecutionEvent(
  executionId: string,
  eventType: ExecutionEvent["eventType"],
  payload: Record<string, unknown>,
  lastSequence: number,
): ExecutionEvent {
  const sequence = Number(payload.sequence ?? payload.event_sequence ?? lastSequence + 1);

  return {
    id: String(payload.id ?? `${executionId}-${eventType}-${sequence}`),
    executionId,
    sequence,
    eventType,
    stepId:
      payload.step_id === null || payload.stepId === null
        ? null
        : String(payload.step_id ?? payload.stepId ?? ""),
    agentFqn:
      payload.agent_fqn === null || payload.agentFqn === null
        ? null
        : String(payload.agent_fqn ?? payload.agentFqn ?? ""),
    payload,
    createdAt: String(
      payload.occurred_at ?? payload.created_at ?? payload.createdAt ?? new Date().toISOString(),
    ),
  };
}

function normalizeWsEventToExecutionEvent(
  executionId: string,
  event: WsEvent<ExecutionWsPayload>,
  lastSequence: number,
): ExecutionEvent | null {
  if (event.type === "event.appended") {
    const appendedEvent = (event.payload as { event?: ExecutionEventResponse }).event;
    return appendedEvent ? normalizeExecutionEvent(appendedEvent) : null;
  }

  if (
    event.type === "step.state_changed" ||
    event.type === "execution.status_changed" ||
    event.type === "budget.threshold" ||
    event.type === "correction.iteration" ||
    event.type === "approval.requested" ||
    event.type === "hot_change.applied"
  ) {
    return createSyntheticExecutionEvent(
      executionId,
      event.type as ExecutionEvent["eventType"],
      (event.payload ?? {}) as Record<string, unknown>,
      lastSequence,
    );
  }

  return null;
}

async function fetchExecutionState(executionId: string) {
  return normalizeExecutionState(
    await executionsApi.get<ExecutionStateResponse>(
      `/api/v1/executions/${encodeURIComponent(executionId)}/state`,
    ),
  );
}

async function fetchStepDetail(executionId: string, stepId: string) {
  return normalizeStepDetail(
    await executionsApi.get<StepDetailResponse>(
      `/api/v1/executions/${encodeURIComponent(executionId)}/steps/${encodeURIComponent(stepId)}`,
    ),
  );
}

export function useExecutionMonitor(executionId: string | null | undefined) {
  const queryClient = useQueryClient();
  const setExecutionState = useExecutionMonitorStore((state) => state.setExecutionState);
  const applyEvent = useExecutionMonitorStore((state) => state.applyEvent);
  const setWsStatus = useExecutionMonitorStore((state) => state.setWsStatus);
  const accumulateCost = useExecutionMonitorStore((state) => state.accumulateCost);
  const upsertStepCost = useExecutionMonitorStore((state) => state.upsertStepCost);

  useEffect(() => {
    if (!executionId) {
      return undefined;
    }

    let isMounted = true;
    const channel = `execution:${executionId}`;

    const reconcileExecutionState = async () => {
      const state = await fetchExecutionState(executionId);
      if (isMounted) {
        setExecutionState(state);
      }
      return state;
    };

    void reconcileExecutionState();

    const unsubscribeChannel = wsClient.subscribe<ExecutionWsPayload>(channel, (wsEvent) => {
      const lastSequence = useExecutionMonitorStore.getState().lastEventSequence;
      const executionEvent = normalizeWsEventToExecutionEvent(
        executionId,
        wsEvent as WsEvent<ExecutionWsPayload>,
        lastSequence,
      );

      if (executionEvent) {
        applyEvent(executionEvent);
      }

      if (wsEvent.type === "event.appended") {
        void queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "executions" &&
            query.queryKey[1] === "journal" &&
            query.queryKey[2] === executionId,
        });
      }

      if (wsEvent.type === "budget.threshold") {
        const payload = (wsEvent.payload ?? {}) as Record<string, unknown>;
        const currentValue = Number(
          payload.current_value ??
            payload.currentValue ??
            payload.tokens ??
            payload.total_tokens ??
            0,
        );
        const costUsd = Number(
          payload.cost_usd ??
            payload.costUsd ??
            payload.estimated_cost_usd ??
            0,
        );

        if (currentValue > 0 || costUsd > 0) {
          accumulateCost(currentValue, costUsd);
        }
      }

      if (
        (wsEvent.type === "step.state_changed" &&
          (((wsEvent.payload as Record<string, unknown>)?.new_status ??
            (wsEvent.payload as Record<string, unknown>)?.newStatus) ===
            "completed")) ||
        wsEvent.type === "event.appended"
      ) {
        const payload = (wsEvent.payload ?? {}) as Record<string, unknown>;
        const stepId =
          (payload.step_id as string | undefined) ??
          (payload.stepId as string | undefined) ??
          (((payload.event as Record<string, unknown> | undefined)?.step_id ??
            (payload.event as Record<string, unknown> | undefined)?.stepId) as
            | string
            | undefined);

        if (stepId) {
          void fetchStepDetail(executionId, stepId)
            .then((detail) => {
              if (!detail.tokenUsage) {
                return;
              }

              const totalCostUsd = useExecutionMonitorStore.getState().totalCostUsd;
              upsertStepCost({
                stepId,
                stepName: stepId,
                inputTokens: detail.tokenUsage.inputTokens,
                outputTokens: detail.tokenUsage.outputTokens,
                totalTokens: detail.tokenUsage.totalTokens,
                costUsd: detail.tokenUsage.estimatedCostUsd,
                percentageOfTotal:
                  totalCostUsd > 0
                    ? (detail.tokenUsage.estimatedCostUsd / totalCostUsd) * 100
                    : 0,
              });
            })
            .catch(() => {
              // Best-effort enrichment; stale step cost data should not break the monitor.
            });
        }
      }
    });

    const unsubscribeState = wsClient.onStateChange((status) => {
      setWsStatus(status);

      if (status === "connected") {
        void reconcileExecutionState().then(() => {
          void queryClient.invalidateQueries({
            predicate: (query) =>
              Array.isArray(query.queryKey) &&
              query.queryKey[0] === "executions" &&
              query.queryKey[2] === executionId,
          });
        });
      }

      if (status === "reconnecting" || status === "disconnected") {
        void queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "executions" &&
            query.queryKey[2] === executionId,
        });
      }
    });

    return () => {
      isMounted = false;
      unsubscribeChannel();
      unsubscribeState();
    };
  }, [
    accumulateCost,
    applyEvent,
    executionId,
    queryClient,
    setExecutionState,
    setWsStatus,
    upsertStepCost,
  ]);

  return {
    wsConnectionStatus: useExecutionMonitorStore((state) => state.wsConnectionStatus),
  };
}
