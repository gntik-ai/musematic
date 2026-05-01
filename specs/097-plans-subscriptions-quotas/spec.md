# Feature Specification: UPD-047 — Plans, Subscriptions, and Quotas (Super-Admin Configurable)

**Feature Branch**: `097-plans-subscriptions-quotas`
**Created**: 2026-05-01
**Status**: Draft
**Input**: User description: "UPD-047 — Plans, Subscriptions, and Quotas. Super-admin-configurable plan parameters with versioning. Subscriptions at workspace scope (Free/Pro in default tenant) or tenant scope (Enterprise). Quota enforcement at execution time with three modes: hard cap Free (HTTP 402), opt-in overage Pro (pause + authorize), no cap Enterprise. Active compute time as the unit of minutes. Three default plans seeded: free, pro, enterprise. Admin UIs at /admin/plans (versioned editing) and /admin/subscriptions (cross-tenant view). FR-706 through FR-722."

## Background and Motivation

The audit-pass platform tracks per-execution cost (UPD-027) and offers admin-level workspace-count limits (FR-025), but it has no formal commercial model: no plan catalogue, no per-tenant subscription, no plan-driven quota enforcement, no overage UX. The SaaS pass (constitution v2.0.0, principles SaaS-4 through SaaS-7 and SaaS-21 through SaaS-30) requires that commercial layer.

UPD-047 introduces three primitives:

1. **Plan** — a named tier (`free`, `pro`, `enterprise`) carrying a publishing history of versioned parameter sets (price, daily/monthly execution count, daily/monthly active compute minutes, max workspaces, max agents, max users, overage price, allowed model tier, trial length, quota period anchor).
2. **Subscription** — a binding between a billable scope and a specific plan version. The scope is the **workspace** for Free and Pro (default tenant) or the **tenant** for Enterprise (constitution rule SaaS-7 / SaaS-29).
3. **Quota** — a synchronous enforcement check that runs before every chargeable action (launch execution, create workspace, register agent). The enforcement mode depends on the plan tier: **hard cap** for Free (constitution rule SaaS-6, SaaS-25), **opt-in overage** for Pro (rule SaaS-24), **no cap** for Enterprise (rule SaaS-6).

The feature is super-admin-configurable end to end: every plan parameter lives in the database (no hardcoded prices or quotas), every plan change creates a new version, every existing subscription stays pinned to its version (rule SaaS-16, SaaS-22, SaaS-26 / AD-26). Stripe handles real billing through the `PaymentProvider` abstraction (UPD-052), but the `subscriptions` and `usage_records` tables are the source of truth for what each tenant is allowed to do RIGHT NOW.

This feature depends on UPD-046 (`tenants` table and `tenant_id` column on every tenant-scoped table); subscriptions and usage records are tenant-scoped from day one. It precedes UPD-052 (Stripe integration), which will populate `stripe_customer_id` and `stripe_subscription_id` and synchronise period boundaries.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Super admin publishes a new Pro plan version (Priority: P1)

The commercial team decides to raise the Pro plan price from 49 EUR/month to 59 EUR/month. Super admin edits the plan in `/admin/plans`, reviews the diff, and publishes a new version. Existing Pro subscribers stay at 49 EUR for the remainder of their billing period (and beyond, until they upgrade); new sign-ups land on 59 EUR.

**Why this priority**: Plan-parameter changes are the single most-common super-admin action in this domain. Without versioning that protects existing subscriptions from retroactive changes, the platform violates principle SaaS-16 ("Plan versioning is mandatory") and exposes the operator to chargeback risk.

**Independent Test**: Authenticated as super admin, edit `/admin/plans/pro/edit`, change `price_monthly` from 49 to 59, click "Publish new version". Verify (a) a new `plan_versions` row exists with version 2, (b) version 1 is marked deprecated for new subscriptions, (c) every existing Pro subscription still references version 1 (verified via SQL count), (d) the diff panel shows price 49→59 with no other changes, (e) an audit chain entry tagged with the super admin principal is recorded.

**Acceptance Scenarios**:

