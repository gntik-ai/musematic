"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

const adminSubscriptionsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface AdminSubscription {
  id: string;
  tenant_id: string;
  tenant_slug: string | null;
  scope_type: "workspace" | "tenant";
  scope_id: string;
  plan_slug: string;
  plan_tier: "free" | "pro" | "enterprise";
  plan_version: number;
  status: string;
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
  trial_expires_at: string | null;
  created_at: string | null;
  stripe_customer_id?: string | null;
  stripe_subscription_id?: string | null;
}

export interface AdminUsageItem {
  metric: "executions" | "minutes";
  period_start: string;
  period_end: string;
  quantity: string;
  is_overage: boolean;
}

export interface MigrateSubscriptionInput {
  subscriptionId: string;
  plan_slug: string;
  plan_version: number;
  reason: string;
}

export function adminSubscriptionKeys() {
  return {
    list: ["admin", "subscriptions"] as const,
    detail: (id: string) => ["admin", "subscriptions", id] as const,
    usage: (id: string) => ["admin", "subscriptions", id, "usage"] as const,
  };
}

export function useAdminSubscriptions(filters?: { status?: string; plan_slug?: string }) {
  const query = new URLSearchParams();
  if (filters?.status) {
    query.set("status", filters.status);
  }
  if (filters?.plan_slug) {
    query.set("plan_slug", filters.plan_slug);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return useAppQuery(adminSubscriptionKeys().list, () =>
    adminSubscriptionsApi.get<{ items: AdminSubscription[] }>(
      `/api/v1/admin/subscriptions${suffix}`,
    ),
  );
}

export function useAdminSubscription(id: string) {
  return useAppQuery(
    adminSubscriptionKeys().detail(id),
    () => adminSubscriptionsApi.get<AdminSubscription>(`/api/v1/admin/subscriptions/${id}`),
    { enabled: id.length > 0 },
  );
}

export function useAdminSubscriptionUsage(id: string) {
  return useAppQuery(
    adminSubscriptionKeys().usage(id),
    () =>
      adminSubscriptionsApi.get<{ items: AdminUsageItem[] }>(
        `/api/v1/admin/subscriptions/${id}/usage`,
      ),
    { enabled: id.length > 0 },
  );
}

export function useSuspendSubscription() {
  return useAppMutation(
    ({ id, reason }: { id: string; reason: string }) =>
      adminSubscriptionsApi.post(
        `/api/v1/admin/subscriptions/${id}/suspend`,
        { reason },
        { skipRetry: true },
      ),
    { invalidateKeys: [adminSubscriptionKeys().list] },
  );
}

export function useReactivateSubscription() {
  return useAppMutation(
    (id: string) =>
      adminSubscriptionsApi.post(
        `/api/v1/admin/subscriptions/${id}/reactivate`,
        {},
        { skipRetry: true },
      ),
    { invalidateKeys: [adminSubscriptionKeys().list] },
  );
}

export function useMigrateSubscription() {
  return useAppMutation(
    ({ subscriptionId, plan_slug, plan_version, reason }: MigrateSubscriptionInput) =>
      adminSubscriptionsApi.post(
        `/api/v1/admin/subscriptions/${subscriptionId}/migrate-version`,
        { plan_slug, plan_version, reason },
        { skipRetry: true },
      ),
    { invalidateKeys: [adminSubscriptionKeys().list] },
  );
}
