"use client";

import { useAppMutation } from "@/lib/hooks/use-api";
import { billingApi, workspaceBillingKeys } from "@/lib/hooks/use-workspace-billing";

interface UpgradeInput {
  workspaceId: string;
  target_plan_slug: string;
  payment_method_token: string | null;
}

interface DowngradeInput {
  workspaceId: string;
  target_plan_slug: string;
}

interface UpgradeResponse {
  preview: {
    prorated_charge_eur: string;
    prorated_credit_eur: string;
    next_full_invoice_eur: string;
    effective_at: string;
  };
  subscription_after: {
    plan_slug: string;
    plan_version: number;
    current_period_end: string;
  };
}

interface SubscriptionLifecycleResponse {
  subscription_id: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end?: string;
}

export function useUpgradeSubscription(workspaceId: string) {
  return useAppMutation<UpgradeResponse, UpgradeInput>(
    ({ workspaceId: id, target_plan_slug, payment_method_token }) =>
      billingApi.post<UpgradeResponse>(
        `/api/v1/workspaces/${id}/billing/upgrade`,
        { target_plan_slug, payment_method_token },
        { skipRetry: true },
      ),
    { invalidateKeys: [workspaceBillingKeys(workspaceId).summary] },
  );
}

export function useDowngradeSubscription(workspaceId: string) {
  return useAppMutation<SubscriptionLifecycleResponse, DowngradeInput>(
    ({ workspaceId: id, target_plan_slug }) =>
      billingApi.post<SubscriptionLifecycleResponse>(
        `/api/v1/workspaces/${id}/billing/downgrade`,
        { target_plan_slug },
        { skipRetry: true },
      ),
    { invalidateKeys: [workspaceBillingKeys(workspaceId).summary] },
  );
}

export function useCancelDowngrade(workspaceId: string) {
  return useAppMutation<SubscriptionLifecycleResponse, string>(
    (id) =>
      billingApi.post<SubscriptionLifecycleResponse>(
        `/api/v1/workspaces/${id}/billing/cancel-downgrade`,
        {},
        { skipRetry: true },
      ),
    { invalidateKeys: [workspaceBillingKeys(workspaceId).summary] },
  );
}

export function useCancelSubscription(workspaceId: string) {
  return useAppMutation<SubscriptionLifecycleResponse, string>(
    (id) =>
      billingApi.post<SubscriptionLifecycleResponse>(
        `/api/v1/workspaces/${id}/billing/cancel`,
        {},
        { skipRetry: true },
      ),
    { invalidateKeys: [workspaceBillingKeys(workspaceId).summary] },
  );
}
