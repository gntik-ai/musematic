# Contract — Workspace Billing REST API

**Prefix**: `/api/v1/workspaces/{workspace_id}/billing/*`
**Owner**: `apps/control-plane/src/platform/billing/subscriptions/router.py`
**Authorization**: Workspace member roles (varies per endpoint).
**OpenAPI tag**: `workspace.billing`.

## `GET /api/v1/workspaces/{workspace_id}/billing`

Workspace billing summary for the current period. Read by all workspace members.

```jsonc
{
  "subscription": {
    "id": "uuid",
    "scope_type": "workspace",
    "plan_slug": "pro",
    "plan_version": 2,
    "status": "active",
    "current_period_start": "2026-05-01T00:00:00Z",
    "current_period_end": "2026-06-01T00:00:00Z",
    "cancel_at_period_end": false,
    "trial_expires_at": null,
    "next_billing_eur": 49.00
  },
  "plan_caps": {
    "executions_per_day": 500,
    "executions_per_month": 5000,
    "minutes_per_day": 240,
    "minutes_per_month": 2400,
    "max_workspaces": 5,
    "max_agents_per_workspace": 50,
    "max_users_per_workspace": 25,
    "overage_price_per_minute": 0.10,
    "allowed_model_tier": "all"
  },
  "usage": {
    "executions_today": 42,
    "executions_this_period": 1287,
    "minutes_today": 24.5,
    "minutes_this_period": 815.0,
    "active_workspaces": 2,
    "active_agents_in_this_workspace": 11,
    "active_users_in_this_workspace": 4
  },
  "forecast": {
    "executions_at_period_end": 4290,
    "minutes_at_period_end": 2715.0,
    "estimated_overage_eur": 31.50,
    "burn_rate_minutes_per_day": 90.5
  },
  "overage": {
    "is_authorized": false,
    "authorization_id": null,
    "max_overage_eur": null,
    "authorized_by": null,
    "authorized_at": null
  },
  "payment_method": {
    "status": "captured",                          // populated by UPD-052
    "last_four": "4242",
    "expires": "2027-06"
  },
  "available_actions": ["upgrade_to_enterprise"]   // computed; "downgrade_to_free" is hidden when there's no lower tier
}
```

## `POST /api/v1/workspaces/{workspace_id}/billing/upgrade`

Workspace admin or owner only. Initiates an upgrade flow. Body:

```jsonc
{
  "target_plan_slug": "pro",
  "payment_method_token": "pm_token_from_stripe_or_stub"
}
```

Response 200 (sync) or 202 (async, when Stripe webhooks must confirm post-UPD-052):

```jsonc
{
  "preview": {
    "prorated_charge_eur": 32.66,
    "prorated_credit_eur": 0,
    "next_full_invoice_eur": 49.00,
    "effective_at": "2026-05-02T10:30:00Z"
  },
  "subscription_after": {
    "plan_slug": "pro",
    "plan_version": 2,
    "current_period_end": "2026-06-01T00:00:00Z"
  }
}
```

## `POST /api/v1/workspaces/{workspace_id}/billing/downgrade`

Workspace admin or owner only. Schedules a downgrade. Body:

```jsonc
{
  "target_plan_slug": "free"
}
```

Sets `cancel_at_period_end=true` and status `cancellation_pending`. Returns the schedule.

## `POST /api/v1/workspaces/{workspace_id}/billing/cancel-downgrade`

Workspace admin or owner only. Empty body. Reverts a scheduled downgrade. Status returns to active Pro.

## `GET /api/v1/workspaces/{workspace_id}/billing/overage-authorization`

All workspace members may read the current authorization state (workspace admins see the same shape with action affordances).

```jsonc
{
  "billing_period_start": "2026-05-01T00:00:00Z",
  "billing_period_end": "2026-06-01T00:00:00Z",
  "is_authorized": false,
  "authorization_required": true,
  "current_overage_eur": 0,
  "max_overage_eur": null,
  "forecast_total_overage_eur": 31.50
}
```

## `POST /api/v1/workspaces/{workspace_id}/billing/overage-authorization`

Workspace admin only. Body:

```jsonc
{ "max_overage_eur": 50.00 }
```

`max_overage_eur` is optional; NULL means unlimited within the period. Idempotent on `(workspace_id, billing_period_start)` per FR-019. Returns the resulting authorization.

## `DELETE /api/v1/workspaces/{workspace_id}/billing/overage-authorization`

Workspace admin only. Revokes the current authorization (sets `revoked_at`). Pauses subsequent overage executions. Notifies all workspace members.

## `GET /api/v1/workspaces/{workspace_id}/billing/usage-history`

Per-period usage history (last 12 periods). Same shape as `/api/v1/admin/subscriptions/{id}/usage` filtered to the workspace.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 402 | `quota_exceeded`, `overage_cap_exceeded`, `model_tier_not_allowed` |
| 403 | `not_workspace_admin`, `subscription_suspended`, `no_active_subscription` |
| 404 | `workspace_not_found` |
| 409 | `concurrent_authorization`, `downgrade_already_scheduled` |
| 422 | `target_plan_not_public`, `payment_method_required`, `negative_max_overage` |

## Quota-rejection response shape (FR-017)

When any chargeable endpoint elsewhere in the platform refuses with HTTP 402 due to quota:

```jsonc
{
  "code": "quota_exceeded",
  "message": "This workspace has reached its monthly execution cap.",
  "details": {
    "quota_name": "executions_per_month",
    "current": 5000,
    "limit": 5000,
    "reset_at": "2026-06-01T00:00:00Z",
    "plan_slug": "pro",
    "upgrade_url": "/workspaces/{workspace_id}/billing/upgrade",
    "overage_available": false
  }
}
```

When the failure is `overage_cap_exceeded` (Pro with EUR cap reached) or `model_tier_not_allowed` (Free attempting premium model), the same shape is returned with the appropriate `code` and `quota_name`.
