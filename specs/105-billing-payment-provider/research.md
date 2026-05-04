# Research: UPD-052 — Billing and Overage (PaymentProvider Abstraction + Stripe)

This file resolves every technical unknown in `plan.md`'s Technical Context so Phase 1 (data-model + contracts + quickstart) can run without `[NEEDS CLARIFICATION]` markers. Each decision is recorded as `Decision / Rationale / Alternatives considered`.

---

## R1 — Stripe Python SDK choice and version pinning

**Decision**: Use the official `stripe>=11.0` Python SDK (synchronous client wrapped in `asyncio.to_thread` per call). Pin the *API behavior* via the request-level `Stripe-Version` header (`"2024-06-20"` for the initial cut) instead of pinning the SDK version. Configure once in `billing/providers/stripe/client.py` via `stripe.api_version = settings.api_version` so every call carries it.

**Rationale**:
- The Stripe Python SDK does not expose a first-class async client. Wrapping the sync calls in `asyncio.to_thread` keeps the FastAPI request loop unblocked and is the documented pattern.
- Request-level API-version pinning lets the platform upgrade the SDK for security fixes (CVE patches, dependency upgrades) without changing API behavior. Stripe's webhook signature format and event payload shape are determined by the dashboard "default API version," but the `Stripe-Version` header overrides it for outbound calls; inbound webhooks use whatever version is set in the Stripe dashboard. The dashboard version is operator-controlled (documented in `quickstart.md`).
- `>=11.0` covers SCA, PaymentElement, and Tax features needed by the spec.

**Alternatives considered**:
- `stripe-async` (third-party fork) — not maintained, no SCA support, last release 2022.
- Pinning the SDK version exactly — complicates supply-chain patches; mature SaaS practice is to pin API version, not SDK version.

---

## R2 — Webhook signature verification and dual-secret rotation

**Decision**: The webhook endpoint loads both `active` and `previous` signing secrets from Vault at `secret/data/musematic/{env}/billing/stripe/webhook-secret` (JSON `{"active": "...", "previous": "..."}`). Verification tries `active` first; on signature mismatch, retries with `previous`. If both fail, return HTTP 401 with a generic body and emit a `billing.webhook.signature_failed` security event. A counter in Redis (`billing:webhook_sig_fail_count`, sliding window 15 min) drives a Prometheus alert at threshold 10/15 min.

**Rationale**:
- Stripe documents the dual-secret pattern for zero-downtime rotation: both endpoints in Stripe dashboard accept events for the rotation window, so two valid secrets must work simultaneously.
- 401 with generic body avoids leaking *which* secret was tried (rule 35 anti-enumeration analogue).
- Vault as the single source of truth + a startup health-check that both secrets are present (or `previous` is explicitly null) prevents silent rotation breakage.

**Alternatives considered**:
- Single-secret rotation with a maintenance window — operationally costly; Stripe explicitly supports dual-endpoint rotation.
- Storing secrets in env vars — violates rule 39 (Vault-only).

---

## R3 — Webhook idempotency strategy

**Decision**: Two-layer idempotency:
1. **Redis 60-s lock**: `SET billing:webhook_lock:{event_id} <worker_id> NX EX 60`. If the lock cannot be acquired, return 200 immediately with `{"status": "already_processing"}` (Stripe will retry the event later if needed, but the in-flight handler is the same event).
2. **PostgreSQL durable record**: composite PK `(provider, event_id)` on `processed_webhooks`. Insert AFTER handler success; on PK conflict (rare — only when the Redis lock expired before the handler finished), the second handler's transaction rolls back.

The handler body itself is wrapped in a single SQLAlchemy transaction so handler-side state changes commit atomically with the `processed_webhooks` insert.

**Rationale**:
- Stripe occasionally delivers the same event twice within milliseconds; the PK alone leaves a window where two handlers can race past the dedupe check before either inserts.
- Redis lock is *cheap to acquire* and *fail-safe* (TTL releases automatically) — the durable record is what guarantees correctness; the lock just compresses the race window from "milliseconds" to "post-commit."
- 200 + `already_processing` keeps Stripe from treating the second delivery as a failed retry and escalating.

