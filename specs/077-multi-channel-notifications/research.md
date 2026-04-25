# Research: Multi-Channel Notifications

**Feature**: 077-multi-channel-notifications
**Date**: 2026-04-25
**Phase**: 0 — Outline & Research

This document records the design decisions made before writing data-model.md and the contracts.

---

## D-001 — Extend `notifications/` BC vs. introduce a new BC

**Decision**: Extend the existing `notifications/` bounded context.

**Rationale**: The notifications BC already owns alert routing, retry policy, and the email + webhook deliverers. The constitution explicitly states that `notifications/` is "EXTENDED (not replaced) by UPD-028" (§ "New Bounded Contexts"). Introducing a parallel BC would split ownership of the alert lifecycle and break in-place patterns.

**Alternatives considered**:
- New `messaging/` BC: rejected — duplicates `notifications/` ownership; breaks rule 1 (no rewrites).
- Per-channel BCs (`notifications_email/`, `notifications_slack/`): rejected — violates BC granularity convention; multiplies routing complexity.

---

## D-002 — Single `DeliveryMethod` enum extended additively vs. new enum

**Decision**: Extend the existing `DeliveryMethod` enum (currently `in_app | email | webhook`) with three additive values: `slack`, `teams`, `sms`.

**Rationale**: Brownfield rule 6 mandates additive enum values when extending. The `delivery_method` column on `user_alert_settings` and `alert_delivery_outcomes` already keys off this enum; reusing it preserves continuity.

**Alternatives considered**:
- New `channel_kind` enum on the new tables and keep the legacy enum unchanged: rejected — splits the type model and confuses downstream consumers (e.g., the existing `AlertDeliveryOutcome.delivery_method` column would still need to express the new values).

---

## D-003 — One channel config table for ALL channels vs. per-channel tables

**Decision**: One unified `notification_channel_configs` table keyed by (`user_id`, `channel_type`, `target`).

**Rationale**: Channels share a common shape: target, signing-secret ref, enabled flag, alert-type filter, quiet hours. A single table keeps the channel router simple (one query → all eligible destinations) and makes per-user caps trivially enforceable. Channel-specific extensions (e.g., SMS severity floor) are stored as JSONB `extra` on the row.

**Alternatives considered**:
- Per-channel tables (`email_channels`, `slack_channels`, …): rejected — six joins on the hot path; quiet-hours logic gets duplicated.
- Polymorphic single-table inheritance: same shape, more complexity, no win.

---

## D-004 — Workspace-level outbound webhooks separate from user-level webhook channels

