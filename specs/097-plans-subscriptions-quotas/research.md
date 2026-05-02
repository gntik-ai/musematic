# Phase 0 — Research and Design Decisions

**Feature**: UPD-047 — Plans, Subscriptions, and Quotas
**Date**: 2026-05-02

This document resolves the open technical questions identified during planning. Each entry follows the format: **Decision** / **Rationale** / **Alternatives considered**.

## R1 — Default plan parameter values

**Decision**: Migration 103 seeds three plans plus their initial published version 1 with the parameter values listed below. These are starting points — super admin is expected to publish revised versions during commercial calibration.

| Parameter | `free` v1 | `pro` v1 | `enterprise` v1 |
|---|---|---|---|
| `price_monthly` (EUR) | 0 | 49 | 0 (custom contract) |
| `executions_per_day` | 50 | 500 | 0 (unlimited) |
| `executions_per_month` | 100 | 5000 | 0 (unlimited) |
| `minutes_per_day` | 30 | 240 | 0 (unlimited) |
| `minutes_per_month` | 100 | 2400 | 0 (unlimited) |
| `max_workspaces` | 1 | 5 | 0 (unlimited) |
| `max_agents_per_workspace` | 5 | 50 | 0 (unlimited) |
| `max_users_per_workspace` | 3 | 25 | 0 (unlimited) |
| `overage_price_per_minute` (EUR) | 0 | 0.10 | 0 |
| `trial_days` | 0 | 14 | 0 |
| `quota_period_anchor` | `calendar_month` | `subscription_anniversary` | `subscription_anniversary` |
| `allowed_model_tier` | `cheap_only` | `all` | `all` |

**Rationale**: Constitution rule SaaS-13 requires Free to be economically protected — `cheap_only` model tier plus modest day-and-month caps prevent abuse as a cost vector. Pro caps are calibrated against typical individual-developer usage (a Pro user running a few executions per hour over the workday stays well under the cap, leaving overage as a true safety valve). Enterprise's `0 = unlimited` is the constitutional default per SaaS-6 / SaaS-30. Trial days at 14 for Pro give a meaningful evaluation period without bleeding revenue.

**Alternatives considered**: (a) Higher Free limits (200 executions/month) — rejected because abuse-prevention modelling shows even one heavy abuser costs more than a marginal-user Pro upgrade earns. (b) Per-tenant Enterprise plans — rejected; one shared Enterprise plan version with custom contractual policy hooks (per Edge Case in spec) keeps the catalogue clean.

## R2 — Plan-version locking during subscription creation

**Decision**: Subscription-creation transactions execute `SELECT … FROM plan_versions WHERE plan_id = :plan_id AND version = :version FOR SHARE` to lock the chosen plan version row. The plan-publish transaction acquires `pg_advisory_xact_lock(<hash>)` on the plan ID; if any in-flight subscription-creation transaction holds a share lock on a plan_versions row for that plan, the publish blocks until that transaction commits or rolls back.

**Rationale**: PostgreSQL advisory locks at the plan level are cheap and don't block parallel reads of unrelated plans; row-level shared locks on the chosen `plan_versions` row are similarly cheap. The combination prevents two race conditions: (a) subscriber lands on a half-published version, (b) subscriber lands on the prior version after the new one was committed but before deprecation took effect — both are eliminated because the publish transaction acquires its lock before inserting the new row and updates `deprecated_at` atomically with the insert.