1. **Given** super admin is on `/admin/plans/pro/edit` showing the current published version's parameters, **When** any parameter is modified and "Publish new version" is clicked, **Then** a new `plan_versions` row is created with the next sequential version number, the prior version's `deprecated_at` is set, an audit chain entry is recorded with the diff, and the form returns to the read-only history view.
2. **Given** version 2 of Pro has been published, **When** a user signs up for Pro, **Then** the resulting subscription references `(plan_id=pro, plan_version=2)`.
3. **Given** an existing Pro subscriber on version 1, **When** the new version 2 is published, **Then** that subscription stays on version 1 for the remainder of the current billing period and across the next renewal unless the subscriber explicitly upgrades.
4. **Given** super admin opens the version-history view for the Pro plan, **When** the page renders, **Then** every published version is listed with its `published_at` timestamp, the diff against the immediately-prior version, the count of subscriptions still on that version, and a "Deprecate" action (which prevents new subscriptions on that version without affecting existing ones).

---

### User Story 2 — Free workspace hits the monthly execution quota and is hard-capped (Priority: P1)

A Free workspace has consumed its 100-execution monthly quota. The next launch attempt is refused immediately with a clear message and a one-click upgrade path. No partial execution is created.

**Why this priority**: Constitutional rule SaaS-6 / SaaS-13 / SaaS-25 — "hard cap for Free, never any overage". Without this enforcement, Free workspaces become a cost vector against the operator.

**Independent Test**: Pre-fill a Free workspace's monthly executions counter to 100 (the limit). Attempt to launch execution #101 via the existing launch endpoint. Receive HTTP 402 with a structured body containing `code=quota_exceeded`, `quota_name=executions_per_month`, `reset_at=<next-period-start>`, `upgrade_url=/upgrade`. Verify no `executions` row was created, no Kafka event published, and the UI surfaces an "Upgrade to Pro" call-to-action.

**Acceptance Scenarios**:

1. **Given** a Free workspace at its monthly execution cap, **When** the user attempts to launch a new execution, **Then** the response is HTTP 402 with the structured body including the failing quota name, the period reset timestamp, and the upgrade link; no execution row is created and no execution event is emitted.
2. **Given** a Free workspace is at any quota cap (executions/day, executions/month, minutes/day, minutes/month, max workspaces, max agents, max users), **When** the user attempts the corresponding action, **Then** the request is refused synchronously with HTTP 402 and the failing quota is named in the response.
3. **Given** the monthly billing period rolls over, **When** the period boundary passes, **Then** the workspace's monthly counters reset and the next attempt to launch an execution succeeds (subject to daily caps).
4. **Given** a Free workspace's plan version sets `allowed_model_tier=cheap_only`, **When** the user attempts an execution that would route to a premium model, **Then** the request is refused with a quota-tier mismatch (constitutional Critical Reminder: "Free plan execution time uses cheap-model-only routing").

---

### User Story 3 — Pro workspace exceeds minutes quota and authorises overage (Priority: P1)

A Pro workspace has consumed its 2400-minute monthly quota. The next execution does not run immediately — it is paused, the workspace admin receives a notification, and after explicit one-click authorisation the paused execution resumes and subsequent executions in the same billing period are billed at the configured overage rate.

**Why this priority**: Constitutional rule SaaS-6 / SaaS-24 — "hybrid for Pro: opt-in confirmation overage". This is the differentiator that lets Pro customers spike legitimately without ever being silently overbilled.

**Independent Test**: Pre-fill a Pro workspace's monthly minutes counter to 2400. Trigger a new execution. Verify (a) the execution row is created with status `paused_quota_exceeded` and produces no work, (b) a notification is delivered to workspace admins (not all members) via the audit-pass notification channels, (c) the workspace admin opens the authorisation page, sees a forecast of remaining-period spend at the current burn rate, and clicks "Authorize overage for this period" with an optional EUR cap, (d) an `overage_authorizations` row is created scoped to the current billing period, (e) the previously-paused execution resumes immediately, (f) a subsequent execution within the same period launches without re-prompting, (g) at the start of the next billing period a new authorisation is required.

**Acceptance Scenarios**:

