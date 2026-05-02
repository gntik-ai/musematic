# Contract — Admin Plans REST API

**Prefix**: `/api/v1/admin/plans/*`
**Owner**: `apps/control-plane/src/platform/billing/plans/admin_router.py`
**Authorization**: Super admin role (`require_superadmin`).
**OpenAPI tag**: `admin.plans`.

## `GET /api/v1/admin/plans`

List plans with filters. Response:

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "slug": "pro",
      "display_name": "Pro",
      "tier": "pro",
      "is_public": true,
      "is_active": true,
      "allowed_model_tier": "all",
      "current_published_version": 2,
      "active_subscription_count": 142,
      "created_at": "2026-05-02T00:00:00Z"
    }
  ]
}
```

Query: `tier`, `is_active`, `is_public`.

## `POST /api/v1/admin/plans`

Create a new plan (the catalogue row, not a version). Body:

```jsonc
{
  "slug": "team",
  "display_name": "Team",
  "description": "Mid-tier plan...",
  "tier": "pro",
  "is_public": true,
  "allowed_model_tier": "all"
}
```

Response 201 with the created plan. Note: a Plan with no published `PlanVersion` cannot be subscribed to — admin must call the publish-version endpoint next.

## `GET /api/v1/admin/plans/{slug}`

Single plan with the latest published version inlined and a count of total versions.

## `GET /api/v1/admin/plans/{slug}/versions`

List every version of the plan. Response:

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "version": 2,
      "price_monthly": 59.00,
      "executions_per_day": 500,
      "executions_per_month": 5000,
      "minutes_per_day": 240,
      "minutes_per_month": 2400,
      "max_workspaces": 5,
      "max_agents_per_workspace": 50,
      "max_users_per_workspace": 25,
      "overage_price_per_minute": 0.10,
      "trial_days": 14,
      "quota_period_anchor": "subscription_anniversary",
      "extras": {},
      "published_at": "2026-05-02T10:30:00Z",
      "deprecated_at": null,
      "subscription_count": 0,
      "diff_against_prior": {
        "price_monthly": {"from": 49.00, "to": 59.00}
      }
    },
    {
      "id": "uuid",
      "version": 1,
      "price_monthly": 49.00,
      "...": "...",
      "deprecated_at": "2026-05-02T10:30:00Z",
      "subscription_count": 142
    }
  ]
}
```

## `POST /api/v1/admin/plans/{slug}/versions`

Publish a new version. Body is the complete parameter set:

```jsonc
{
  "price_monthly": 59.00,
  "executions_per_day": 500,
  "executions_per_month": 5000,
  "minutes_per_day": 240,
  "minutes_per_month": 2400,
  "max_workspaces": 5,
  "max_agents_per_workspace": 50,
  "max_users_per_workspace": 25,
  "overage_price_per_minute": 0.10,
  "trial_days": 14,
  "quota_period_anchor": "subscription_anniversary",
  "extras": {}
}
```

Response 201:

```jsonc
{
  "id": "uuid",
  "version": 2,
  "published_at": "2026-05-02T10:30:00Z",
  "diff_against_prior": { "price_monthly": {"from": 49.00, "to": 59.00} }
}
```

Side effects: appends to `plan_versions`, sets `deprecated_at` on the immediately prior version, emits `billing.plan.published` Kafka event, records audit chain entry with the diff and the super-admin principal.

Errors: `409 plan_version_in_progress` if a publish is already in-flight (advisory lock contention); `422 invalid_parameters` if any quota field is negative or the parameter shape is malformed.

## `POST /api/v1/admin/plans/{slug}/versions/{version}/deprecate`

Manually deprecate a specific version (without publishing a new one). Used for "stop accepting new subs at this price tier" without changing terms. Empty body. Sets `deprecated_at`. Idempotent — second call is a no-op.

## `PATCH /api/v1/admin/plans/{slug}`

Update plan metadata (`display_name`, `description`, `is_public`, `is_active`). Cannot change `slug`, `tier`, or `allowed_model_tier` (those changes require new plan creation).

## Error model

Standard `PlanError` shape inheriting from `PlatformError`. Codes:

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 403 | `not_super_admin` |
| 404 | `plan_not_found`, `plan_version_not_found` |
| 409 | `plan_slug_taken`, `plan_version_in_progress`, `plan_version_immutable` |
| 422 | `invalid_parameters`, `tier_invalid`, `allowed_model_tier_invalid` |
