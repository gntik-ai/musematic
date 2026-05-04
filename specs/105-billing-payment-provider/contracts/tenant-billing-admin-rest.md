# Contract: Enterprise tenant billing (admin)

All endpoints under `/api/v1/admin/tenants/{tenant_id}/billing/*`. Auth: `platform_admin` or tenant `admin` role.

## `GET /api/v1/admin/tenants/{tenant_id}/billing`

Returns the tenant-level billing summary for Enterprise. Default tenants will return 404 because their billing is per-workspace.

Response 200:
```json
{
  "tenant_id": "...",
  "stripe_customer_id": "cus_...",
  "subscription": {
    "id": "...",
    "stripe_subscription_id": "sub_...",
    "status": "active",
    "current_period_start": "...",
    "current_period_end": "...",
    "cancel_at_period_end": false,
    "plan_slug": "enterprise_custom"
  },
  "payment_method": { "brand": "visa", "last4": "4242", "is_default": true },
  "outstanding_invoices_eur": "0.00",
  "next_invoice_eur_estimate": "1200.00",
  "recent_invoices": [ ... ]
}
```

Errors:
- `404 tenant_billing_not_found` — tenant is `default` kind or has no Stripe customer record.

## `POST /api/v1/admin/tenants/{tenant_id}/billing/portal-session`

Same shape as the workspace portal session, scoped to the tenant. Returns the Stripe portal URL for the tenant admin.

## `POST /api/v1/admin/tenants/{tenant_id}/billing/force-suspend`

Operator-emergency endpoint. Suspends the tenant's subscription immediately (not at period end). **Requires 2PA** per rule 33.

Body: `{ "reason": "free-form, audit-logged", "two_pa_consume_token": "..." }`.

Response 200: `{ "subscription_id": "...", "status": "suspended" }`.

The 2PA token is consumed via the existing `TwoPersonApprovalService` and the action_type is `billing.force_suspend`.

## `POST /api/v1/admin/tenants/{tenant_id}/billing/force-downgrade`

Operator-emergency endpoint. Downgrades the tenant immediately to a target plan slug (typically `free`). **Requires 2PA** per rule 33.

Body: `{ "target_plan_slug": "free", "reason": "...", "two_pa_consume_token": "..." }`.

## Resolution endpoint for grace records

`POST /api/v1/admin/tenants/{tenant_id}/billing/grace/{grace_id}/resolve`

Manually resolves a `payment_failure_grace` row (e.g., when the operator confirmed the customer paid out-of-band). Sets `resolved_at = now`, `resolution = 'manually_resolved'`. Audit-logged. **Does not require 2PA** (it's a closing action, not a coercive one).

Body: `{ "note": "..." }`.

Response 200: `{ "grace_id": "...", "resolved_at": "...", "resolution": "manually_resolved" }`.

Errors:
- `404 grace_not_found` — grace row does not belong to the tenant.
- `409 grace_already_resolved` — already closed.