1. **Given** a Pro workspace whose plan version permits overage and whose current usage equals the monthly minutes quota, **When** a new execution is requested, **Then** the request is accepted but the execution is created in a paused state, and a notification is delivered to workspace admins only.
2. **Given** the workspace admin opens the overage-authorisation surface, **When** the page renders, **Then** it displays current usage, the configured overage rate per minute, a forecast of total period spend at the current burn rate, and a one-click authorise action with an optional EUR cap.
3. **Given** the workspace admin clicks "Authorize overage" with or without an EUR cap, **When** the action is processed, **Then** an `overage_authorizations` row is recorded with the principal, timestamp, period scope, and optional cap; previously-paused executions resume; subsequent executions within the same period proceed without prompting.
4. **Given** two workspace admins click "Authorize overage" simultaneously, **When** the requests reach the server, **Then** exactly one authorisation row is recorded (idempotency on `(workspace_id, billing_period_start)`); the second admin sees a no-op confirmation rather than an error.
5. **Given** a Pro overage authorisation exists for the current period, **When** the next billing period begins, **Then** the authorisation is no longer in scope and the next overage requires a fresh authorisation.
6. **Given** an authorised overage is in effect with an EUR cap, **When** the cap is reached, **Then** new executions are paused again and a fresh authorisation prompt is sent to the workspace admin.

---

### User Story 4 — Enterprise workspace runs unlimited (Priority: P1)

A workspace inside an Enterprise tenant launches 10,000 executions in a day. Every quota check sees `0 = unlimited` for the tenant's plan version and short-circuits without enforcement. No 402 ever surfaces; no overage prompt ever appears.

**Why this priority**: Constitutional rule SaaS-6 / SaaS-30 — "Enterprise tenant subscriptions are tenant-scoped; every workspace inside inherits; quota = 0 means unlimited". This is the contractual posture for paid Enterprise customers; visible quota friction would break the value proposition.

**Independent Test**: Provision an Enterprise tenant whose tenant-level subscription points at a plan version with all quota fields set to zero. From a workspace inside that tenant, launch 10,000 executions over the course of a day. Verify (a) every quota check returns "OK" without consulting the usage counters, (b) no 402 is ever returned, (c) no overage notification is ever sent, (d) every workspace inside the tenant inherits the same subscription (no per-workspace subscription rows for Enterprise tenants).

**Acceptance Scenarios**:

1. **Given** an Enterprise tenant subscription whose plan version has all quota fields set to zero, **When** any chargeable action is requested, **Then** the quota check short-circuits with "OK" and the action proceeds.
2. **Given** an Enterprise tenant exists, **When** the system attempts to insert a workspace-scoped subscription within that tenant, **Then** the database constraint refuses the insert with a clear constraint-violation error.
3. **Given** a Free or Pro tenant exists (the default tenant), **When** the system attempts to insert a tenant-scoped subscription, **Then** the database constraint refuses the insert.
4. **Given** an Enterprise tenant has a custom contractual cap configured by super admin (e.g., 100,000 executions/month), **When** that cap is reached, **Then** the platform applies the documented contractual-cap policy hook (out of scope for parameter values here; the hook is super-admin-defined per Edge Cases).

---

### User Story 5 — Free workspace upgrades to Pro mid-month (Priority: P2)

A Free workspace user clicks "Upgrade to Pro" mid-month, supplies a payment method, sees a prorated cost preview, confirms, and immediately gains Pro quotas. Stripe handles proration; the local `subscriptions` row updates atomically with the new `plan_id`, `plan_version`, and current period boundaries.

**Why this priority**: The conversion path from Free to Pro is the primary commercial event for the SaaS pass. P2 because P1 stories cover the foundational "Pro tier enforcement works" — this story validates the upgrade transition mechanics.

**Independent Test**: As a Free workspace user, click "Upgrade to Pro" on `/workspaces/{id}/billing`. Confirm with a test payment method. Verify (a) the UI shows a prorated-cost preview computed against the current Stripe subscription, (b) on confirmation a Stripe subscription is created or updated, (c) the Stripe webhook (delivered through UPD-052) updates the local `subscriptions` row atomically with the new plan, plan version, and period boundaries, (d) Pro quotas immediately apply on the next chargeable action (no backfill of historical executions), (e) an audit chain entry is recorded.

**Acceptance Scenarios**:

