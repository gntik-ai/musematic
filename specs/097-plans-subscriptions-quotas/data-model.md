# Phase 1 — Data Model

**Feature**: UPD-047 — Plans, Subscriptions, and Quotas
**Date**: 2026-05-02

This document specifies the database schema introduced or modified by UPD-047. Five new tables, one additive column on an existing table, one trigger, one Kafka topic. All tenant-scoped tables follow the UPD-046 conventions (`tenant_id NOT NULL` + RLS policy + `tenant_id` index).

## Entity 1 — `Plan`

**Owning bounded context**: `apps/control-plane/src/platform/billing/plans/`
**Table**: `plans`
**Owner**: `billing/plans/models.py`
**Migration**: `103_billing_plans_subscriptions_usage_overage.py`
**RLS**: NOT tenant-scoped — plans are catalogue rows, the same set is visible to all tenants. Read access is unrestricted; write access is gated at the router by `require_superadmin`.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `slug` | `VARCHAR(32)` | `NOT NULL UNIQUE` | URL-safe; used in `/admin/plans/{slug}` paths. |
| `display_name` | `VARCHAR(128)` | `NOT NULL` | Rendered in pricing UI. |
| `description` | `TEXT` | NULL | Marketing copy. |
| `tier` | `VARCHAR(16)` | `NOT NULL`, `CHECK (tier IN ('free', 'pro', 'enterprise'))` | Constitutional rule SaaS-2 / SaaS-4. |
| `is_public` | `BOOLEAN` | `NOT NULL DEFAULT true` | Controls visibility on `/api/v1/public/plans`. Enterprise is `false`. |
| `is_active` | `BOOLEAN` | `NOT NULL DEFAULT true` | Controls whether new subscriptions can target this plan. |
| `allowed_model_tier` | `VARCHAR(32)` | `NOT NULL DEFAULT 'all'`, `CHECK (allowed_model_tier IN ('cheap_only', 'standard', 'all'))` | Constitutional rule SaaS-13 — Free is `cheap_only`. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |

### Indexes

- `plans_pkey` (implicit on `id`).
- `plans_slug_key` UNIQUE (implicit).
- `plans_tier_active_idx` on `(tier, is_active)` — for `/admin/plans` filtering and the public-pricing query.

## Entity 2 — `PlanVersion`

**Owning bounded context**: `apps/control-plane/src/platform/billing/plans/`
**Table**: `plan_versions`
**Owner**: `billing/plans/models.py`
**Migration**: `103_billing_plans_subscriptions_usage_overage.py`
**RLS**: NOT tenant-scoped — same rationale as `plans`.
**Immutability**: Append-only. Once `published_at IS NOT NULL`, only `deprecated_at` and `extras_json` (forward-compatible additions) may change. A trigger refuses any other UPDATE.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `plan_id` | `UUID` | `NOT NULL REFERENCES plans(id)` | |
| `version` | `INTEGER` | `NOT NULL` | Sequential per plan_id; service computes next via `MAX(version) + 1`. |
| `price_monthly` | `DECIMAL(10, 2)` | `NOT NULL DEFAULT 0` | EUR. |
| `executions_per_day` | `INTEGER` | `NOT NULL DEFAULT 0` | 0 = unlimited per FR-003. |
| `executions_per_month` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `minutes_per_day` | `INTEGER` | `NOT NULL DEFAULT 0` | Active compute minutes per AD-29. |
| `minutes_per_month` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `max_workspaces` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `max_agents_per_workspace` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `max_users_per_workspace` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `overage_price_per_minute` | `DECIMAL(10, 4)` | `NOT NULL DEFAULT 0` | 0 = no overage permitted. |
| `trial_days` | `INTEGER` | `NOT NULL DEFAULT 0` | |
| `quota_period_anchor` | `VARCHAR(32)` | `NOT NULL DEFAULT 'calendar_month'`, `CHECK (quota_period_anchor IN ('calendar_month', 'subscription_anniversary'))` | |
| `extras_json` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Forward-compatible parameters. |
| `published_at` | `TIMESTAMPTZ` | NULL | NULL = draft (rare; the publish flow goes draft→published in one transaction). |
| `deprecated_at` | `TIMESTAMPTZ` | NULL | Set when a newer version is published or super admin manually deprecates. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `created_by` | `UUID` | NULL, FK `users.id` | Authoring super admin. NULL for the seeded version-1 rows. |

### Indexes

- `plan_versions_pkey` (implicit on `id`).
- `plan_versions_plan_version_key` UNIQUE on `(plan_id, version)`.
- `plan_versions_plan_published_idx` on `(plan_id, published_at)` `WHERE deprecated_at IS NULL` — for "find current published version of plan X" queries.

### Triggers

- `plan_versions_immutable_after_publish` BEFORE UPDATE — refuses any change to fields other than `deprecated_at` or `extras_json` once `published_at IS NOT NULL`. FR-006.
- `plan_versions_no_delete_published` BEFORE DELETE — refuses delete of any published row. Reinforces append-only semantics.

## Entity 3 — `Subscription`

