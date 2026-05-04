# Data Model: UPD-052 — Billing and Overage (PaymentProvider Abstraction + Stripe)

Tables introduced or extended by this feature. All new tables are PostgreSQL with timezone-aware timestamps and UUID primary keys (matching the existing platform conventions). Tenant-scoped tables use the standard RLS policy `tenant_isolation USING (tenant_id = current_setting('app.tenant_id', true)::uuid)` enforced via the `before_cursor_execute` listener.

Migration: **`114_billing_stripe`** (Alembic revision id, ≤32 chars).

## Tables

### `payment_methods`

Tenant-scoped (RLS). Mirrors a Stripe payment-method record locally for fast lookup on the billing pages.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, `gen_random_uuid()` | |
| `tenant_id` | UUID | NOT NULL, FK `tenants(id)` | RLS scope |
| `workspace_id` | UUID | NULL | `NULL` for tenant-level (Enterprise); set for default-tenant workspaces |
| `stripe_payment_method_id` | VARCHAR(64) | NOT NULL, UNIQUE | `pm_…` |
| `brand` | VARCHAR(32) | NULL | `visa`, `mastercard`, etc. |
| `last4` | VARCHAR(4) | NULL | last four digits of the card |
| `exp_month` | INTEGER | NULL | 1–12 |
| `exp_year` | INTEGER | NULL | 4-digit year |
| `is_default` | BOOLEAN | NOT NULL DEFAULT false | only one row per `(tenant_id, workspace_id)` SHOULD have `is_default = true` (enforced at service layer; no DB constraint because the flip is a two-step transition during card replacement) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` | |

**Indexes**:
- `ix_payment_methods_tenant_workspace` on `(tenant_id, workspace_id)`.
- `ix_payment_methods_default` partial on `(tenant_id, workspace_id) WHERE is_default = true`.

**RLS**:
```sql
ALTER TABLE payment_methods ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payment_methods
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

**FK from `subscriptions`** (additive — column already exists in UPD-047):
```sql
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_payment_method_fk
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
    DEFERRABLE INITIALLY DEFERRED;
```

The deferred constraint lets us run upgrade/downgrade in a single transaction that creates the payment_methods row, then attaches it to the subscription.

---

### `invoices`

Tenant-scoped (RLS). Local mirror of Stripe invoices. Drives the invoices page and feeds the cost-governance reports.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, `gen_random_uuid()` | |
| `tenant_id` | UUID | NOT NULL, FK `tenants(id)` | RLS scope |
| `subscription_id` | UUID | NOT NULL, FK `subscriptions(id)` | parent subscription |
| `stripe_invoice_id` | VARCHAR(64) | NOT NULL, UNIQUE | `in_…` |
| `invoice_number` | VARCHAR(64) | NULL | Stripe-assigned human-readable number |
| `amount_total` | DECIMAL(10, 2) | NOT NULL | EUR; tax included |
| `amount_subtotal` | DECIMAL(10, 2) | NOT NULL | EUR; pre-tax |
| `amount_tax` | DECIMAL(10, 2) | NOT NULL | EUR; Stripe Tax computed |
| `currency` | VARCHAR(3) | NOT NULL DEFAULT `'EUR'` | ISO 4217 |
| `status` | VARCHAR(32) | NOT NULL CHECK (`status IN ('draft','open','paid','void','uncollectible')`) | mirrors Stripe |
| `period_start` | TIMESTAMPTZ | NULL | invoice billing period start |
| `period_end` | TIMESTAMPTZ | NULL | invoice billing period end |
| `issued_at` | TIMESTAMPTZ | NULL | Stripe `created` timestamp |
| `paid_at` | TIMESTAMPTZ | NULL | populated by `invoice.payment_succeeded` |
| `pdf_url` | TEXT | NULL | Stripe-hosted PDF (`invoice_pdf` field) |
| `metadata_json` | JSONB | NOT NULL DEFAULT `'{}'::jsonb` | extra Stripe metadata, line items summary |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` | row insertion time |

**Indexes**:
- `ix_invoices_tenant_period` on `(tenant_id, period_end DESC)` — drives the invoices list.
- `ix_invoices_subscription` on `(subscription_id, period_end DESC)`.
- `ix_invoices_status_open` partial on `(tenant_id) WHERE status = 'open'` — drives the "outstanding invoices" admin view.

**RLS**:
```sql
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON invoices
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