1. **Given** a Free workspace user on the billing surface, **When** they click "Upgrade to Pro", **Then** a prorated-cost preview computed against the current period is displayed before confirmation.
2. **Given** the user confirms the upgrade, **When** the upgrade flow completes, **Then** the `subscriptions` row updates atomically (single transaction) to the new plan, version, and period boundaries; the workspace's quotas immediately reflect Pro limits; an audit chain entry is recorded.
3. **Given** the upgrade flow encounters an error during payment-method capture, **When** the error is detected, **Then** the local subscription remains on Free (no partial-state row), the user sees a clear error message, and no audit chain entry for upgrade is recorded.

---

### User Story 6 — Pro workspace schedules a downgrade to Free (Priority: P2)

A Pro workspace user clicks "Downgrade to Free". The downgrade is scheduled for the end of the current billing period (default behaviour) and the user receives a notification explaining that data exceeding Free limits will need to be archived. The downgrade can be cancelled at any time before the period ends.

**Why this priority**: The reverse of Story 5. P2 because P1 stories cover "the platform refuses Free actions correctly"; this story validates the downgrade transition.

**Independent Test**: As a Pro workspace user, click "Downgrade to Free" on `/workspaces/{id}/billing`. Confirm. Verify (a) the UI explains data implications (extra workspaces, extra agents, extra users will be flagged for cleanup), (b) the local `subscriptions` row enters status `cancellation_pending` with `cancel_at_period_end=true`, (c) at the period boundary the subscription transitions to Free; quotas tighten; data exceeding Free limits is flagged for the user to archive, (d) up until the period boundary, the user can click "Cancel scheduled downgrade" and the subscription reverts to active Pro.

**Acceptance Scenarios**:

1. **Given** a Pro workspace, **When** the user clicks "Downgrade to Free" and confirms, **Then** the subscription enters scheduled-cancellation state with the effective date pinned to the current period end.
2. **Given** a scheduled downgrade is pending, **When** the period boundary elapses, **Then** the subscription transitions to Free, quotas tighten, and any data exceeding Free limits is flagged in the UI for the workspace admin to archive (not deleted automatically).
3. **Given** a scheduled downgrade is pending, **When** the user cancels the downgrade before the period boundary, **Then** the subscription returns to active Pro state with no data effects.
4. **Given** a workspace transitions to Free with extra workspaces / agents / users above the Free quota, **When** the workspace admin views the cleanup banner, **Then** affected entities are listed with archive controls; nothing is permanently deleted by the platform without operator action.

---

### Edge Cases

- **Plan version edited concurrently with a subscription creation**: subscription creation transactions read the currently-published plan version under a shared lock; a plan-publish transaction acquires a stronger lock so the two cannot interleave to produce a subscription pinned to a half-published version.
- **Wall-clock skew between metering and quota check**: minute counters can lag the wall clock by up to a documented tolerance window (~30 seconds is the assumption); the quota check accounts for in-flight executions when computing projected usage so a borderline launch is refused rather than approved-then-overrun.
- **Concurrent overage authorisations from two admins**: idempotency is enforced by the `(workspace_id, billing_period_start)` uniqueness on `overage_authorizations`; the second insert finds the existing row and the response is a no-op success.
- **Plan version deprecated while existing subscriptions reference it**: deprecation prevents new subscriptions from being assigned the version but does not retroactively migrate existing subscriptions; renewal stays on the same pinned version (rule SaaS-21).
- **Stripe webhook arriving before the local subscription row exists**: webhook handler is idempotent on the Stripe event ID; if no local row exists yet, the handler retries (delivery is at-least-once). Eventual consistency converges within seconds.
- **Quota race at the period boundary**: an execution that starts at 23:59:59 with quota OK and finishes at 00:00:01 in the next period is counted in the period it finishes (single attribution, no double-count).
- **Plan with all zero quotas**: super admin can publish a plan with all quota fields set to zero (effectively unlimited). The UI surfaces a warning before publish so this is not done accidentally.
- **Custom contractual caps on Enterprise tenants**: super admin can register policy hooks for an Enterprise tenant that enforce contract-specific caps (e.g., 100,000 executions/month) without making them part of the plan parameter set. The plan version stays at zero (unlimited); the hook adds a per-tenant overlay.
- **Subscription scope mismatch with tenant kind**: a database trigger refuses any `subscriptions` insert/update where `scope_type='workspace'` is paired with an Enterprise tenant or `scope_type='tenant'` is paired with the default tenant.
- **Existing cost-attribution records before this feature**: the cost attribution flow from UPD-027 gains an additive `subscription_id` reference. Records written before this feature lack the reference; they are tagged retroactively to the workspace's current subscription on first read.
- **Trial subscriptions ending without a payment method**: when a trial elapses without a captured payment method, the subscription transitions to `past_due`; one notification is sent; if no payment method is added within the configured grace period, the workspace is downgraded to Free with the standard data-cleanup banner (rule SaaS-43).

