# Contract — Admin Subscriptions REST API

**Prefix**: `/api/v1/admin/subscriptions/*`
**Owner**: `apps/control-plane/src/platform/billing/subscriptions/admin_router.py`
**Authorization**: Super admin role (`require_superadmin`). Cross-tenant reads use the privileged platform-staff session per UPD-046 conventions.
**OpenAPI tag**: `admin.subscriptions`.

## `GET /api/v1/admin/subscriptions`

Cross-tenant subscription listing with filters and cursor pagination.

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "tenant_id": "uuid",
      "tenant_slug": "acme",
      "scope_type": "tenant",                     // or "workspace"
      "scope_id": "uuid",
      "scope_label": "Acme Corp",                  // joined from tenants or workspaces
      "plan_slug": "enterprise",
      "plan_version": 1,
      "status": "active",
      "started_at": "2026-04-15T00:00:00Z",
      "current_period_start": "2026-05-01T00:00:00Z",
      "current_period_end": "2026-06-01T00:00:00Z",
      "cancel_at_period_end": false,
      "stripe_subscription_id": "sub_…",            // populated by UPD-052
      "trial_expires_at": null
    }
  ],
  "next_cursor": "opaque-token-or-null"
}
```

Query: `tenant_id`, `plan_slug`, `status`, `payment_status` (post-UPD-052), `trial_expiring_within_days`, `cursor`, `limit`.

## `GET /api/v1/admin/subscriptions/{id}`

Single subscription detail including: status timeline (every transition with timestamp + actor), current usage progress bars (executions today/month, minutes today/month) computed from `usage_records`, plan version pinning info, payment history (post-UPD-052).

## `POST /api/v1/admin/subscriptions/{id}/suspend`

Body:

```jsonc
{ "reason": "Account under fraud review" }
```

Transitions status to `suspended`. Audit-chain + Kafka emitted.

## `POST /api/v1/admin/subscriptions/{id}/reactivate`

Empty body. Transitions `suspended → active`.

## `POST /api/v1/admin/subscriptions/{id}/migrate-version`

Manually migrate a subscription to a different plan version (typically used when a deprecated version becomes problematic and super admin needs to move stragglers forward). Body:

```jsonc
{
  "target_plan_id": "uuid",
  "target_plan_version": 3,
  "effective": "next_period"                       // "immediate" requires 2PA per audit-pass rule 33
}
```

Response 200 with updated subscription.

## `GET /api/v1/admin/subscriptions/{id}/usage`

Per-period usage breakdown for the subscription, useful for support / chargeback investigation:

```jsonc
{
  "items": [
    {
      "period_start": "2026-05-01T00:00:00Z",
      "period_end": "2026-06-01T00:00:00Z",
      "executions_total": 4823,
      "executions_overage": 0,
      "minutes_total": 2287.5,
      "minutes_overage": 0,
      "cost_attributed_total_cents": 412500
    }
  ]
}
```

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 403 | `not_super_admin` |
| 404 | `subscription_not_found` |
| 409 | `concurrent_lifecycle_action`, `cannot_migrate_canceled_subscription` |
| 422 | `target_version_not_published`, `effective_immediate_requires_2pa` |