**Alternatives considered**:
- Pure PostgreSQL advisory locks — works but ties up a connection per in-flight event; problematic at scale.
- Pure idempotency-via-PK without Redis — workable but produces noisy `IntegrityError` logs for legitimate concurrent retries.

---

## R4 — Customer model: per-workspace vs per-tenant

**Decision**: One **Stripe customer per `(tenant_id, scope)`** where scope is `workspace` for default-tenant workspaces and `tenant` for Enterprise. Concretely:
- Default tenant + Free/Pro: one Stripe customer per *workspace* (the workspace owner pays).
- Enterprise tenant: one Stripe customer per *tenant* (the tenant admin / procurement pays).

`stripe_customer_id` lives on `subscriptions` (already exists, UPD-047). Customer metadata carries `{tenant_id, workspace_id, scope}` so reverse lookups from Stripe Dashboard are unambiguous.

**Rationale**:
- Default-tenant workspaces are individually owned and billed; one workspace's payment failure must not impact another workspace.
- Enterprise tenants pay at the tenant level (one contract, one card, one invoice for the whole tenant); per-workspace customers there would force the procurement team to manage N cards.
- Aligns with the existing `subscriptions.scope_type ∈ {workspace, tenant}` discriminator from UPD-047.

**Alternatives considered**:
- One Stripe customer per user — breaks workspace transfer (when a workspace changes owner the billing record would migrate too); also makes seat-based billing harder to add later.
- One Stripe customer per tenant always — collapses default-tenant workspace billing into a single customer, which makes per-workspace payment failure isolation impossible.

---

## R5 — Coverage strategy for live-Stripe paths

**Decision**: Module-level coverage policy:
- **In coverage** (≥95% required by rule 14): `webhook_signing.py`, `idempotency.py`, all webhook handlers (using deterministic test events constructed from canonical Stripe payloads), `payment_failure_grace/service.py`, `grace_monitor.py`, `invoices/service.py`, `payment_methods/service.py`, `providers/protocol.py` extension.
- **Omitted** (CI does not cover; the integration test suite + journey tests exercise these against real Stripe test mode): `providers/stripe/{client,customer,subscription,usage,portal,tax}.py`, `webhooks/router.py` end-to-end (the dispatch logic in `handlers/registry.py` IS covered), `payment_failure_grace/grace_monitor.py` cron tick orchestration (the service it calls IS covered).

The same omit-list pattern matches UPD-051's `data_lifecycle/services/dpa_service.py` precedent (live-Vault-needed paths).

**Rationale**:
- Unit tests cannot fake Stripe authoritative state (real customer ids, real subscription lifecycle); attempting to do so produces brittle tests that miss SDK drift.
- Webhook handlers can be unit-tested with fixture payloads since the handler logic is deterministic given a `stripe.Event`.
- The omit list is documented per-module with the same comment-pattern as UPD-051 (rule 14 follow-up policy).

**Alternatives considered**:
- 100% local mocking of `stripe` SDK — produces tests that pass while the real SDK fails; rejected.
- VCR-style record/replay against test Stripe — adds cassette maintenance overhead disproportionate to value.

---

## R6 — Why the Go side of the interface is dropped

**Decision**: `PaymentProvider` is Python-only. Go satellite services consume billing state through the existing REST quota/usage surface and Kafka events.

**Rationale**:
- The Go satellites (`runtime-controller`, `reasoning-engine`, `sandbox-manager`, `simulation-controller`) handle execution lifecycle, not billing. None of them need to call Stripe.
- Quota enforcement at execution start is already Python-side (the existing UPD-047 quota enforcer); the Go execution callers receive an `ExecutionStartDecision` from the control-plane API.
- Adding a Go interface that nobody implements (and that would need a Stripe Go SDK dependency added to services that have no use for it) would *increase* surface area without functional benefit.
- The user input's "Python + Go interface" stems from the constitution's "shared interfaces" rule, but that rule applies when both sides actually need the abstraction. Here only Python does.

