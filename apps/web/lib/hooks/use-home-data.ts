"use client";

import { useEffect, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type {
  PendingActionsResponse,
  RecentActivityResponse,
  WorkspaceSummaryResponse,
} from "@/lib/types/home";
import { wsClient } from "@/lib/ws";

const homeApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const homeQueryKeys = {
  all: (workspaceId: string) => ["home", workspaceId] as const,
  summary: (workspaceId: string) => ["home", workspaceId, "summary"] as const,
  activity: (workspaceId: string) => ["home", workspaceId, "activity"] as const,
  pendingActions: (workspaceId: string) =>
    ["home", workspaceId, "pending-actions"] as const,
};

interface HomeQueryOptions {
  isConnected?: boolean | undefined;
}

interface ApproveMutationVariables {
  endpoint: string;
  method: "POST" | "DELETE";
}

interface PendingActionsMutationContext {
  previous: PendingActionsResponse | undefined;
}

function getWorkspaceScope(workspaceId: string | null | undefined): string {
  return workspaceId ?? "no-workspace";
}

function getRefetchInterval(isConnected: boolean | undefined): false | number {
  return isConnected === false ? 30_000 : false;
}

function getWorkspaceIdFromPayload(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  if ("workspace_id" in payload && typeof payload.workspace_id === "string") {
    return payload.workspace_id;
  }

  if ("workspaceId" in payload && typeof payload.workspaceId === "string") {
    return payload.workspaceId;
  }

  return null;
}

function shouldInvalidateEvent(
  workspaceId: string,
  event: { payload: unknown },
): boolean {
  const payloadWorkspaceId = getWorkspaceIdFromPayload(event.payload);
  return payloadWorkspaceId === null || payloadWorkspaceId === workspaceId;
}

async function mutatePendingAction({
  endpoint,
  method,
}: ApproveMutationVariables): Promise<unknown> {
  if (method === "DELETE") {
    return homeApi.delete(endpoint);
  }

  return homeApi.post(endpoint);
}

export function useWorkspaceSummary(
  workspaceId: string | null | undefined,
  options: HomeQueryOptions = {},
) {
  const workspaceScope = getWorkspaceScope(workspaceId);

  return useQuery({
    queryKey: homeQueryKeys.summary(workspaceScope),
    queryFn: () =>
      homeApi.get<WorkspaceSummaryResponse>(
        `/api/v1/workspaces/${workspaceScope}/analytics/summary`,
      ),
    staleTime: 30_000,
    refetchInterval: getRefetchInterval(options.isConnected),
    enabled: Boolean(workspaceId),
  });
}

export function useRecentActivity(
  workspaceId: string | null | undefined,
  options: HomeQueryOptions = {},
) {
  const workspaceScope = getWorkspaceScope(workspaceId);

  return useQuery({
    queryKey: homeQueryKeys.activity(workspaceScope),
    queryFn: () =>
      homeApi.get<RecentActivityResponse>(
        `/api/v1/workspaces/${workspaceScope}/dashboard/recent-activity`,
      ),
    staleTime: 30_000,
    refetchInterval: getRefetchInterval(options.isConnected),
    enabled: Boolean(workspaceId),
  });
}

export function usePendingActions(
  workspaceId: string | null | undefined,
  options: HomeQueryOptions = {},
) {
  const workspaceScope = getWorkspaceScope(workspaceId);

  return useQuery({
    queryKey: homeQueryKeys.pendingActions(workspaceScope),
    queryFn: () =>
      homeApi.get<PendingActionsResponse>(
        `/api/v1/workspaces/${workspaceScope}/dashboard/pending-actions`,
      ),
    staleTime: 30_000,
    refetchInterval: getRefetchInterval(options.isConnected),
    enabled: Boolean(workspaceId),
  });
}

export function useWebSocketStatus(): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(
    wsClient.connectionState === "connected",
  );

  useEffect(() => wsClient.onConnectionChange(setIsConnected), []);

  return { isConnected };
}

export function useApproveMutation(
  workspaceId: string | null | undefined,
) {
  const queryClient = useQueryClient();
  const workspaceScope = getWorkspaceScope(workspaceId);

  return useMutation<
    unknown,
    Error,
    ApproveMutationVariables,
    PendingActionsMutationContext
  >({
    mutationFn: mutatePendingAction,
    onMutate: async ({ endpoint }) => {
      await queryClient.cancelQueries({
        queryKey: homeQueryKeys.pendingActions(workspaceScope),
      });

      const previous = queryClient.getQueryData<PendingActionsResponse>(
        homeQueryKeys.pendingActions(workspaceScope),
      );

      if (previous) {
        const items = previous.items.filter(
          (item) =>
            !item.actions.some((action) => action.endpoint === endpoint),
        );
        queryClient.setQueryData<PendingActionsResponse>(
          homeQueryKeys.pendingActions(workspaceScope),
          {
            ...previous,
            items,
            total: items.length,
          },
        );
      }

      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          homeQueryKeys.pendingActions(workspaceScope),
          context.previous,
        );
      }
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: homeQueryKeys.pendingActions(workspaceScope),
        }),
        queryClient.invalidateQueries({
          queryKey: homeQueryKeys.summary(workspaceScope),
        }),
      ]);
    },
  });
}

export function useDashboardWebSocket(
  workspaceId: string | null | undefined,
): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    const invalidate = (queryKey: QueryKey) =>
      queryClient.invalidateQueries({ queryKey });

    const executionUnsubscribe = wsClient.subscribe("execution", (event) => {
      if (!shouldInvalidateEvent(workspaceId, event)) {
        return;
      }

      void Promise.all([
        invalidate(homeQueryKeys.activity(workspaceId)),
        invalidate(homeQueryKeys.summary(workspaceId)),
      ]);

      if (
        event.type === "execution.failed" ||
        event.type === "execution.requires_approval"
      ) {
        void invalidate(homeQueryKeys.pendingActions(workspaceId));
      }
    });

    const interactionUnsubscribe = wsClient.subscribe("interaction", (event) => {
      if (!shouldInvalidateEvent(workspaceId, event)) {
        return;
      }

      void invalidate(homeQueryKeys.activity(workspaceId));

      if (event.type === "interaction.attention.requested") {
        void Promise.all([
          invalidate(homeQueryKeys.pendingActions(workspaceId)),
          invalidate(homeQueryKeys.summary(workspaceId)),
        ]);
      }
    });

    const workspaceUnsubscribe = wsClient.subscribe("workspace", (event) => {
      if (!shouldInvalidateEvent(workspaceId, event)) {
        return;
      }

      if (
        event.type === "workspace.approval.created" ||
        event.type === "workspace.approval.resolved"
      ) {
        void Promise.all([
          invalidate(homeQueryKeys.pendingActions(workspaceId)),
          invalidate(homeQueryKeys.summary(workspaceId)),
        ]);
      }
    });

    return () => {
      executionUnsubscribe();
      interactionUnsubscribe();
      workspaceUnsubscribe();
    };
  }, [queryClient, workspaceId]);
}
