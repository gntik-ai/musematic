# Contract: Workspace billing REST surface

All endpoints under `/api/v1/workspaces/{workspace_id}/billing/*`. Auth: workspace `owner` or `admin` role. Tenant scope is enforced by the existing tenant-resolver middleware + RLS.

## Endpoints

### `GET /api/v1/workspaces/{workspace_id}/billing`

Existing UPD-047 endpoint. UPD-052 adds these fields to the response:

- `payment_method`: `{ id, brand, last4, exp_month, exp_year, is_default }` or `null`.
- `recent_invoices`: array of up to 6 most recent invoices with `{id, invoice_number, amount_total, currency, status, period_end, pdf_url}`.
- `subscription.cancel_at_period_end`: bool (already exists in UPD-047, populated from local state).

### `POST /api/v1/workspaces/{workspace_id}/billing/upgrade`

Body:
```json
{
  "target_plan_slug": "pro",
  "payment_method_token": "pm_xxx",       // Stripe SetupIntent confirm result
  "billing_address": {                    // optional; required for Stripe Tax to compute IVA
    "line1": "Calle Mayor 1",
    "city": "Madrid",
    "postal_code": "28001",
    "country": "ES"
  }
}
```

Response 200: `{ "subscription_id": "...", "stripe_subscription_id": "...", "status": "active|trialing", "next_invoice_eur": "20.00" }`.

Errors:
- `400 invalid_payment_method_token` — token format invalid or doesn't belong to the workspace's customer.
- `402 payment_required` — Stripe rejected the charge (insufficient funds, declined, SCA failure).
- `409 already_on_target_plan` — target_plan_slug equals current plan.
- `503 stripe_unavailable` — Stripe API unreachable; retry later.

### `POST /api/v1/workspaces/{workspace_id}/billing/portal-session`

Creates a Stripe Customer Portal session and returns the redirect URL. Rate-limited to 10/h per customer.

Body: `{ "return_url": "/workspaces/{id}/billing" }`. The return URL is validated against an allowlist of relative paths.

Response 200: `{ "portal_url": "https://billing.stripe.com/p/session/..." }`.

Errors:
- `404 customer_not_found` — workspace has no Stripe customer record yet.
- `429 rate_limited` — too many portal sessions in the rolling hour.

### `POST /api/v1/workspaces/{workspace_id}/billing/cancel`

Body:
```json
{
  "reason": "switched_to_competitor|too_expensive|missing_features|other",
  "reason_text": "free-form details (optional, max 1000 chars)"
}
```

Sets the Stripe subscription to `cancel_at_period_end=true`, transitions local status to `cancellation_pending`, persists the reason for retention analysis. Email confirmation is dispatched via UPD-077.

Response 200: `{ "subscription_id": "...", "ends_at": "2026-06-04T00:00:00Z" }`.

Errors:
- `409 already_cancelled` — subscription is already pending cancellation or canceled.
- `403 not_owner` — non-owner attempted to cancel.

### `POST /api/v1/workspaces/{workspace_id}/billing/reactivate`

Reverses a pending cancellation. Sets Stripe `cancel_at_period_end=false`, transitions local status to `active`. Only valid while `cancellation_pending` and the period has not yet ended.

Response 200: `{ "subscription_id": "...", "status": "active" }`.

Errors:
- `409 not_cancellation_pending` — subscription is not in `cancellation_pending` state.
- `409 period_already_ended` — too late; subscription is now `canceled`.

### `GET /api/v1/workspaces/{workspace_id}/billing/invoices?limit=20&cursor=...`

Cursor-paginated invoice list. The cursor is opaque (encoded period_end timestamp).

Response 200:
```json
{
  "items": [
    {
      "id": "...",
      "invoice_number": "INV-0001-000123",
      "amount_total": "24.20",
      "amount_subtotal": "20.00",
      "amount_tax": "4.20",
      "currency": "EUR",
      "status": "paid",
      "period_start": "2026-05-01T00:00:00Z",
      "period_end": "2026-06-01T00:00:00Z",
      "issued_at": "2026-06-01T00:05:00Z",
      "paid_at": "2026-06-01T00:05:30Z",
      "pdf_url": "https://files.stripe.com/v3/files/..."
    }
  ],
  "next_cursor": "..."
}
```
