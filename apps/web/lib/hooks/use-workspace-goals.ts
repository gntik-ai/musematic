"use client";

import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery, useAppQuery } from "@/lib/hooks/use-api";
import {
  isTerminalGoalStatus,
  queryKeys,
  type GoalMessage,
  type PaginatedMessageResponse,
  type WorkspaceGoal,
} from "@/types/conversations";
import { useAuthStore } from "@/store/auth-store";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useGoals(workspaceId: string | null | undefined) {
  return useAppQuery<{ items: WorkspaceGoal[] }>(
    queryKeys.goals(workspaceId ?? "no-workspace"),
    () => api.get<{ items: WorkspaceGoal[] }>(`/api/v1/workspaces/${workspaceId}/goals`),
    {
      enabled: Boolean(workspaceId),
    },
  );
}

export function useGoalMessages(
  workspaceId: string | null | undefined,
  goalId: string | null | undefined,
) {
  const query = useAppInfiniteQuery<
    PaginatedMessageResponse<GoalMessage>,
    string | null
  >(
    queryKeys.goalMessages(goalId ?? "no-goal"),
    (cursor) => {
      const params = new URLSearchParams();
      params.set("limit", "50");
      if (cursor) {
        params.set("cursor", cursor);
      }

      return api.get<PaginatedMessageResponse<GoalMessage>>(
        `/api/v1/workspaces/${workspaceId}/goals/${goalId}/messages?${params.toString()}`,
      );
    },
    {
      enabled: Boolean(workspaceId) && Boolean(goalId),
      getNextPageParam: (page) => page.next_cursor,
    },
  );

  const messages = query.data?.pages.flatMap((page) => page.items) ?? [];

  return {
    ...query,
    messages,
  };
}

interface PostGoalMessageVariables {
  workspaceId: string;
  goalId: string;
  content: string;
}

export function usePostGoalMessage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);

  return {
    mutateAsync: async ({
      content,
      goalId,
      workspaceId,
    }: PostGoalMessageVariables) => {
      const queryKey = queryKeys.goalMessages(goalId);
      const previous = queryClient.getQueryData<
        InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>
      >(queryKey);
      const optimisticMessage: GoalMessage = {
        id: `optimistic-goal-${Date.now()}`,
        goal_id: goalId,
        sender_type: "user",
        sender_id: user?.id ?? "current-user",
        sender_display_name: user?.displayName ?? "You",
        agent_fqn: null,
        content,
        originating_interaction_id: null,
        created_at: new Date().toISOString(),
      };

      queryClient.setQueryData(queryKey, (
        current:
          | InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>
          | undefined,
      ) => {
        if (!current) {
          return {
            pages: [{ items: [optimisticMessage], next_cursor: null }],
            pageParams: [null],
          };
        }

        const pages = [...current.pages];
        const lastPage = pages[pages.length - 1];
        if (!lastPage) {
          return current;
        }

        pages[pages.length - 1] = {
          ...lastPage,
          items: [...lastPage.items, optimisticMessage],
        };

        return { ...current, pages };
      });

      try {
        const response = await api.post<GoalMessage>(
          `/api/v1/workspaces/${workspaceId}/goals/${goalId}/messages`,
          { content },
        );

        queryClient.setQueryData(queryKey, (
          current:
            | InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>
            | undefined,
        ) => {
          if (!current) {
            return {
              pages: [{ items: [response], next_cursor: null }],
              pageParams: [null],
            };
          }

          return {
            ...current,
            pages: current.pages.map((page) => ({
              ...page,
              items: page.items.map((item) =>
                item.id === optimisticMessage.id ? response : item,
              ),
            })),
          };
        });

        return response;
      } catch (error) {
        queryClient.setQueryData(queryKey, previous);
        throw error;
      }
    },
  };
}

export function getSelectedGoal(
  goals: WorkspaceGoal[],
  goalId: string | null | undefined,
) {
  return goals.find((goal) => goal.id === goalId) ?? goals[0] ?? null;
}

export function canPostToGoal(goal: WorkspaceGoal | null | undefined) {
  return goal ? !isTerminalGoalStatus(goal.status) : false;
}