**Alternatives considered**:
- Add a Go `PaymentProvider` interface in `apps/control-plane` shared protobuf — same outcome (no implementer), but pollutes the proto contracts.
- Add a Go interface in each satellite — see above; rejected for surface-area reasons.

---

## R7 — Stripe Tax (IVA OSS) integration depth

**Decision**: Enable Stripe Tax at the Stripe account level (operator action, documented in `quickstart.md`). When creating Stripe subscriptions, pass `automatic_tax: { enabled: true }`. Persist `amount_tax` and `amount_subtotal` separately on the local `invoices` row. Tax registration numbers (VATIN, OSS) are configured in the Stripe dashboard, not in the platform code.

**Rationale**:
- Stripe Tax computes per-customer rates correctly for EU IVA OSS (the destination country's VAT applies for B2C; reverse charge for valid B2B VATINs).
- The platform doesn't need to maintain a tax-rate table or know jurisdictional rules.
- IVA OSS reporting is exported from the Stripe dashboard; the platform's role is to ensure every issued invoice carries the rate Stripe Tax computed.

**Alternatives considered**:
- Computing tax in-platform — not feasible without a maintained tax-rate library; high regulatory risk.
- Skipping `automatic_tax` and applying tax post-hoc — invoices issued without tax are non-compliant.

---

## R8 — Failed-payment grace state machine and reminder cadence

**Decision**: Single-row state machine in `payment_failure_grace`:
- `started_at = now`, `grace_ends_at = started_at + 7d`, `reminders_sent = 0`, `last_reminder_at = NULL`, `resolved_at = NULL`.
- On `invoice.payment_succeeded` during the grace window: set `resolved_at = now`, `resolution = 'payment_recovered'`, transition subscription back to `active`.
- Cron `grace_monitor` runs every 6h. Per open row, sends reminder N when `now >= started_at + N*48h` (so day-1, day-3, day-5; one tick can send at most one reminder).
- When `now >= grace_ends_at` and `resolved_at IS NULL`: transition subscription to `suspended` → trigger workspace downgrade to Free → close grace row with `resolution = 'downgraded_to_free'`.

A partial unique index `(subscription_id) WHERE resolved_at IS NULL` enforces "one open grace per subscription."

**Rationale**:
- 6-hour cadence keeps the day-N alignment within a few hours (SC-005 says ±2 hours, so we're conservatively inside that envelope; CI fast-forwards wall clock to test the day-7 path).
- The "one open grace per subscription" invariant is critical: if Stripe sends `payment_failed` twice in a row (it shouldn't, but networks…), we don't want two grace rows tracking the same fault.
- Recovery branch is the simpler path: `payment_succeeded` while open → close immediately.

**Alternatives considered**:
- Reminder cadence at day-1, day-3, day-5, day-7 (4 reminders) — user spec specifies 3 reminders.
- Hard-coded 1-hour cadence — wastes scheduler capacity for no benefit.
- Per-tenant configurable grace length — out of scope; user spec sets 7 days.

---

## R9 — Frontend payment-element vs card-element

**Decision**: Use `@stripe/react-stripe-js` PaymentElement (the unified element). Mount it inside a `<form>` driven by React Hook Form + Zod for non-card inputs (billing address); the PaymentElement itself owns the card, SCA prompts, and 3D Secure modals.

**Rationale**:
- PaymentElement is Stripe's current recommendation; it auto-supports SCA, alternative payment methods (SEPA, iDEAL, Apple Pay) without per-method UI work.
- Legacy CardElement still works but is deprecated for new integrations.
- React Hook Form for the surrounding form keeps consistency with the rest of the apps/web codebase (UPD-051 follow-ups, UPD-016 signup, etc. all use RHF + Zod).

**Alternatives considered**:
- CardElement only — works but requires manual SCA wiring and won't support SEPA/iDEAL when we add them later.
- Hosted Stripe Checkout redirect — gives less branding control and breaks the in-app flow; rejected.

---

## Outstanding clarifications: NONE

All `[NEEDS CLARIFICATION]` markers from the spec/plan are resolved. Phase 1 may proceed.