## Requirements *(mandatory)*

### Functional Requirements

#### Plan catalogue and versioning

- **FR-001**: The platform MUST persist a `Plan` entity with: stable identifier, URL-safe slug, human display name, optional description, tier (`free`, `pro`, or `enterprise`), `is_public` flag (controls visibility on the marketing pricing page), `is_active` flag (controls whether new subscriptions can target it), allowed model tier (`cheap_only`, `standard`, `all`), and creation timestamp.
- **FR-002**: The platform MUST persist a `PlanVersion` entity with: stable identifier, parent plan reference, sequential version integer, monthly price, daily and monthly execution caps, daily and monthly active-compute-minute caps, max workspaces, max agents per workspace, max users per workspace, overage price per minute, trial length in days, quota period anchor (`calendar_month` or `subscription_anniversary`), free-form extras (JSON for forward-compatible parameters), publication timestamp, deprecation timestamp, and authoring super-admin reference. Uniqueness on `(plan_id, version)`.
- **FR-003**: The platform MUST treat any plan version field with value `0` as **unlimited** for that field. The quota enforcer MUST short-circuit with "OK" whenever the relevant cap is zero.
- **FR-004**: The platform MUST seed three default plans on first install: `free` (tier `free`, public, allowed model tier `cheap_only`), `pro` (tier `pro`, public, allowed model tier `all`), `enterprise` (tier `enterprise`, NOT public, allowed model tier `all`). Each receives an initial published version 1 with documented default parameters.
- **FR-005**: The platform MUST allow super admin to edit a plan and publish a new version through `/admin/plans/{slug}/edit`. Publishing creates a new `PlanVersion` row with the next sequential version, sets `deprecated_at` on the immediately prior version (preventing new subscriptions on it but not affecting existing subscriptions), and emits a hash-linked audit chain entry with the parameter diff and the super-admin principal.
- **FR-006**: The platform MUST refuse any operation that would mutate a published `PlanVersion` row in place. Publishing is an append-only operation. Deprecation flips a flag; it does not modify other fields.
- **FR-007**: The platform MUST surface a plan-version-history view at `/admin/plans/{slug}/history` showing every version with its publication timestamp, deprecation timestamp, parameter diff against the immediately-prior version, and count of subscriptions currently pinned to that version.
- **FR-008**: The platform MUST expose a public-pricing read-only API at `/api/v1/public/plans` returning every plan whose `is_public=true` along with its currently-published (non-deprecated) version's parameters. Used by the marketing pricing page; no authentication required.

#### Subscriptions