**Decision**: Two distinct concepts.
1. `notification_channel_configs` rows of type `webhook` for **per-user** personal webhook destinations (e.g., a developer's own monitoring endpoint).
2. `outbound_webhooks` for **workspace-level** integration endpoints (registered by workspace admins, subscribed to event types, used by external systems).

**Rationale**: They have different governance: per-user webhooks are self-service (rule 46) and limited in count and capability. Workspace webhooks have admin-level CRUD, broader event-type subscriptions, harder audit requirements, and dead-letter visibility for the entire workspace. Lifecycles differ; lumping them risks role-gate confusion.

**Alternatives considered**:
- One table with a workspace-vs-user discriminator: rejected — invites cross-scope leakage (rule 47) and complicates RBAC checks.

---

## D-005 — HMAC signing scheme for outbound webhooks

**Decision**: HMAC-SHA-256 over `f"{timestamp}.{canonical_payload}"`, sent in two HTTP headers:
- `X-Musematic-Signature: sha256=<hex>`
- `X-Musematic-Timestamp: <unix_seconds>`
Receivers verify by recomputing HMAC with the shared secret and rejecting deliveries older than a configurable replay window (default 5 minutes).

**Rationale**: Stripe/GitHub-style scheme; widely understood; trivial to verify with stdlib in any language; replay protection is built in via timestamp.

**Alternatives considered**:
- HMAC over body only (no timestamp): rejected — vulnerable to capture-and-replay.
- Asymmetric (Ed25519): rejected for v1 — receivers must hold a public key, not just a shared secret; adds key-distribution friction. Reserved for a future iteration.
- JWS (JSON Web Signature): rejected — heavier; receivers need a JOSE library.

**Canonicalisation**: JSON Canonicalization Scheme (JCS, RFC 8785) — sorted keys, no whitespace, UTF-8 NFC. The same canonical form is used for the signed payload and the audit log entry, ensuring deterministic verification.

---

## D-006 — Idempotency-key construction

**Decision**: `idempotency_key = uuid_v5(namespace=webhook.id, name=event.id)` — deterministic UUID per (webhook, event) pair so all retries of the same event share the key.

**Rationale**: Receivers can deduplicate on the key without coordination with the sender. Switching from per-attempt UUIDs to per-(webhook, event) UUID is what unlocks the at-least-once contract from a receiver's perspective.

**Alternatives considered**:
- Per-attempt UUID: rejected — defeats deduplication.
- Server-generated counter: rejected — requires shared counter, brittle under multi-instance dispatch.

---

## D-007 — Retry schedule and total window

**Decision**: Default backoff schedule `[60s, 300s, 1800s]` (3 retries, last attempt at 35 min after the original); maximum total retry window configurable per webhook up to 24 hours. After the schedule is exhausted (or the 24h budget) the delivery dead-letters.

**Rationale**: The constitution rule 17 calls for "3 retries over 24h" — interpreted as up-to-3 retries within the 24h budget. The default schedule gives 4 attempts (initial + 3 retries) and stops well within the 24h cap so that the cap is reserved for operators who legitimately want a longer window (e.g., maintenance windows in customer infrastructure).

**Alternatives considered**:
- Exponential to 24h capped at 4096s: rejected — produces inhumanly slow retry cadence and makes operator debugging painful.
- Linear schedule: rejected — wastes retry budget when receiver is hard-down.

---

## D-008 — Dead-letter queue is a SQL table, not a separate Kafka topic

**Decision**: Dead-letter entries persist in `webhook_deliveries` rows with `status='dead_letter'`. No separate Kafka topic. Listing, replay, and threshold-monitoring all operate on this table.

**Rationale**: Dead-lettering is rare; queryability matters more than throughput. Operators need to filter by destination, time window, and reason. Dead-letter entries are also needed for rule 32 audit visibility, which is naturally relational.

**Alternatives considered**:
- Kafka dead-letter topic: rejected — listing and filtering for a UI requires a separate index store; doubles infrastructure for no gain.
- Redis sorted set: rejected — not durable enough for a 30-day audit retention requirement.

---

## D-009 — Quiet hours timezone evaluation

**Decision**: Use Python's `zoneinfo` (stdlib, IANA-backed) to compare the current time in the user's configured timezone against the `[start, end]` window. If `end < start`, the window crosses midnight (e.g., 22:00–08:00) — handled explicitly. The user's timezone comes from the `users.timezone` column (existing); falls back to `UTC` if NULL.

**Rationale**: `zoneinfo` is stdlib (no new dependency), IANA-correct, DST-aware, and trivial to test. Reading the user's existing timezone column avoids a duplicate field.

**Alternatives considered**:
- Server UTC + offset: rejected — wrong across DST transitions.
- Per-channel timezone: rejected — confuses users; the user's profile timezone is the single source of truth.

---

## D-010 — Severity floor for SMS

**Decision**: SMS channel configurations carry an explicit `severity_floor` field (default `critical`). The channel router refuses to dispatch SMS for alerts below the floor. Per-deployment, an admin can lift the default to `high` for organisations that opt in.

**Rationale**: SMS is the most expensive and most disruptive channel; a hard severity floor prevents both runaway cost and user fatigue. Making it explicit per-channel allows future fine-grained policy (e.g., one user opts in to all alerts, another only on critical).

**Alternatives considered**:
- Hard-coded "critical only": rejected — too rigid; some oncall users want `high` too.
- No floor (rely on alert-type filter): rejected — the alert type doesn't always carry severity, and users would pay for unintended SMS.

---

## D-011 — Verification of new email / phone / chat targets

**Decision**:
- Email: tokenized link valid 24h, sent to the address (existing email-deliverer reuse).
- Phone: 6-digit code valid 10 min, sent via SMS provider.
- Slack/Teams: incoming-webhook URLs are not "verified" — instead, registration sends a one-time test message; the user confirms in the Slack/Teams channel that they received it.

**Rationale**: Matches existing platform conventions for accounts/email verification. Test-message confirmation for chat is standard practice (Stripe, GitHub, etc.).

**Alternatives considered**:
- OAuth app installations: deferred to a future iteration; v1 ships incoming-webhook URL flow because it requires no central app registration in customer organisations.

---

## D-012 — Channel-config CRUD authorization scope

**Decision**: `/api/v1/me/notifications/channels/*` for per-user CRUD (rule 46 — `current_user`-scoped); `/api/v1/notifications/webhooks/*` for workspace-admin CRUD (workspace-admin role gate); `/api/v1/notifications/dead-letter/*` for operator + workspace-admin (scoped to workspace ownership for non-platform admins).

**Rationale**: Mirrors the existing platform pattern. Self-service under `/api/v1/me/*`, workspace-scoped under workspace-admin endpoints, operator surfaces under platform-admin guard with workspace-scoping for cross-workspace listings.

**Note on constitution prefix list**: The constitution § REST Endpoint Prefixes already reserves `/api/v1/notifications/channels/*` and `/api/v1/notifications/webhooks/*`. We add an additional `/api/v1/me/notifications/channels/*` for self-service to comply with rule 46 (no `user_id` param on self-service endpoints).

**Alternatives considered**:
- Single endpoint set keyed by query parameter: rejected — risks rule-47 cross-scope leakage.

---

## D-013 — Backward compatibility with existing `user_alert_settings.delivery_method`

**Decision**: When `FEATURE_MULTI_CHANNEL_NOTIFICATIONS=false` (the default), the `AlertService` continues to read `user_alert_settings.delivery_method` and dispatch to the legacy single-channel path. When the flag flips to `true`, `AlertService` first looks for matching `notification_channel_configs` rows for the user; if any exist, the channel router fans out via them. If none exist, the legacy `user_alert_settings.delivery_method` is used as a single-channel fallback.

**Rationale**: Rule 8 (feature flags) and rule 7 (backwards compat) require existing single-channel users to keep working. The fallback to the legacy column means a user can flip the flag on at the deployment level without forcing every individual user to reconfigure.

**Alternatives considered**:
- Migrate the legacy `delivery_method` row to a `notification_channel_configs` row at flag-flip time: rejected — risky bulk migration, can be done lazily on next user touch.
- Drop the legacy column immediately: rejected — violates rule 1 (no rewrites) and rule 7 (backwards compat).

---

## D-014 — Workspace-admin webhook URL must be HTTPS in production

**Decision**: Webhook URLs must be HTTPS unless `FEATURE_ALLOW_HTTP_WEBHOOKS=true` (intended for local dev only). HTTP URLs are rejected at registration with a clear validation error. The flag is undocumented in production deployments and refuses to enable in `ENV=production`.

**Rationale**: Protects payloads (which may contain PII even after DLP redaction) from network observers, and prevents accidental misuse where a developer pastes an HTTP test endpoint.

**Alternatives considered**:
- Always require HTTPS, no flag: rejected — local dev needs an escape hatch.
- Allow HTTP with a warning: rejected — silent risk.

---

## D-015 — DLP (rule 34) and residency (rule 18) integration points

**Decision**: Two interception points in the channel router:
1. **Pre-send DLP**: For every outbound payload (any channel), call `dlp_service.scan_outbound(payload, workspace_id, user_id)`. If the workspace policy is `block`, abort the send. If `redact`, replace the matched fragments. The DLP event is logged regardless.
2. **Pre-send residency**: For webhook channels (per-user webhook + workspace outbound), check the destination URL's resolved region against `data_residency_configs.allowed_egress_regions`. Re-check at registration time (synchronously fail) and at delivery time (dead-letter with a residency reason).

**Rationale**: Catches both registration-time and delivery-time residency violations (configurations can change between registration and delivery). DLP is universal — applies to chat/email/SMS too because the same payload may carry PII.

**Alternatives considered**:
- DLP only at registration (skip per-delivery): rejected — payload contents change per alert; registration cannot anticipate them.
- Residency only at registration: rejected — config can change.

---

## D-016 — Audit chain emissions

**Decision**: Emit audit chain entries on:
- Channel config create / update / enable-disable / delete (rule 9 — PII operations on email and phone).
- Outbound webhook create / update / activate-deactivate / delete / signing-secret rotation (rule 32 — config changes).
- Dead-letter manual replay (operator action; for traceability of who replayed and why).

**Do not emit on**:
- Per-delivery successes (rule 33 — high-volume; analytics pipeline already records via `monitor.alerts` + new `notifications.delivery.attempted` event).
- Per-delivery transient failures (handled by analytics; only dead-letter writes get audit visibility).

**Rationale**: Audit chain is append-only and durable; per-delivery emissions would dwarf the chain. Audit-worthy events are state changes and operator interventions.

---

## D-017 — Webhook payload schema

**Decision**: Every outbound webhook delivery uses the existing `EventEnvelope` schema with three additional headers (`X-Musematic-Signature`, `X-Musematic-Timestamp`, `X-Musematic-Idempotency-Key`). The body is the canonicalised JSON form of the EventEnvelope.

**Rationale**: Existing internal event consumers already understand the envelope; external receivers benefit from a stable, documented schema. The envelope already carries correlation IDs, event type, timestamp — no need to invent a new outbound shape.

**Alternatives considered**:
- Slim per-event-type schemas: rejected — explodes documentation surface.
- Binary protobuf: rejected for v1 — JSON is universal; perf is not a constraint at notification volume.

---

## D-018 — Slack and Teams adapters: incoming webhooks vs. apps

**Decision**: v1 ships incoming-webhook URL support only. Slack/Teams app installations are deferred.

**Rationale**: Incoming webhooks require no central app registration in the customer organisation; users can self-service. Apps require platform-side registration and OAuth — significant additional scope. Most customers start with incoming webhooks and only graduate to apps for richer interactions (replies, threads, slash commands), which are not in scope here.

**Alternatives considered**:
- Apps in v1: deferred to v2.

---

## D-019 — SMS provider abstraction

**Decision**: Define a `SmsProvider` Protocol (Twilio-compatible interface: `send_sms(to, body, sender) -> SmsDeliveryResult`). v1 ships a Twilio adapter. Operators can swap by implementing the protocol.

**Rationale**: Twilio is the most common; protocol abstraction lets customers BYO if they have a provider relationship. Cost cap enforcement lives in the router, not the adapter, so all providers behave the same way.

**Alternatives considered**:
- Hardcoded to Twilio: rejected — locks customers in.
- Connector-style plug-in: deferred — more complex than the v1 need; can be lifted later.

---

## D-020 — Migration numbering

**Decision**: Migration `058_multi_channel_notifications.py`, sitting on top of `057_api_governance.py`. If features 074/075/076 land between this plan and implementation, this migration's `down_revision` will be rebased on the latest head before merge — standard brownfield-rebase practice.

**Rationale**: Migrations are linear; the next sequential number is the safest default.

---

## Open questions resolved

All `[NEEDS CLARIFICATION]` markers from the spec have been resolved with industry-standard defaults documented in this research:

- Backoff schedule: `[60s, 300s, 1800s]`, retry window up to 24h (D-007).
- Dead-letter retention: 30 days default (D-008 + spec assumptions).
- Verification mechanics: tokenized email link 24h, SMS 6-digit 10 min (D-011).
- Per-user channel cap: configurable, default 6 (1 each); per-workspace webhook cap: configurable, default 50 (D-003 implication).
- Severity floor for SMS: critical by default (D-010).
- HMAC scheme: SHA-256 over `timestamp.payload` with replay protection (D-005).
- Canonicalization: JCS (RFC 8785) (D-005).
- Idempotency key: deterministic UUID v5 (D-006).
