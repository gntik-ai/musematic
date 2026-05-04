"use client";

import { createApiClient } from "@/lib/api";

export interface BillingStripeUpgradeRequest {
  target_plan_slug: string;
  payment_method_token: string;
}

export interface BillingStripeUpgradeResponse {
  subscription_id: string;
  stripe_subscription_id: string;
  status: string;
}

export interface BillingStripeCancelRequest {
  reason: string;
  reason_text?: string;
}

export interface BillingStripeCancelResponse {
  subscription_id: string;
  status: string;
  ends_at: string;
}

export interface BillingStripePortalResponse {
  portal_url: string;
}

export interface BillingStripeStoreCardRequest {
  payment_method_token: string;
}

export interface InvoiceSummary {
  id: string;
  stripe_invoice_id: string;
  invoice_number: string | null;
  amount_total: string;
  amount_subtotal: string;
  amount_tax: string;
  currency: string;
  status: string;
  period_start: string | null;
  period_end: string | null;
  issued_at: string | null;
  paid_at: string | null;
  pdf_url: string | null;
}

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

const base = (workspaceId: string) =>
  `/api/v1/workspaces/${workspaceId}/billing`;

export async function stripeUpgrade(
  workspaceId: string,
  body: BillingStripeUpgradeRequest,
): Promise<BillingStripeUpgradeResponse> {
  return api.post<BillingStripeUpgradeResponse>(
    `${base(workspaceId)}/stripe-upgrade`,
    body,
  );
}

export async function stripeCancel(
  workspaceId: string,
  body: BillingStripeCancelRequest,
): Promise<BillingStripeCancelResponse> {
  return api.post<BillingStripeCancelResponse>(
    `${base(workspaceId)}/cancel-with-reason`,
    body,
  );
}

export async function stripeReactivate(
  workspaceId: string,
): Promise<{ subscription_id: string; status: string }> {
  return api.post<{ subscription_id: string; status: string }>(
    `${base(workspaceId)}/reactivate`,
    {},
  );
}

export async function stripePortalSession(
  workspaceId: string,
): Promise<BillingStripePortalResponse> {
  return api.post<BillingStripePortalResponse>(
    `${base(workspaceId)}/portal-session`,
    {},
  );
}

export async function stripeStoreCard(
  workspaceId: string,
  body: BillingStripeStoreCardRequest,
): Promise<{ payment_method_id: string; stripe_payment_method_id: string }> {
  return api.post<{
    payment_method_id: string;
    stripe_payment_method_id: string;
  }>(`${base(workspaceId)}/store-card`, body);
}

export async function listInvoices(
  workspaceId: string,
): Promise<{ items: InvoiceSummary[]; next_cursor: string | null }> {
  return api.get<{ items: InvoiceSummary[]; next_cursor: string | null }>(
    `${base(workspaceId)}/invoices`,
  );
}

export async function getInvoice(
  workspaceId: string,
  invoiceId: string,
): Promise<InvoiceSummary> {
  return api.get<InvoiceSummary>(`${base(workspaceId)}/invoices/${invoiceId}`);
}
