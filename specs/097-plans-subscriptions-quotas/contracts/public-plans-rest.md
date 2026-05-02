# Contract — Public Plans REST API

**Prefix**: `/api/v1/public/plans`
**Owner**: `apps/control-plane/src/platform/billing/plans/public_router.py`
**Authorization**: NONE — this endpoint is public (per FR-008). Used by the marketing pricing page.
**OpenAPI tag**: `public.plans`.

## `GET /api/v1/public/plans`

Returns every plan with `is_public=true` along with its currently-published (non-deprecated) version's parameters. Excludes Enterprise (which is `is_public=false` by default).

```jsonc
{
  "plans": [
    {
      "slug": "free",
      "display_name": "Free",
      "description": "Perfect for getting started",
      "tier": "free",
      "allowed_model_tier": "cheap_only",
      "current_version": {
        "version": 1,
        "price_monthly_eur": 0,
        "executions_per_day": 50,
        "executions_per_month": 100,
        "minutes_per_day": 30,
        "minutes_per_month": 100,
        "max_workspaces": 1,
        "max_agents_per_workspace": 5,
        "max_users_per_workspace": 3,
        "overage_price_per_minute_eur": 0,
        "trial_days": 0
      }
    },
    {
      "slug": "pro",
      "display_name": "Pro",
      "description": "For professional teams shipping agents",
      "tier": "pro",
      "allowed_model_tier": "all",
      "current_version": {
        "version": 2,
        "price_monthly_eur": 59,
        "executions_per_day": 500,
        "executions_per_month": 5000,
        "minutes_per_day": 240,
        "minutes_per_month": 2400,
        "max_workspaces": 5,
        "max_agents_per_workspace": 50,
        "max_users_per_workspace": 25,
        "overage_price_per_minute_eur": 0.10,
        "trial_days": 14
      }
    }
  ]
}
```

## Caching

This endpoint is cached at the edge (1 minute TTL via `Cache-Control: public, max-age=60`). The response can stay stale for up to 60 seconds after a plan version is published — acceptable per SC-001 (60-second propagation budget).

## Error model

The endpoint never returns 4xx for missing plans (the array is empty if no public plans exist). 5xx is the only failure class — falls through to the standard PlatformError shape.