---

### `processed_webhooks`

**Platform-level** (NOT tenant-scoped — see plan.md Complexity Tracking). Pure dedupe metadata; holds zero customer data.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `provider` | VARCHAR(32) | NOT NULL | `stripe` (forward-compatible for additional providers) |
| `event_id` | VARCHAR(128) | NOT NULL | Stripe `evt_…` |
| `event_type` | VARCHAR(64) | NOT NULL | e.g. `customer.subscription.created` |
| `processed_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` | |

**Primary Key**: `(provider, event_id)`.

**No RLS** — platform-level by design.

---

### `payment_failure_grace`

Tenant-scoped (RLS). Open record while a subscription is in the failed-payment grace window.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, `gen_random_uuid()` | |
| `tenant_id` | UUID | NOT NULL, FK `tenants(id)` | RLS scope |
| `subscription_id` | UUID | NOT NULL, FK `subscriptions(id)` | |
| `started_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` | grace window start |
| `grace_ends_at` | TIMESTAMPTZ | NOT NULL | `started_at + 7 days` |
| `reminders_sent` | INTEGER | NOT NULL DEFAULT 0 | 0/1/2/3 |
| `last_reminder_at` | TIMESTAMPTZ | NULL | timestamp of the most recent reminder |
| `resolved_at` | TIMESTAMPTZ | NULL | `NULL` while open |
| `resolution` | VARCHAR(32) | NULL CHECK (`resolution IN ('payment_recovered','downgraded_to_free','manually_resolved')`) | populated when `resolved_at` is set |

**Indexes**:
- `ix_payment_failure_grace_open` partial on `(grace_ends_at) WHERE resolved_at IS NULL` — drives the grace_monitor cron scan.
- `uq_payment_failure_grace_one_open_per_sub` partial unique on `(subscription_id) WHERE resolved_at IS NULL` — invariant: one open grace per subscription.

**RLS**:
```sql
ALTER TABLE payment_failure_grace ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payment_failure_grace
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

---

## State transitions

### `subscription.status` (UPD-047 column; UPD-052 drives the transitions)

```text
                    ┌────────────────┐
                    │   pending      │  (created locally, awaiting Stripe webhook)
                    └────────┬───────┘
                             │ customer.subscription.created
                             ▼
                    ┌────────────────┐
            ┌──────►│   active       │◄──────────────┐
            │       └────┬───────────┘               │
            │            │                           │
            │            │ invoice.payment_failed    │
            │            ▼                           │
            │       ┌────────────────┐               │
            │       │   past_due     │               │
            │       └────┬───────────┘               │
            │            │                           │
            │  payment_succeeded                     │ payment_method.attached
            │  (within grace)                        │ + manual reactivation
            └─◄──────────┘  payment.recovered        │
                         │  grace.resolved           │
                         │                           │
                         │ day-7 expiry              │
                         ▼                           │
                    ┌────────────────┐               │
                    │   suspended    │───────────────┘
                    │  (workspace    │
                    │   on Free)     │
                    └────────────────┘
                             │ user submits cancel
                             ▼
                    ┌──────────────────────┐
                    │ cancellation_pending │ (Stripe: cancel_at_period_end=true)
                    └────────┬─────────────┘
                             │ period_end
                             ▼
                    ┌────────────────┐
                    │   canceled     │ (workspace on Free)
                    └────────────────┘
```

### `payment_failure_grace.resolution`

```text
   open  ─────► payment_recovered   (Stripe retried successfully during grace)
        ─────► downgraded_to_free  (day-7 expiry; workspace dropped to Free)
        ─────► manually_resolved   (super-admin override via admin UI)