- **FR-009**: The platform MUST persist a `Subscription` entity with: stable identifier, tenant reference, scope type (`workspace` or `tenant`), scope identifier (the workspace ID or the tenant ID), plan reference, pinned plan version, status (`trial`, `active`, `past_due`, `cancellation_pending`, `canceled`, `suspended`), started timestamp, current period start and end, `cancel_at_period_end` flag, payment-method reference (added by UPD-052), Stripe customer and subscription IDs (populated by UPD-052), and audit fields. Uniqueness on `(scope_type, scope_id)` — at most one subscription per scope.
- **FR-010**: The platform MUST enforce a database trigger that refuses any subscription insert or update where `scope_type='workspace'` AND the tenant's kind is `enterprise`, OR where `scope_type='tenant'` AND the tenant's kind is `default`. Constitution rule SaaS-29 / SaaS-30 / AD-27.
- **FR-011**: The platform MUST resolve "the active subscription for a workspace" by: (a) if the workspace's tenant is Enterprise, return the tenant-scoped subscription; (b) otherwise, return the workspace-scoped subscription. Every chargeable code path MUST resolve through this single helper.
- **FR-012**: The platform MUST allow a workspace user to upgrade their workspace from Free to Pro through the billing surface. The upgrade flow displays a prorated-cost preview, captures or confirms a payment method, and on confirmation atomically updates the local subscription row to the new plan, version, and period boundaries.
- **FR-013**: The platform MUST allow a workspace user to schedule a downgrade from Pro to Free by setting `cancel_at_period_end=true` and entering status `cancellation_pending`. The downgrade takes effect at the period boundary; the user MAY cancel the scheduled downgrade up until that boundary.
- **FR-014**: The platform MUST allow super admin to suspend a subscription independently of tenant suspension — sets status `suspended` and blocks chargeable actions for the scope until reactivated.
- **FR-015**: The platform MUST emit a hash-linked audit chain entry tagged with the tenant identifier on every subscription state change (create, upgrade, downgrade-scheduled, downgrade-cancelled, downgrade-effective, suspend, reactivate, cancel).

#### Quota enforcement

- **FR-016**: The platform MUST run a synchronous quota check before every chargeable action: launching an execution, creating a workspace, registering an agent (active revision), inviting a user. The check MUST be deterministic and complete in a documented latency budget.
- **FR-017**: When a Free-tier subscription's plan version caps are exceeded, the platform MUST refuse the action with HTTP 402 carrying a structured body containing at minimum: `code=quota_exceeded`, the failing quota name, the period reset timestamp, and an upgrade URL. No partial state is created.
- **FR-018**: When a Pro-tier subscription's plan version caps are exceeded AND the plan version permits overage (`overage_price_per_minute > 0`), the platform MUST: (a) accept the action, (b) put the resulting work in a paused state distinguishable from completed/failed, (c) deliver a notification to workspace admins (and only to workspace admins, not all members) requesting overage authorisation, (d) NOT charge for the work until authorisation is recorded.
- **FR-019**: The platform MUST persist an `OverageAuthorization` entity with: tenant reference, workspace reference, subscription reference, billing period boundaries, authorising user, optional EUR cap (NULL means unlimited within the period), authorisation timestamp, and optional revocation. Uniqueness on `(workspace_id, billing_period_start)` so concurrent authorisations are idempotent.
- **FR-020**: When an overage authorisation is recorded for the active billing period, the platform MUST resume any paused work for that workspace immediately and allow subsequent chargeable actions in the same period without re-prompting until the optional EUR cap (if any) is reached.
- **FR-021**: When a billing period rolls over, the platform MUST treat the prior period's authorisation as expired; new overage events in the new period require a fresh authorisation.
- **FR-022**: When an Enterprise-tenant subscription's plan version has zero quotas, the platform MUST short-circuit the quota check with "OK" without consulting usage counters; quota friction is invisible to Enterprise users.
- **FR-023**: When a Free-tier subscription's plan version has `allowed_model_tier=cheap_only`, the platform MUST refuse any execution that would route to a premium model, returning the same HTTP 402 shape with a model-tier mismatch reason. Constitutional Critical Reminder: "Free plan execution time uses cheap-model-only routing".
- **FR-024**: The quota enforcement decision MUST be synchronous, fail-closed, and never permit a chargeable action when the subscription resolution itself fails (no subscription found, subscription suspended, etc.).

#### Usage metering and counters

- **FR-025**: The platform MUST aggregate post-execution usage events from the existing `execution.compute.*` event stream into per-`(subscription, period, metric)` counters in a `UsageRecord` entity. Metrics: `executions` (count) and `minutes` (decimal, computed from active compute time per AD-29 — the time the agent runtime pod actively processes, EXCLUDING approval-gate waits, attention-request waits, sandbox provisioning latency, and queue wait).
- **FR-026**: The metering pipeline MUST be idempotent on execution-event identifier; replaying the same Kafka event MUST NOT double-count.
- **FR-027**: The platform MUST flag overage usage on the same `UsageRecord` shape (`is_overage=true`) so finance and chargeback views can isolate the overage portion from the included portion.
- **FR-028**: Daily counters MUST reset at 00:00 UTC of each day. Monthly counters MUST reset on the documented period anchor — `calendar_month` (1st of the month) or `subscription_anniversary` (the day-of-month the subscription started). The plan version's `quota_period_anchor` field selects which.
- **FR-029**: The quota check MUST consider in-flight executions (executions whose start has been counted but whose duration is not yet finalised) when computing projected usage. The projected delta is the planned `projected_minutes` argument supplied by the caller (typically 1.0 minute as a conservative default, overridable by the execution dispatcher when a budget hint is available).

