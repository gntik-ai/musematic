"use client";

import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import { operatorDashboardApi, operatorDashboardQueryKeys } from "@/lib/hooks/operator-dashboard-shared";
import { executionExperienceQueryKeys } from "@/lib/hooks/use-execution-trajectory";
import type { Checkpoint } from "@/types/trajectory";

interface RawCheckpointSummary {
  id: string;
  execution_id: string;
  checkpoint_number: number;
  created_at: string;
  current_step_id?: string | null;
  superseded: boolean;
  policy_snapshot?: Record<string, unknown>;
}

interface RawCheckpointListResponse {
  items: RawCheckpointSummary[];
  total: number;
  page: number;
  page_size: number;
}

function describeCheckpointReason(policySnapshot: Record<string, unknown> | undefined): string {
  const type = typeof policySnapshot?.type === "string" ? policySnapshot.type : null;
  if (type === "pre_tool") {
    return "Captured before tool execution.";
  }
  if (type === "every_step") {
    return "Captured after every step.";
  }
  if (type === "named_steps") {
    return "Captured by named-step checkpoint policy.";
  }
  if (type === "disabled") {
    return "Checkpoint retained after policy changed.";
  }
  return "Captured automatically for rollback support.";
}

async function fetchExecutionCheckpoints(
  executionId: string,
): Promise<RawCheckpointListResponse> {
  return operatorDashboardApi.get<RawCheckpointListResponse>(
    `/api/v1/executions/${encodeURIComponent(executionId)}/checkpoints?page=1&page_size=100`,
  );
}

export function useExecutionCheckpoints(executionId: string | null | undefined) {
  const query = useAppQuery(
    executionExperienceQueryKeys.checkpoints(executionId),
    async () => fetchExecutionCheckpoints(executionId ?? ""),
    {
      enabled: Boolean(executionId),
      staleTime: Number.POSITIVE_INFINITY,
    },
  );

  const data = useMemo(
    () =>
      (query.data?.items ?? []).map<Checkpoint>((checkpoint) => ({
        id: checkpoint.id,
        executionId: checkpoint.execution_id,
        stepIndex: checkpoint.checkpoint_number,
        createdAt: checkpoint.created_at,
        reason: describeCheckpointReason(checkpoint.policy_snapshot),
        isRollbackCandidate: !checkpoint.superseded,
      })),
    [query.data],
  );

  return {
    ...query,
    data,
    total: query.data?.total ?? 0,
  };
}

export function useCheckpointRollback(executionId: string | null | undefined) {
  const queryClient = useQueryClient();
  const mutation = useAppMutation(
    async ({
      checkpointNumber,
      reason,
    }: {
      checkpointNumber: number;
      reason?: string | undefined;
    }) => {
      return operatorDashboardApi.post(
        `/api/v1/executions/${encodeURIComponent(
          executionId ?? "",
        )}/rollback/${checkpointNumber}`,
        reason ? { reason } : undefined,
      );
    },
    {
      invalidateKeys: [
        executionExperienceQueryKeys.checkpoints(executionId),
        executionExperienceQueryKeys.trajectory(executionId),
        operatorDashboardQueryKeys.executionDetail(executionId),
      ],
      onSuccess: async () => {
        if (!executionId) {
          return;
        }
        await queryClient.invalidateQueries({
          queryKey: executionExperienceQueryKeys.debate(executionId),
        });
        await queryClient.invalidateQueries({
          queryKey: executionExperienceQueryKeys.reactCycles(executionId),
        });
      },
    },
  );

  return mutation;
}
