"use client";

import { useEffect } from "react";
import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { wsClient } from "@/lib/ws";
import { useConversationStore } from "@/lib/stores/conversation-store";
import {
  queryKeys,
  type GoalEventPayload,
  type GoalMessage,
  type PaginatedMessageResponse,
  type WorkspaceGoal,
} from "@/types/conversations";

export function useGoalWs(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  const selectedGoalId = useConversationStore((state) => state.selectedGoalId);
  const setSelectedGoal = useConversationStore((state) => state.setSelectedGoal);

  useEffect(() => {
    if (!workspaceId) {
      return undefined;
    }

    return wsClient.subscribe(`workspace:${workspaceId}`, (event) => {
      const payload = event.payload as GoalEventPayload;

      switch (payload.event_type) {
        case "goal.message_created":
          queryClient.setQueryData(
            queryKeys.goalMessages(payload.message.goal_id),
            (
              current:
                | InfiniteData<PaginatedMessageResponse<GoalMessage>, string | null>
                | undefined,
            ) => {
              if (!current) {
                return {
                  pages: [{ items: [payload.message], next_cursor: null }],
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
                items: [...lastPage.items, payload.message],
              };

              return { ...current, pages };
            },
          );
          return;
        case "goal.state_changed":
          queryClient.setQueryData(
            queryKeys.goals(workspaceId),
            (current: { items: WorkspaceGoal[] } | undefined) => {
              if (!current) {
                return current;
              }

              return {
                ...current,
                items: current.items.map((goal) =>
                  goal.id === payload.goal.id ? payload.goal : goal,
                ),
              };
            },
          );

          if (selectedGoalId === payload.goal.id) {
            setSelectedGoal(payload.goal.id);
          }
          return;
        default:
          return;
      }
    });
  }, [queryClient, selectedGoalId, setSelectedGoal, workspaceId]);
}