#### Cost attribution coupling

- **FR-030**: Cost attribution records owned by UPD-027 MUST gain an additive `subscription_id` reference so chargeback and margin analysis can join cost-per-execution against the active plan version. The reference is populated synchronously at execution commit (no batch backfill of historical records); pre-existing records are tagged retroactively on first read by the attribution-read path.
- **FR-031**: Every cost record carries `tenant_id` (already required by constitutional Critical Reminder) AND now also `subscription_id` so per-tenant margin can be computed by joining usage × cost × plan version.

#### Admin and user interfaces

- **FR-032**: The platform MUST expose `/admin/plans` (super admin only) listing every plan with its tier, public flag, current published version, and active-subscription count. Each row links to `/admin/plans/{slug}/edit` and `/admin/plans/{slug}/history`.
- **FR-033**: The platform MUST expose `/admin/subscriptions` (super admin only) listing every subscription cross-tenant, with filters for tenant, plan, status, payment status (post-UPD-052), and trial expiration. Each row links to a per-subscription detail view showing status timeline, current usage progress bars, plan version pinning, and payment history.
- **FR-034**: The platform MUST expose `/workspaces/{id}/billing` (workspace members) showing the workspace's current plan card with daily / monthly executions and minutes progress bars, an end-of-period usage forecast, recent invoices (UPD-052), payment method status, an overage-authorisation surface when applicable, and Upgrade / Downgrade / Cancel actions.
- **FR-035**: The platform MUST surface the overage-authorisation page at `/workspaces/{id}/billing/overage-authorize` for workspace admins. The page shows current usage, the configured overage rate, a forecast of total period spend at the current burn rate, and a one-click authorise action with an optional EUR cap.
- **FR-036**: The notification delivered when a Pro workspace requires overage authorisation MUST go ONLY to workspace admins (not workspace members at large). Constitution rule SaaS-24 implies workspace-admin-only notification scope.
- **FR-037**: The notification delivered when a Free workspace hits a hard cap MUST go to ALL workspace members (so the user who hit the cap sees the upgrade CTA inline) and the upgrade link MUST resolve to `/workspaces/{id}/billing/upgrade`.

#### Operator and CI guarantees

- **FR-038**: Editing a plan version's parameter set MUST refuse any save that does NOT also bump the version (no in-place edits to a published version). Validated at the service layer and at the database level (`updated_at` constraint check or trigger).
- **FR-039**: A CI check MUST verify that no production code path bypasses the quota enforcer for chargeable actions. Static analysis flags any direct call to the execution / agent / workspace / user creation primitives that does not first invoke the enforcer (allow-list maintained for non-chargeable internal flows).
- **FR-040**: The enterprise-scope subscription constraint MUST be enforced at THREE layers: the application service layer, the database trigger, and a CI test that asserts both layers reject the bad combination.

### Key Entities

