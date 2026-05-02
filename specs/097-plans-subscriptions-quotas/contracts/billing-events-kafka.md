# Contract — Billing Lifecycle Kafka Events

**Topic**: `billing.lifecycle`
**Owner**: `apps/control-plane/src/platform/billing/subscriptions/events.py`
**Producer**: `PlanService` and `SubscriptionService` (after a successful state change, post-commit outbox).
**Consumers** (initial set): `audit/projection.py` (audit-chain projection), `notifications/consumers/billing.py` (workspace notification fan-out), `analytics/consumers/billing.py` (commercial KPI dashboard), `cost_governance/consumers/subscription_link.py` (back-tag legacy cost rows on first read).
**Partition key**: `tenant_id` (UUID string) — guarantees per-tenant ordering.

## Envelope

The canonical `EventEnvelope` from UPD-013, with `tenant_id` and additional `subscription_id` (when applicable):

```jsonc
{
  "event_id": "uuid",
  "event_type": "billing.subscription.upgraded",
  "schema_version": 1,
  "occurred_at": "2026-05-02T10:30:00Z",
  "tenant_id": "uuid",
  "subscription_id": "uuid",                       // optional; absent for plan-level events
  "correlation_id": "uuid",
  "actor": {
    "user_id": "uuid",
    "role": "workspace_admin"
  },
  "trace_id": "32-char-otel-id",
  "payload": { ... }
}
```

## Plan-level event types

### `billing.plan.published`

```jsonc
{
  "plan_id": "uuid",
  "plan_slug": "pro",
  "new_version": 2,
  "prior_version": 1,
  "diff": {
    "price_monthly": {"from": 49.00, "to": 59.00}
  },
  "deprecated_prior_at": "2026-05-02T10:30:00Z"
}
```

### `billing.plan.deprecated`

```jsonc
{
  "plan_id": "uuid",
  "plan_slug": "pro",
  "version": 1,
  "subscriptions_pinned_count": 142
}
```

## Subscription-level event types

### `billing.subscription.created`

```jsonc
{
  "scope_type": "workspace",                       // or "tenant"
  "scope_id": "uuid",
  "plan_id": "uuid",
  "plan_slug": "free",
  "plan_version": 1,
  "status": "active",                              // or "trial"
  "started_at": "2026-05-02T10:30:00Z",
  "current_period_start": "2026-05-01T00:00:00Z",
  "current_period_end": "2026-06-01T00:00:00Z",
  "trial_expires_at": null
}
```

### `billing.subscription.upgraded`

```jsonc
{
  "from_plan_slug": "free",
  "from_plan_version": 1,
  "to_plan_slug": "pro",
  "to_plan_version": 2,
  "effective_at": "2026-05-02T10:30:00Z",
  "prorated_charge_eur": 32.66
}
```

### `billing.subscription.downgrade_scheduled`

```jsonc
{
  "from_plan_slug": "pro",
  "to_plan_slug": "free",
  "scheduled_for": "2026-06-01T00:00:00Z"
}
```

### `billing.subscription.downgrade_cancelled`

```jsonc
{
  "had_been_scheduled_for": "2026-06-01T00:00:00Z"
}
```

### `billing.subscription.downgrade_effective`

Emitted by the period-rollover scheduler at the moment the downgrade takes effect.

```jsonc
{
  "from_plan_slug": "pro",
  "from_plan_version": 2,
  "to_plan_slug": "free",
  "to_plan_version": 1,
  "data_exceeding_free_limits": {
    "extra_workspaces": 0,
    "extra_agents_in_this_workspace": 7,
    "extra_users_in_this_workspace": 2
  }
}
```

The `data_exceeding_free_limits` payload drives the post-downgrade cleanup banner per FR-014 / spec User Story 6.

### `billing.subscription.suspended`

```jsonc
{ "reason": "Account under fraud review" }
```

### `billing.subscription.reactivated`

```jsonc
{ "previous_status": "suspended" }
```

### `billing.subscription.canceled`

```jsonc
{ "canceled_at": "2026-06-01T00:00:00Z", "final_invoice_eur": 12.50 }
```

### `billing.subscription.period_renewed`

Emitted by the period-rollover scheduler.

```jsonc
{
  "previous_period_start": "2026-04-01T00:00:00Z",
  "previous_period_end": "2026-05-01T00:00:00Z",
  "new_period_start": "2026-05-01T00:00:00Z",
  "new_period_end": "2026-06-01T00:00:00Z",
  "previous_period_overage_eur": 18.20
}
```

## Overage-level event types

### `billing.overage.authorized`

```jsonc
{
  "billing_period_start": "2026-05-01T00:00:00Z",
  "max_overage_eur": 50.00,
  "authorized_by_user_id": "uuid"
}
```

### `billing.overage.revoked`

```jsonc
{
  "billing_period_start": "2026-05-01T00:00:00Z",
  "revoked_by_user_id": "uuid"
}
```

### `billing.overage.cap_reached`

```jsonc
{
  "billing_period_start": "2026-05-01T00:00:00Z",
  "max_overage_eur": 50.00,
  "current_overage_eur": 50.00
}
```

## Idempotency

Consumers MUST be idempotent on `event_id` (existing pattern from UPD-013).

## Ordering

Per-tenant ordering is guaranteed via the `tenant_id` partition key. Cross-tenant ordering is not — and is not needed by any consumer.

## Schema evolution

`schema_version: 1` is the initial version. Forward-compatible additions land via additive payload fields. Breaking changes increment `schema_version` and consumers must dispatch on it.