**Owning bounded context**: `apps/control-plane/src/platform/billing/subscriptions/`
**Table**: `subscriptions`
**Owner**: `billing/subscriptions/models.py`
**Migration**: `103_billing_plans_subscriptions_usage_overage.py`
**RLS**: Tenant-scoped per UPD-046 conventions.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `tenant_id` | `UUID` | `NOT NULL REFERENCES tenants(id)` | UPD-046 convention. |
| `scope_type` | `VARCHAR(16)` | `NOT NULL`, `CHECK (scope_type IN ('workspace', 'tenant'))` | |
| `scope_id` | `UUID` | `NOT NULL` | Workspace ID for `scope_type='workspace'`; tenant ID for `scope_type='tenant'`. Composite uniqueness with `scope_type` enforces "at most one subscription per scope". |
| `plan_id` | `UUID` | `NOT NULL REFERENCES plans(id)` | |
| `plan_version` | `INTEGER` | `NOT NULL` | Pinned version per FR-022 / SaaS-22. |
| `status` | `VARCHAR(32)` | `NOT NULL`, `CHECK (status IN ('trial', 'active', 'past_due', 'cancellation_pending', 'canceled', 'suspended'))` | State machine below. |
| `started_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `current_period_start` | `TIMESTAMPTZ` | `NOT NULL` | |
| `current_period_end` | `TIMESTAMPTZ` | `NOT NULL` | |
| `cancel_at_period_end` | `BOOLEAN` | `NOT NULL DEFAULT false` | Set by FR-013 downgrade flow. |
| `payment_method_id` | `UUID` | NULL | FK populated by UPD-052. |
| `stripe_customer_id` | `VARCHAR(64)` | NULL | Populated by UPD-052. Plain text per research R12. |
| `stripe_subscription_id` | `VARCHAR(64)` | NULL | Populated by UPD-052. |
| `created_by_user_id` | `UUID` | NULL, FK `users.id` | NULL for the migration-backfilled Free subscriptions. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | Updated via standard `TimestampMixin` pattern. |

### Foreign keys

- `(plan_id, plan_version) REFERENCES plan_versions(plan_id, version)` — composite FK to the pinned version.

### Indexes

- `subscriptions_pkey` (implicit on `id`).
- `subscriptions_scope_unique` UNIQUE on `(scope_type, scope_id)` — at most one subscription per scope per FR-009.
- `subscriptions_tenant_idx` on `(tenant_id)`.
- `subscriptions_status_period_end_idx` on `(status, current_period_end)` — for the period-rollover scheduler query.
- `subscriptions_plan_version_idx` on `(plan_id, plan_version)` — for "count subs on this version" admin queries.

### RLS

```sql
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON subscriptions
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
```

### Triggers

- `subscriptions_scope_check` BEFORE INSERT OR UPDATE — refuses where `scope_type='workspace'` AND tenant kind is `enterprise`, OR where `scope_type='tenant'` AND tenant kind is `default`. Constitutional rule SaaS-29 / SaaS-30; FR-040.

## Entity 4 — `UsageRecord`

**Owning bounded context**: `apps/control-plane/src/platform/billing/quotas/`
**Table**: `usage_records`
**Owner**: `billing/quotas/models.py`
**Migration**: `103_billing_plans_subscriptions_usage_overage.py`
**RLS**: Tenant-scoped.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `tenant_id` | `UUID` | `NOT NULL REFERENCES tenants(id)` | |
| `workspace_id` | `UUID` | `NOT NULL` | Even for Enterprise tenant-scoped subscriptions, usage is recorded per-workspace for chargeback fidelity. |
| `subscription_id` | `UUID` | `NOT NULL REFERENCES subscriptions(id)` | |
| `metric` | `VARCHAR(32)` | `NOT NULL`, `CHECK (metric IN ('executions', 'minutes'))` | |
| `period_start` | `TIMESTAMPTZ` | `NOT NULL` | |
| `period_end` | `TIMESTAMPTZ` | `NOT NULL` | |
| `quantity` | `DECIMAL(20, 4)` | `NOT NULL DEFAULT 0` | Cumulative count for `executions`; cumulative active minutes for `minutes`. |
| `is_overage` | `BOOLEAN` | `NOT NULL DEFAULT false` | Rows with `is_overage=true` represent the post-cap portion. |

### Indexes

- `usage_records_pkey` (implicit on `id`).
- `usage_records_unique_aggregate` UNIQUE on `(tenant_id, workspace_id, subscription_id, metric, period_start, is_overage)` — idempotent upsert target.
- `usage_records_subscription_period_idx` on `(subscription_id, period_start, metric)` — quota-check hot path.

### Companion table — `processed_event_ids`

Per research R6, a separate table guards metering idempotency:

```sql
CREATE TABLE processed_event_ids (
  event_id UUID PRIMARY KEY,
  consumer_name VARCHAR(64) NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX processed_event_ids_consumer_idx ON processed_event_ids (consumer_name, processed_at);
```

The metering job writes to this table in the same transaction that upserts `usage_records`. Reconciliation job at 02:00 UTC re-reads the prior 24 hours and asserts every Kafka event has a `processed_event_ids` row.

### RLS

Same pattern as `subscriptions`.

## Entity 5 — `OverageAuthorization`

**Owning bounded context**: `apps/control-plane/src/platform/billing/quotas/`
**Table**: `overage_authorizations`
**Owner**: `billing/quotas/models.py`
**Migration**: `103_billing_plans_subscriptions_usage_overage.py`
**RLS**: Tenant-scoped.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `tenant_id` | `UUID` | `NOT NULL REFERENCES tenants(id)` | |
| `workspace_id` | `UUID` | `NOT NULL` | |
| `subscription_id` | `UUID` | `NOT NULL REFERENCES subscriptions(id)` | |
| `billing_period_start` | `TIMESTAMPTZ` | `NOT NULL` | Matches the subscription's period at the time of authorization. |
| `billing_period_end` | `TIMESTAMPTZ` | `NOT NULL` | |
| `authorized_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `authorized_by_user_id` | `UUID` | `NOT NULL`, FK `users.id` | Workspace admin per FR-036. |
| `max_overage_eur` | `DECIMAL(10, 2)` | NULL | NULL = unlimited within the period. |
| `revoked_at` | `TIMESTAMPTZ` | NULL | A workspace admin may revoke per security note in user input. |
| `revoked_by_user_id` | `UUID` | NULL, FK `users.id` | |

### Indexes

- `overage_authorizations_pkey` (implicit).
- `overage_authorizations_workspace_period_unique` UNIQUE on `(workspace_id, billing_period_start)` — idempotency anchor per FR-019, SC-007.
- `overage_authorizations_subscription_period_idx` on `(subscription_id, billing_period_start)` — for "is overage authorized for this sub right now?" queries.

### RLS

Same pattern as `subscriptions`.

## Modification — `cost_attributions.subscription_id`

**Owning bounded context**: existing `apps/control-plane/src/platform/cost_governance/`
**Migration**: `104_cost_attributions_subscription_id.py`

```sql
ALTER TABLE cost_attributions
  ADD COLUMN subscription_id UUID NULL REFERENCES subscriptions(id) ON DELETE SET NULL;
CREATE INDEX cost_attributions_subscription_idx ON cost_attributions (subscription_id);
```

`cost_governance/services/attribution_service.py:_record_step_cost()` is updated to call `subscription_resolver.resolve_active_subscription(workspace_id)` and pass the result as `subscription_id`. Pre-existing rows have `NULL`; the read path tags retroactively per FR-030.

## State machine — `Subscription.status`

```text
                                            (period rollover with cancel_at_period_end=true)
       (provision)                          ┌──────────────────────────────────────────────────┐
            │                               │                                                  ↓
        ┌───┴───┐                           │
        │ trial │                           │                                              ┌──────────┐
        └───┬───┘                           │              ┌─── (super admin reactivate)──>│  active  │
            │ (trial expires + payment OK)  │              │                                └────┬─────┘
            ↓                               │              │                                     │
        ┌────────┐ ←── (super admin reactivate) ── ┌────────┐                                    │ (user schedules downgrade)
        │ active │ ── (payment fails) ────────────>│ past_due│                                    ↓
        └────┬───┘                                  └───┬────┘                            ┌─────────────────────────┐
             │                                          │ (grace expires)                 │ cancellation_pending    │
             │                                          ↓                                 └────────────┬────────────┘
             │                                  ┌──────────┐                                           │ (user cancels schedule)
             │                                  │ canceled │                                           │
             │                                  └──────────┘                                           │ (period rollover)
             │ (super admin suspends)                                                                  ↓
             ↓                                                                                ┌──────────┐
        ┌────────────┐                                                                        │ canceled │
        │ suspended  │ ── (super admin reactivate) ──→ active                                 └──────────┘
        └────────────┘
```

`canceled` is a terminal status for that subscription row. A subsequent re-subscription creates a new row.

## Seed — Default plans (migration 103)

The migration runs the SQL inserts listed in `research.md` R1. The seed is idempotent (`ON CONFLICT (slug) DO NOTHING` for plans; `ON CONFLICT (plan_id, version) DO NOTHING` for plan_versions). The default-tenant Free subscriptions backfill (research R9) follows in the same migration.

## Kafka topic — `billing.lifecycle`

Owner: `apps/control-plane/src/platform/billing/subscriptions/events.py`
Producer: `SubscriptionService` after every state change (post-commit outbox pattern).
Partition key: `tenant_id` for per-tenant ordering.
Event types: `billing.plan.published`, `billing.plan.deprecated`, `billing.subscription.created`, `billing.subscription.upgraded`, `billing.subscription.downgrade_scheduled`, `billing.subscription.downgrade_cancelled`, `billing.subscription.downgrade_effective`, `billing.subscription.suspended`, `billing.subscription.reactivated`, `billing.subscription.canceled`, `billing.subscription.period_renewed`, `billing.overage.authorized`, `billing.overage.revoked`, `billing.overage.cap_reached`. Detailed payload schemas in `contracts/billing-events-kafka.md`.

## End of data model.
