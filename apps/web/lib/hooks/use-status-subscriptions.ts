"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

export type StatusSubscriptionHealth = "pending" | "healthy" | "unhealthy" | "unsubscribed";
export type StatusSubscriptionChannel = "email" | "webhook" | "slack";

export interface StatusSubscription {
  id: string;
  channel: StatusSubscriptionChannel;
  target: string;
  scope_components: string[];
  health: StatusSubscriptionHealth;
  confirmed_at: string | null;
  created_at: string;
}

export interface StatusSubscriptionListResponse {
  items: StatusSubscription[];
}

export interface StatusSubscriptionInput {
  channel: StatusSubscriptionChannel;
  target: string;
  scope_components: string[];
}

const statusSubscriptionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const statusSubscriptionKeys = {
  all: ["platform-status", "subscriptions"] as const,
};

export function useStatusSubscriptions() {
  return useAppQuery<StatusSubscriptionListResponse>(
    statusSubscriptionKeys.all,
    () =>
      statusSubscriptionsApi.get<StatusSubscriptionListResponse>(
        "/api/v1/me/status-subscriptions",
      ),
  );
}

export function useCreateStatusSubscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StatusSubscriptionInput) =>
      statusSubscriptionsApi.post<StatusSubscription>(
        "/api/v1/me/status-subscriptions",
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: statusSubscriptionKeys.all });
    },
  });
}

export function useUpdateStatusSubscription(subscriptionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Pick<StatusSubscriptionInput, "target" | "scope_components">>) =>
      statusSubscriptionsApi.patch<StatusSubscription>(
        `/api/v1/me/status-subscriptions/${encodeURIComponent(subscriptionId)}`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: statusSubscriptionKeys.all });
    },
  });
}

export function useDeleteStatusSubscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (subscriptionId: string) =>
      statusSubscriptionsApi.delete<{ status: string; message: string }>(
        `/api/v1/me/status-subscriptions/${encodeURIComponent(subscriptionId)}`,
      ),
    onMutate: async (subscriptionId) => {
      await queryClient.cancelQueries({ queryKey: statusSubscriptionKeys.all });
      const previous =
        queryClient.getQueryData<StatusSubscriptionListResponse>(statusSubscriptionKeys.all);
      queryClient.setQueryData<StatusSubscriptionListResponse>(
        statusSubscriptionKeys.all,
        (current) => ({
          items: (current?.items ?? []).filter((item) => item.id !== subscriptionId),
        }),
      );
      return { previous };
    },
    onError: (_error, _subscriptionId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(statusSubscriptionKeys.all, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: statusSubscriptionKeys.all });
    },
  });
}
