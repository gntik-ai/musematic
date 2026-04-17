"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import {
  type ExecutionMonitorStoreState,
  useExecutionMonitorStore,
} from "@/lib/stores/execution-monitor-store";
import type { StepStatus } from "@/types/execution";

const executionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

type MonitorSnapshot = Pick<
  ExecutionMonitorStoreState,
  "executionStatus" | "stepStatuses"
>;

function getSnapshot(): MonitorSnapshot {
  const state = useExecutionMonitorStore.getState();
  return {
    executionStatus: state.executionStatus,
    stepStatuses: state.stepStatuses,
  };
}

function restoreSnapshot(snapshot: MonitorSnapshot): void {
  useExecutionMonitorStore.setState(snapshot);
}

function useExecutionMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<void>,
  applyOptimisticUpdate: (variables: TVariables) => void,
  executionId: string,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onMutate: async (variables) => {
      const snapshot = getSnapshot();
      applyOptimisticUpdate(variables);
      return snapshot;
    },
    onError: (_error, _variables, snapshot) => {
      if (snapshot) {
        restoreSnapshot(snapshot);
      }
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.execution(executionId),
        }),
        queryClient.invalidateQueries({
          queryKey: workflowQueryKeys.executionState(executionId),
        }),
        queryClient.invalidateQueries({
          queryKey: ["executions", "journal", executionId],
        }),
      ]);
    },
  });
}

function setStepStatus(stepId: string, status: StepStatus): void {
  useExecutionMonitorStore.setState((state) => ({
    stepStatuses: {
      ...state.stepStatuses,
      [stepId]: status,
    },
  }));
}

export function usePauseExecution(executionId: string) {
  return useExecutionMutation(
    async () => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/pause`,
        {},
      );
    },
    () => {
      useExecutionMonitorStore.setState({ executionStatus: "paused" });
    },
    executionId,
  );
}

export function useResumeExecution(executionId: string) {
  return useExecutionMutation(
    async () => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/resume`,
        {},
      );
    },
    () => {
      useExecutionMonitorStore.setState({ executionStatus: "running" });
    },
    executionId,
  );
}

export function useCancelExecution(executionId: string) {
  return useExecutionMutation(
    async (payload: { reason?: string | undefined }) => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/cancel`,
        payload,
      );
    },
    () => {
      useExecutionMonitorStore.setState({ executionStatus: "canceled" });
    },
    executionId,
  );
}

export function useRetryStep(executionId: string) {
  return useExecutionMutation(
    async ({ stepId }: { stepId: string }) => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/steps/${encodeURIComponent(stepId)}/retry`,
        {},
      );
    },
    ({ stepId }) => {
      useExecutionMonitorStore.setState({ executionStatus: "running" });
      setStepStatus(stepId, "running");
    },
    executionId,
  );
}

export function useSkipStep(executionId: string) {
  return useExecutionMutation(
    async ({ stepId, reason }: { stepId: string; reason?: string | undefined }) => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/steps/${encodeURIComponent(stepId)}/skip`,
        { reason },
      );
    },
    ({ stepId }) => {
      setStepStatus(stepId, "skipped");
    },
    executionId,
  );
}

export function useInjectVariable(executionId: string) {
  return useExecutionMutation(
    async ({
      variableName,
      value,
      reason,
    }: {
      variableName: string;
      value: unknown;
      reason?: string | undefined;
    }) => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/hot-change`,
        {
          variable_name: variableName,
          value,
          reason,
        },
      );
    },
    () => {},
    executionId,
  );
}

export function useApprovalDecision(executionId: string) {
  return useExecutionMutation(
    async ({
      stepId,
      decision,
      comment,
    }: {
      stepId: string;
      decision: "approved" | "rejected";
      comment?: string | undefined;
    }) => {
      await executionsApi.post(
        `/api/v1/executions/${encodeURIComponent(executionId)}/approvals/${encodeURIComponent(stepId)}/decide`,
        { decision, comment },
      );
    },
    ({ stepId, decision }) => {
      setStepStatus(stepId, decision === "approved" ? "completed" : "failed");
      useExecutionMonitorStore.setState({ executionStatus: "running" });
    },
    executionId,
  );
}
