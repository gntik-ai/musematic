"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useMutation } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { GoalState, WorkspaceGoal } from "@/types/goal";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface GoalResponse {
  id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

interface GoalListResponse {
  items: GoalResponse[];
  total: number;
}

function normalizeGoalState(state: string): GoalState {
  switch (state) {
    case "active":
      return "in_progress";
    case "paused":
    case "abandoned":
      return "cancelled";
    case "open":
    case "in_progress":
    case "completed":
    case "cancelled":
      return state;
    default:
      return "open";
  }
}

function normalizeGoal(goal: GoalResponse): WorkspaceGoal {
  const state = normalizeGoalState(goal.status);

  return {
    id: goal.id,
    workspaceId: goal.workspace_id,
    title: goal.title,
    description: goal.description ?? "",
    state,
    createdAt: goal.created_at,
    updatedAt: goal.updated_at,
    completedAt: state === "completed" ? goal.updated_at : null,
  };
}

export function useGoalLifecycle(workspaceId: string | null | undefined) {
  const query = useAppQuery<{ activeGoal: WorkspaceGoal | null; goals: WorkspaceGoal[] }>(
    ["goal", workspaceId ?? "none"],
    async () => {
      const response = await api.get<GoalListResponse>(
        `/api/v1/workspaces/${workspaceId}/goals?page=1&page_size=20`,
      );
      const goals = response.items.map(normalizeGoal);
      const activeGoal =
        goals.find((goal) => goal.state === "in_progress" || goal.state === "open") ??
        goals[0] ??
        null;
      return { activeGoal, goals };
    },
    { enabled: Boolean(workspaceId), staleTime: 30_000 },
  );

  return {
    ...query,
    activeGoal: query.data?.activeGoal ?? null,
    goals: query.data?.goals ?? [],
  };
}

export function useGoalLifecycleMutations(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ goalId, state }: { goalId: string; state: GoalState }) =>
      api.patch<GoalResponse>(`/api/v1/workspaces/${workspaceId}/goals/${goalId}`, {
        status: state,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["goal", workspaceId ?? "none"] }),
        queryClient.invalidateQueries({ queryKey: ["conversation-messages", workspaceId ?? "none"] }),
      ]);
    },
  });
}