```

### `invoice.status` (mirrors Stripe)

```text
   draft ─► open ─► paid
                  └► void
                  └► uncollectible
```

---

## Touched existing tables

| Table | Change | Rationale |
|---|---|---|
| `subscriptions` | Add deferred FK on `payment_method_id → payment_methods(id)` | UPD-047 has the column; UPD-052 makes it referentially correct now that `payment_methods` exists. |
| `subscriptions` | None to columns; the `stripe_customer_id`, `stripe_subscription_id` columns already exist | UPD-052 is the first feature that *populates* them with real Stripe ids. |
| `plan_versions` | None | `stripe_price_id`, `stripe_overage_price_id` already exist from UPD-047. UPD-052 just reads them. |

No other table is touched. No column drops. No CHECK-constraint relaxations.

---

## Kafka envelopes

Topic: **`billing.events`** (new). Strimzi `KafkaTopic` CRD; partitions=3, replicas=3 prod / replicas=1 dev. Retention = 7 days (consumers must be caught up by then). Partition key = `tenant_id` (forces ordering per tenant).

| Event type | Payload (Pydantic v2) | Producer | Consumers |
|---|---|---|---|
| `billing.subscription.created` | `{subscription_id, tenant_id, workspace_id, plan_slug, stripe_customer_id, stripe_subscription_id, current_period_end, correlation_context}` | webhook `customer.subscription.created` handler | quotas BC, observability dashboards, audit chain |
| `billing.subscription.updated` | `{subscription_id, from_plan_slug, to_plan_slug, cancel_at_period_end, correlation_context}` | webhook `customer.subscription.updated` handler | quotas BC, observability |
| `billing.subscription.cancelled` | `{subscription_id, scheduled_at, effective_at, reason, correlation_context}` | API + webhook on `customer.subscription.deleted` | quotas BC, audit chain |
| `billing.invoice.paid` | `{invoice_id, subscription_id, amount_total, amount_tax, currency, paid_at, correlation_context}` | webhook `invoice.payment_succeeded` handler | analytics, audit chain |
| `billing.invoice.failed` | `{invoice_id, subscription_id, amount_total, currency, attempt_count, next_retry_at, correlation_context}` | webhook `invoice.payment_failed` handler | grace_monitor, notifications |
| `billing.payment_method.attached` | `{payment_method_id, tenant_id, workspace_id, brand, last4, correlation_context}` | webhook `payment_method.attached` handler | audit chain |
| `billing.payment_failure_grace.opened` | `{grace_id, subscription_id, grace_ends_at, correlation_context}` | grace service | notifications (day-1 reminder), audit chain |
| `billing.payment_failure_grace.resolved` | `{grace_id, subscription_id, resolution, correlation_context}` | grace service | notifications, audit chain, quotas BC (downgrade-to-Free trigger) |
| `billing.dispute.opened` | `{stripe_charge_id, tenant_id, subscription_id, amount, reason, correlation_context}` | webhook `charge.dispute.created` handler | super-admin notifications, audit chain |

---

## Vault paths (UPD-040 secret layout)

| Path | Format | Operator-only |
|---|---|---|
| `secret/data/musematic/{env}/billing/stripe/api-key` | `{ "key": "sk_test_..." }` (test) or `{ "key": "sk_live_..." }` (live) | Yes |
| `secret/data/musematic/{env}/billing/stripe/webhook-secret` | `{ "active": "whsec_...", "previous": "whsec_..." \| null }` | Yes; rotation playbook in `quickstart.md` |

The webhook-secret JSON is always parsed; `previous` may be `null` when no rotation is in progress.

---

## Redis key namespaces

| Pattern | Usage | TTL |
|---|---|---|
| `billing:webhook_lock:{event_id}` | Short-lived lock guarding webhook idempotency check | 60 s |
| `billing:webhook_sig_fail_count:{window}` | Sliding 15-min window counter for signature failures (alerting) | 900 s |
| `billing:portal_session_ratelimit:{customer_id}` | Customer Portal session-creation rate limit | 1 hour |

No persistent Redis state is required — these are all transient.
