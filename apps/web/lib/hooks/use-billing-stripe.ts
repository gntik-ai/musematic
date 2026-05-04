"use client";

import * as billing from "@/lib/api/billing-stripe";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export const billingStripeKeys = {
  invoices: (workspaceId: string) =>
    ["billing-stripe", workspaceId, "invoices"] as const,
  invoice: (workspaceId: string, invoiceId: string) =>
    ["billing-stripe", workspaceId, "invoices", invoiceId] as const,
};

export function useStripeUpgrade(workspaceId: string) {
  return useAppMutation(
    (vars: billing.BillingStripeUpgradeRequest) =>
      billing.stripeUpgrade(workspaceId, vars),
    { invalidateKeys: [["workspace", workspaceId, "billing"]] },
  );
}

export function useStripeCancel(workspaceId: string) {
  return useAppMutation(
    (vars: billing.BillingStripeCancelRequest) =>
      billing.stripeCancel(workspaceId, vars),
    { invalidateKeys: [["workspace", workspaceId, "billing"]] },
  );
}

export function useStripeReactivate(workspaceId: string) {
  return useAppMutation(() => billing.stripeReactivate(workspaceId), {
    invalidateKeys: [["workspace", workspaceId, "billing"]],
  });
}

export function useStripePortalSession(workspaceId: string) {
  return useAppMutation(() => billing.stripePortalSession(workspaceId));
}

export function useStripeStoreCard(workspaceId: string) {
  return useAppMutation(
    (vars: billing.BillingStripeStoreCardRequest) =>
      billing.stripeStoreCard(workspaceId, vars),
    { invalidateKeys: [["workspace", workspaceId, "billing"]] },
  );
}

export function useStripeInvoices(workspaceId: string) {
  return useAppQuery(
    billingStripeKeys.invoices(workspaceId),
    () => billing.listInvoices(workspaceId),
    { enabled: workspaceId.length > 0 },
  );
}

export function useStripeInvoice(workspaceId: string, invoiceId: string | null) {
  return useAppQuery(
    billingStripeKeys.invoice(workspaceId, invoiceId ?? ""),
    () => billing.getInvoice(workspaceId, invoiceId as string),
    { enabled: workspaceId.length > 0 && Boolean(invoiceId) },
  );
}