- **Plan**: A named tier (`free`, `pro`, `enterprise`) plus presentation metadata (display name, description, public flag, allowed model tier). Owns a publishing history of `PlanVersion` rows.
- **PlanVersion**: An immutable parameter set published by super admin. Carries every quota and pricing field. Once published, a row may only be flipped to `deprecated`; no other fields change. Subscriptions reference a specific `(plan_id, version)`.
- **Subscription**: A binding between a billable scope (workspace or tenant) and a specific `PlanVersion`. Has a status state machine and current-period boundaries. Stripe identifiers are populated by UPD-052.
- **UsageRecord**: A per-`(subscription, period, metric)` rolling counter. Two metrics: `executions` (count) and `minutes` (active compute time, decimal). Carries an `is_overage` flag so the included portion and the overage portion are separately addressable.
- **OverageAuthorization**: A per-`(workspace, billing_period)` artefact recording that a workspace admin opted into overage for the current period. Carries the authorising principal, timestamp, optional EUR cap, and optional revocation.
- **Subscription Audit Entry**: A hash-linked audit chain entry recording every subscription state transition. Tagged with `tenant_id` and the acting principal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Super admin can publish a new plan version from `/admin/plans/{slug}/edit` and the new version is the basis of every subsequent new subscription within **60 seconds** of publication; existing subscriptions remain on their pinned version with **zero exceptions** detectable by SQL audit.
- **SC-002**: A Free workspace at quota cap receives HTTP 402 with the structured body within **a single request round-trip** (no retry, no async backoff). Across 1000 deliberately-overrun requests in a stress test, **100% return 402** and **zero create execution rows** that count toward usage.
- **SC-003**: A Pro workspace at quota cap receives an overage-authorisation prompt via the existing notification channel within **30 seconds** of the first overrun event; after authorisation, paused work resumes within **5 seconds**.
- **SC-004**: An Enterprise tenant with zero-cap plan version sustains **at least 10,000 executions per day per workspace** with the quota enforcer adding no measurable latency relative to a baseline non-quota-checked path (overhead < 1 ms p95).
- **SC-005**: Plan-version history surface displays the full diff between any two versions for a representative plan within **2 seconds** of page load.
- **SC-006**: Active-compute-time metering matches a hand-validated ground truth for a sample of 100 executions (varying durations from 5 seconds to 5 minutes) with **error below ±2%** per execution and **zero double-counting** under deliberate Kafka event replay.
- **SC-007**: Concurrent overage authorisations from two admins produce exactly one `OverageAuthorization` row in **100% of stress-test runs** (1000 simultaneous-click trials).
- **SC-008**: A workspace upgrading from Free to Pro mid-period sees its quota gates reflect Pro limits on the next chargeable action (verified within **a single request**) with no historical execution backfill.
- **SC-009**: A workspace scheduling a downgrade from Pro to Free can cancel the schedule at any time before the period end with **a single API call** that returns the subscription to active Pro state and emits one audit chain entry.
- **SC-010**: The database constraint preventing workspace-scoped subscriptions on Enterprise tenants (and vice versa) is verified by integration test against **100% of the cross-product of (tenant kind × scope type)**.

## Assumptions

- UPD-046 (`tenants` table; `tenant_id` columns and RLS on every tenant-scoped table) is fully landed before this feature begins. Subscriptions and usage records are tenant-scoped from day one.
- UPD-052 (Stripe + `PaymentProvider` abstraction) is the partner feature that populates `stripe_customer_id`, `stripe_subscription_id`, payment methods, invoices, and prorated billing webhooks. UPD-047 OWNS the `subscriptions` table and the local source-of-truth status; UPD-052 OWNS the Stripe sync.
- The audit chain hash already includes `tenant_id` (UPD-046 R7); subscription audit entries leverage that without further chain-format changes.
- The notification channels established in UPD-042 (in-product bell + email) are the delivery surfaces for overage-authorisation prompts and quota-hit alerts.
- The cost-attribution table from UPD-027 is extended additively with a nullable `subscription_id` column; legacy records are tagged on first read by the attribution-read path.
- Active compute time is the unit of "minutes" per constitutional rule SaaS-26 / AD-29: the time an agent runtime pod actively processes, excluding approval gate waits, attention request waits, sandbox provisioning latency, and queue wait time.
- Quota period anchor defaults to `calendar_month` for Free and `subscription_anniversary` for Pro, configurable per plan version. The default tenant's billing periods default to `calendar_month`; Enterprise contracts may use `subscription_anniversary`.
- The metering tolerance window (the maximum lag between a chargeable action completing and its `UsageRecord` reflecting the increment) is configurable; the default is 30 seconds and is documented in the operator runbook.
- Custom contractual caps for Enterprise tenants are out of scope for this feature's parameter set; super admin can register policy hooks to enforce them as a per-tenant overlay without modifying plan versions.
- The cleanup of data exceeding Free quotas after a downgrade is operator-initiated (the platform flags affected entities; it does NOT auto-delete). Aligns with constitution rule SaaS-43.
- The currency for plan pricing is EUR throughout the SaaS pass; multi-currency support is deferred.