**Alternatives considered**: (a) Serializable isolation — works but causes serialization-failure retry storms under contention; (b) `SELECT … FOR UPDATE` instead of `FOR SHARE` — over-locks (subscription creation doesn't need exclusive access); (c) Optimistic concurrency with version checks — viable but more code; advisory locks are simpler and the contention regime is rare (publishes are infrequent).

## R3 — Quota check caching strategy

**Decision**: Two-tier cache. **Tier 1**: process-local TTL cache (`cachetools.TTLCache`, max 4096 entries, TTL 60 s) keyed on `(workspace_id, period_start)`. **Tier 2**: Redis with key pattern `quota:plan_version:{workspace_id}` (resolved plan version, TTL 60 s) and `quota:usage:{subscription_id}:{period_start}` (rolling counter snapshot, TTL 60 s). The QuotaEnforcer reads Tier 1 → Tier 2 → DB. On every `usage_records` increment, the metering job invalidates the Tier 2 key via Redis pub/sub; receivers evict their Tier 1 entries. The DB is authoritative on tie — at the start of each period rollover, both cache tiers are flushed for the affected subscription.

**Rationale**: Sub-millisecond hot-path lookups are required for SC-005 (Enterprise zero-cap overhead < 1 ms p95) and SC-002 (Free hard cap returned in a single round-trip). The 60 s TTL is short enough that even without invalidation a stale counter self-heals within a minute. The pub/sub invalidation keeps the cache coherent across instances during normal operation.

**Alternatives considered**: (a) Tier 1 only — drift across instances. (b) Tier 2 only — adds a Redis hop on every quota check. (c) Database query on every check — fails the latency budget. (d) Optimistic counters in Redis with periodic DB sync — risks losing counts on Redis failure; the DB-as-authoritative pattern eliminates that risk.

## R4 — Period boundary attribution semantics

**Decision**: Minutes are attributed to the billing period in which the `execution.compute.end` Kafka event is consumed. The execution that started at 23:59:59 UTC and ended at 00:00:01 UTC of the next day has its full duration counted in the new period. Single attribution; no proportional split. This is documented in the operator runbook and surfaced in the workspace billing UI as a footnote.

**Rationale**: Splitting a single execution across two periods creates accounting complexity (two `usage_records` rows per execution) and edge-case bugs (rounding, ordering). Attribution at end time is consistent with Lambda-style billing (the de-facto industry convention for active-compute-time minutes). The wall-clock skew is bounded by the metering tolerance window (~30 seconds), so the attribution is deterministic.

**Alternatives considered**: (a) Proportional split — adds complexity for negligible accounting fidelity; rejected. (b) Attribute to start period — biases against late finishers; rejected.

## R5 — Period-rollover scheduler frequency

**Decision**: APScheduler interval job runs every 60 seconds in the `scheduler` runtime profile. Selects `subscriptions WHERE current_period_end <= now() AND status NOT IN ('canceled', 'suspended')`, advances each row using `FOR UPDATE SKIP LOCKED` so concurrent scheduler instances cooperate without lock contention. Idempotent on `(subscription_id, current_period_end)`: an advance that finds the row already pointing at a future period is a no-op.

**Rationale**: 60-second granularity is sufficient — periods are billed in days/months, so an extra minute of pre-rollover usage in the prior period is negligible. `FOR UPDATE SKIP LOCKED` is the standard PostgreSQL pattern for cooperative work distribution across multiple scheduler instances (matches the existing pattern used by `cost_governance/jobs/anomaly_job.py`).

**Alternatives considered**: (a) Database trigger fired on each insert — adds write-path overhead and complicates testing. (b) On-demand rollover at first quota check post-boundary — adds latency to the affected request. (c) Higher frequency (10 seconds) — wasted scheduler cycles for no business benefit.

## R6 — Metering pipeline idempotency and reconciliation

**Decision**: The `MeteringJob` Kafka consumer aggregates `execution.compute.end` events into per-`(subscription_id, period_start, metric, is_overage)` `UsageRecord` rows. Idempotency is enforced by a separate `processed_event_ids` table keyed on the Kafka event ID; the consumer writes to that table and increments the `usage_records` counter in the same transaction. A daily reconciliation job at 02:00 UTC re-reads the prior 24 hours of `execution.compute.end` events and asserts that every event has a corresponding `processed_event_ids` row; mismatches surface as alerts via the existing observability pipeline.

**Rationale**: Constitutional rule SaaS-26 / AD-29 requires accurate active-compute-time metering; SC-006 requires < ±2% error and zero double-counting under deliberate replay. The `processed_event_ids` table makes the idempotency check trivially correct. Daily reconciliation catches any drift caused by Kafka redelivery edge cases or schema drift in the upstream event.

**Alternatives considered**: (a) Use `usage_records.UNIQUE` constraint without a separate `processed_event_ids` table — works for inserts but not for increment operations. (b) Probabilistic dedup (Bloom filter) — possible false negatives, bad for billing. (c) Skip reconciliation — but then a silent metering bug could go unnoticed for billing periods.

## R7 — PaymentProvider Protocol shape

**Decision**: The `PaymentProvider` Protocol exposes the following methods (each async):

```python
async def create_customer(workspace_id: UUID, email: str) -> str  # returns provider customer ID
async def attach_payment_method(customer_id: str, method_token: str) -> str  # returns method ID
async def create_subscription(customer_id: str, plan_external_id: str, trial_days: int) -> ProviderSubscription
async def update_subscription(provider_sub_id: str, plan_external_id: str, prorate: bool) -> ProviderSubscription
async def cancel_subscription(provider_sub_id: str, at_period_end: bool) -> ProviderSubscription
async def preview_proration(provider_sub_id: str, target_plan_external_id: str) -> ProrationPreview
async def report_usage(provider_sub_id: str, quantity: Decimal, idempotency_key: str) -> None
async def void_payment_method(customer_id: str, method_id: str) -> None
async def list_invoices(customer_id: str, limit: int) -> list[ProviderInvoice]
```

`StubPaymentProvider` returns deterministic responses (e.g., `preview_proration` returns a value computed by linear interpolation on the local plan price); `report_usage` is a no-op that logs the call. UPD-052 implements `StripePaymentProvider` against the same Protocol.

**Rationale**: The Protocol covers the exact subset of operations the business logic needs without leaking Stripe-specific concepts (e.g., Stripe's `Setup Intents` are abstracted into `attach_payment_method`). This satisfies constitutional rule SaaS-17 / AD-28 — bounded contexts call `payment_provider.x()`, never Stripe APIs directly. Future migration to Paddle or LemonSqueezy means a new Protocol implementation, not a business-logic rewrite.

**Alternatives considered**: (a) Thin pass-through (Stripe SDK as the abstraction) — leaks vendor concepts everywhere; rejected by the constitutional rule. (b) Richer Protocol with refunds, disputes, etc. — out of scope for UPD-047; UPD-052 will extend the Protocol when those features land.

## R8 — HTTP status code mapping for quota failures

**Decision**:

| Failure | HTTP | `code` |
|---|---|---|
| Free workspace at quota cap, no overage permitted | **402 Payment Required** | `quota_exceeded` |
| Pro workspace at cap with overage authorized but EUR cap reached | **402 Payment Required** | `overage_cap_exceeded` |
| Pro workspace at cap awaiting authorization (work paused) | **202 Accepted** with body `{status: "paused_quota_exceeded"}` | n/a |
| Subscription suspended | **403 Forbidden** | `subscription_suspended` |
| No active subscription | **403 Forbidden** | `no_active_subscription` |
| Free workspace requesting a premium model | **402 Payment Required** | `model_tier_not_allowed` |

**Rationale**: 402 ("Payment Required") is the canonical HTTP status for "this would cost money you have not authorized" — preserves the structured-body contract in spec FR-017. 202 with the paused-state body is the right shape for Pro's pause-then-authorize flow because the request was accepted but the work has not yet started. 403 is correct for "the subscription itself is in a state that disallows action".

**Alternatives considered**: (a) 429 (Too Many Requests) — wrong semantic; rate-limit retry implies the request will eventually succeed without user action. (b) 451 (Unavailable For Legal Reasons) — wrong semantic. (c) 403 for all quota failures — loses the "fix this with payment" affordance.

## R9 — Migration of existing default-tenant workspaces to Free subscriptions

**Decision**: Migration 103 contains a backfill step that inserts a `Subscription` row for every existing default-tenant workspace, bound to `(plan=free, version=1)`. The billing period is anchored at the calendar month containing the migration. The insert is `ON CONFLICT (scope_type, scope_id) DO NOTHING` so re-runs are idempotent. A small backfill report is emitted at migration end (count of inserted subscriptions, distribution by tenant).

**Rationale**: Without this backfill, every existing workspace would lack an active subscription, and the `QuotaEnforcer` would refuse every chargeable action with `code=no_active_subscription` — breaking every existing user. The Free assignment is the safe default; users who want Pro can upgrade through the standard flow.

**Alternatives considered**: (a) Backfill at first request — adds latency and complicates the enforcer (it would have to handle missing-subscription as a pre-creation case). (b) Backfill from `main.py` startup — viable but couples startup to a one-time data migration. The Alembic backfill is the cleanest place.

## R10 — Reconciliation between `usage_records` and `cost_attributions`

**Decision**: The two are peer time-series of related but distinct concerns. `cost_attributions` (UPD-027) records per-step model/compute/storage cost in cents; `usage_records` (this feature) records per-period executions and minutes for quota enforcement. The additive `cost_attributions.subscription_id` column lets the analytics layer join the two without coupling. There is NO ongoing reconciliation between counters and cost — they measure different things. The reconciliation job R6 covers metering correctness; cost-attribution correctness is owned by UPD-027's existing checks.

**Rationale**: Conflating the two would force every cost-write path to also increment usage counters (and vice versa), creating tight coupling. Keeping them separate with a join key (`subscription_id`) preserves bounded-context isolation per Core Principle IV.

**Alternatives considered**: (a) Single combined table — violates the constitutional bounded-context separation. (b) Live reconciliation between the two — unnecessary; they are independent measurements that happen to share a timeline.

## R11 — Notification delivery scope for quota events

**Decision**:

- **Free hard-cap hit**: notification delivered to **all workspace members**. This is the case where the user attempting the action sees the upgrade CTA inline; everyone in the workspace is aware that the workspace is at cap.
- **Pro overage authorization required**: notification delivered to **workspace admins only**. The financial decision belongs to the admins; non-admin members do not need to see the prompt.
- **Pro overage authorized**: notification delivered to **all workspace members** so they understand the workspace is now in billable-overage mode.
- **Pro overage cap reached (paused again)**: notification delivered to **workspace admins only**.
- **Subscription state changes (upgrade, downgrade-scheduled, period-renewed, etc.)**: notification delivered to the **workspace owner** plus **all workspace admins**.

**Rationale**: Constitution rule SaaS-24 implies workspace-admin-only notification scope for the overage decision. FR-036 / FR-037 in the spec encode this. The all-members scope for Free hard cap is a deliberate UX choice — every user who hits the cap should see the upgrade option without depending on an admin to relay it.

**Alternatives considered**: (a) All notifications go to all members — noisy and confuses non-admin users with finance prompts they cannot act on. (b) All notifications go to admins only — leaves non-admin users without the upgrade CTA when they hit a hard cap.

## R12 — Stripe customer-ID encryption

**Decision**: `subscriptions.stripe_customer_id` and `stripe_subscription_id` are stored as plain VARCHAR in PostgreSQL. They are NOT secrets — Stripe identifiers are reference values, not cryptographic material. The encryption that matters is at the transport layer (TLS to Stripe) and at the secret layer (the Stripe API key, which lives in Vault per UPD-040 + SaaS-35). Database-at-rest encryption is provided by the cluster-level disk encryption already in production.

**Rationale**: Stripe identifiers are treated as PII-adjacent reference data; the constitutional secret-management rules (SaaS-35) apply to the API key, not to the customer ID. Adding column-level encryption would create operational complexity (key rotation, query-side decryption) for no security benefit.

**Alternatives considered**: (a) Application-level column encryption — high cost, no benefit. (b) Tokenize the IDs locally — adds an indirection layer that obscures debug logs without improving security.

## Summary of decisions

All resolved. Zero `NEEDS CLARIFICATION` markers remain. The plan can proceed to Phase 1 (data model, contracts, quickstart).
