# Contract: Invoices REST surface

Read-only invoice surface for workspace owners/admins (workspace scope) and tenant admins (Enterprise tenant scope). Operated under `apps/control-plane/src/platform/billing/invoices/router.py`.

The list endpoint is documented in the workspace-billing contract; this file covers the per-invoice detail and the PDF redirect.

## `GET /api/v1/workspaces/{workspace_id}/billing/invoices/{invoice_id}`

Returns the full invoice row plus the line-items summary stored in `metadata_json`.

Response 200:
```json
{
  "id": "...",
  "stripe_invoice_id": "in_...",
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
  "pdf_url": "https://files.stripe.com/v3/files/...",
  "line_items": [
    {"description": "Pro plan — May 2026", "amount": "20.00", "quantity": 1},
    {"description": "Overage minutes (50 @ €0.10)", "amount": "5.00", "quantity": 50}
  ],
  "tax_breakdown": {
    "country": "ES",
    "vat_rate": "21.0",
    "amount": "4.20",
    "type": "value_added_tax"
  }
}
```

Errors:
- `404 invoice_not_found` — invoice does not belong to the workspace.

## `GET /api/v1/workspaces/{workspace_id}/billing/invoices/{invoice_id}/pdf`

302 redirect to the Stripe-hosted PDF URL. The platform never proxies the bytes — it issues a redirect after verifying:
1. The invoice belongs to the workspace.
2. The caller has `owner` or `admin` role.
3. The Stripe-hosted URL is non-null and not expired (Stripe rotates these URLs roughly every 30 days; on expiry, a fresh `Invoice.retrieve()` Stripe call refreshes `pdf_url` server-side before the redirect).

The redirect target is logged in the audit chain (entry payload includes `invoice_id` only; not the URL).

Errors:
- `404 invoice_not_found` — same as above.
- `409 pdf_unavailable` — Stripe has not yet finalized the PDF (status `draft`).

## Tenant-scope variant (Enterprise)

For Enterprise tenants the same endpoints are exposed under `/api/v1/admin/tenants/{tenant_id}/billing/invoices*` and require `platform_admin` or tenant `admin` role. The shape of the responses is identical.
