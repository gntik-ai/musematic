# Implementation Plan: Multi-Channel Notifications

**Branch**: `077-multi-channel-notifications` | **Date**: 2026-04-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/077-multi-channel-notifications/spec.md`

## Summary

Extend the existing `notifications/` bounded context from a single per-user delivery method (in-app | email | webhook) to a multi-channel router with six destinations: in-app, email, webhook, Slack, Microsoft Teams, SMS. Add workspace-level outbound webhooks with HMAC-SHA-256 signing, idempotency keys, exponential-backoff retries, and a dead-letter queue. Per-user channel configurations gain quiet hours (IANA timezone) and alert-type filters. Backward compatibility for the existing `user_alert_settings.delivery_method` single-channel path is preserved via a forward-compatible adapter.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+, APScheduler 3.x, aiosmtplib (already in use by existing email deliverer), aioboto3 (existing). **Does NOT add new runtime libraries** — Slack and Teams target HTTPS incoming-webhook URLs handled by `httpx`; SMS uses an existing connector-style abstraction over a third-party provider via `httpx`.
**Storage**: PostgreSQL — 3 new tables (`notification_channel_configs`, `outbound_webhooks`, `webhook_deliveries`), 3 additive `DeliveryMethod` enum values (`slack`, `teams`, `sms`); Redis — 3 new key namespaces (`notifications:webhook_lease:{id}`, `notifications:webhook_dlq_depth`, `notifications:channel_verify:{token}` for verification challenges); Vault — 1 path family (`secret/data/notifications/webhook-secrets/{webhook_id}`, `secret/data/notifications/sms-providers/{deployment}`).
**Testing**: pytest + pytest-asyncio 8.x; integration tests against existing notifications harness; E2E test in the existing kind cluster (UPD-021) covering each channel adapter via mock receivers.
**Target Platform**: Linux server (control plane), Kubernetes deployment.
**Project Type**: Web service (FastAPI control plane bounded context).
**Performance Goals**: Webhook fan-out p95 ≤ 500 ms (event → first delivery attempt); first-attempt success rate ≥ 99 % to a healthy receiver (SC-002); replay batch of 100 dead-letter entries completes within 5 min (SC-005).
**Constraints**: At-least-once delivery contract; idempotency keys stable across retries; quiet-hours evaluation MUST use the user's IANA timezone (zoneinfo); HMAC SHA-256 over canonicalized JSON payload + timestamp header.
**Scale/Scope**: ≤ 6 channels per user (configurable cap); ≤ 50 outbound webhooks per workspace (configurable cap); dead-letter retention 30 days default.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | Extends existing `notifications/` BC; adds files alongside; modifies `service.py` and `router.py` additively. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `058_multi_channel_notifications.py` adds 3 tables + 3 additive enum values. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing `delivery_method` flow stays as a degenerate single-channel router path. Existing tests keep running unchanged. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New code follows the established `notifications/` layout: `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`. |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | `DeliveryMethod` gets `slack`, `teams`, `sms` appended via `ALTER TYPE ... ADD VALUE`. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | Existing `user_alert_settings` row remains authoritative for users who have not configured the new per-channel rows. New endpoints under `/api/v1/notifications/channels/*` and `/api/v1/notifications/webhooks/*` are additive (already reserved in constitution § REST Endpoint Prefixes). |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | New behavior gated by `FEATURE_MULTI_CHANNEL_NOTIFICATIONS` (default OFF for existing deployments). When OFF, alert routing falls back to legacy single-channel logic. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | Channel config CRUD (which holds emails, phone numbers) emits audit chain entries via `security_compliance/services/audit_chain_service.py`. |
| Rule 10 — vault for credentials | Constitution § Domain | ✅ Pass | HMAC signing secrets and SMS provider credentials resolve via `SecretProvider`. DB stores only vault refs. |
| Rule 17 — outbound webhooks HMAC + at-least-once + DLQ | Constitution § Domain | ✅ Pass | This rule is the operative contract for US2. Implemented exactly as specified: HMAC-SHA-256, idempotency keys, 3-retry exponential backoff over 24h, dead-letter. |
| Rule 18 — residency at query time | Constitution § Domain | ✅ Pass | Webhook URL registration consults the workspace's `data_residency_configs` to reject URLs in disallowed regions; runtime delivery re-checks the residency rule (in case configuration changes between registration and delivery). |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. No `print`. |
| Rule 23 — secrets never in logs | Constitution § Domain | ✅ Pass | Webhook signing secrets, SMS API keys, and chat connector tokens are never logged. CI gitleaks already covers source; structured-log fields are reviewed. |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Every channel config CRUD, every webhook CRUD, every secret rotation emits an audit chain entry. |
| Rule 34 — DLP on outbound | Constitution § Domain | ✅ Pass | Outbound payloads are evaluated through `privacy_compliance/services/dlp_service.py` (feature 076) before transmission. |
| Rule 39 — SecretProvider only | Constitution § Domain | ✅ Pass | All secret resolution via `common.secrets.secret_provider`. No `os.getenv` for `*_SECRET`/`*_API_KEY`/`*_TOKEN` outside SecretProvider. |
| Rule 45 — backend has UI | Constitution § Domain | ⚠️ Deferred | Per-user channel CRUD UI lands in UPD-042 (User Notification Center). Outbound-webhook admin UI lands in UPD-043 (Workspace Owner Workbench). Recorded in Complexity Tracking. |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All work inside `notifications/` BC. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL for relational state; Redis for short-lived leases and counters. No vectors, no FTS, no analytics. |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | Audit, DLP, residency, secret, and workspace lookups all happen via in-process service interfaces (Python function calls), never SQL into other BCs' tables. |
| Critical reminder #30 — audit chain durability | Constitution § Critical Reminders | ✅ Pass | Audit chain writes use the existing durable Kafka-backed mechanism; this feature is a producer only. |

## Project Structure

### Documentation (this feature)

```text
specs/077-multi-channel-notifications/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 (this command)
├── data-model.md        # Phase 1 (this command)
├── quickstart.md        # Phase 1 (this command)
├── contracts/           # Phase 1 (this command)
│   ├── channel-router.md
│   ├── outbound-webhooks.md
│   ├── channel-adapters.md
│   └── dead-letter.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 058_multi_channel_notifications.py             # NEW (3 tables, 3 additive enum values)
└── src/platform/
    ├── notifications/
    │   ├── models.py                                  # MODIFIED — add ChannelConfig, OutboundWebhook,
    │   │                                              #   WebhookDelivery; extend DeliveryMethod enum
    │   ├── schemas.py                                 # MODIFIED — add ChannelConfig*, OutboundWebhook*,
    │   │                                              #   QuietHours schemas
    │   ├── service.py                                 # MODIFIED — AlertService delegates to
    │   │                                              #   ChannelRouter (no rewrite of existing methods)
    │   ├── repository.py                              # MODIFIED — add channel/webhook/delivery queries
    │   ├── router.py                                  # MODIFIED — add channel CRUD + webhook CRUD routers
    │   ├── events.py                                  # MODIFIED — add channel.config.changed,
    │   │                                              #   webhook.registered, webhook.delivery.attempted,
    │   │                                              #   webhook.delivery.dead_lettered events
    │   ├── exceptions.py                              # MODIFIED — add ChannelVerificationError,
    │   │                                              #   ResidencyViolationError (re-raised),
    │   │                                              #   QuotaExceededError
    │   ├── routers/                                   # NEW SUBDIR
    │   │   ├── channels_router.py                     # NEW — /api/v1/notifications/channels/*
    │   │   ├── webhooks_router.py                     # NEW — /api/v1/notifications/webhooks/*
    │   │   └── deadletter_router.py                   # NEW — /api/v1/notifications/dead-letter/*
    │   ├── channel_router.py                          # NEW — fan-out, quiet hours, filter, severity floor
    │   ├── deliverers/                                # EXISTING + NEW siblings
    │   │   ├── email_deliverer.py                     # UNCHANGED (called from new ChannelRouter)
    │   │   ├── webhook_deliverer.py                   # MODIFIED — add HMAC + idempotency + canonical
    │   │   │                                          #   payload helpers; DLQ persistence
    │   │   ├── slack_deliverer.py                     # NEW
    │   │   ├── teams_deliverer.py                     # NEW
    │   │   └── sms_deliverer.py                       # NEW
    │   ├── workers/                                   # NEW SUBDIR
    │   │   ├── webhook_retry_worker.py                # NEW (APScheduler) — picks up next-due
    │   │   │                                          #   webhook_deliveries; replaces inline retry
    │   │   ├── deadletter_threshold_worker.py         # NEW — emits monitor.alert when DLQ depth > N
    │   │   └── channel_verification_worker.py         # NEW — expires unverified channel configs
    │   ├── canonical.py                               # NEW — payload canonicalisation + signing helpers
    │   ├── quiet_hours.py                             # NEW — IANA timezone evaluation
    │   ├── consumers/                                 # EXISTING (unchanged)
    │   └── dependencies.py                            # MODIFIED — wire ChannelRouter, new deliverers
    └── common/
        └── config.py                                  # MODIFIED — add NotificationsChannelSettings
                                                      #   subsection (caps, retention, defaults,
                                                      #   FEATURE_MULTI_CHANNEL_NOTIFICATIONS flag)

tests/control-plane/unit/notifications/
├── test_channel_router.py                             # NEW
├── test_quiet_hours.py                                # NEW
├── test_webhook_deliverer_hmac.py                     # NEW
├── test_webhook_retry_worker.py                       # NEW
├── test_dead_letter.py                                # NEW
└── test_slack_teams_sms_adapters.py                   # NEW

tests/control-plane/integration/notifications/
├── test_multi_channel_e2e.py                          # NEW
└── test_webhook_idempotency.py                        # NEW

tests/e2e/journeys/                                    # OPTIONAL — extends UPD-022 capstone
└── test_j10_multi_channel_notifications.py            # OPTIONAL (deferred to capstone wave)
```

**Structure Decision**: All work fits within the existing `notifications/` bounded context. The router-style submodule (`routers/`) and worker submodule (`workers/`) follow the conventions used by `connectors/` and `execution/`. No new bounded context is introduced. Frontend surfaces are deliberately out of scope for this feature and are routed to UPD-042 (per-user channel UI in user notification centre) and UPD-043 (workspace-admin webhook UI in workspace owner workbench).

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New `routers/` subpackage with three sub-routers | Clean separation of self-service (channel CRUD), workspace-admin (webhook CRUD), and operator (dead-letter) endpoints | A single fat `router.py` would conflate three distinct authorization scopes (rule 46 self-service vs. workspace-admin vs. operator); separation makes role gates obvious and reviewable. |
| New `channel_router.py` module instead of merging into `service.py` | The existing `AlertService` is already 438 lines and orchestrates dispatch; isolating fan-out + quiet-hours + filter logic into a dedicated module keeps `AlertService` thin and avoids rewriting it. | Rewriting `AlertService` would violate brownfield rule 1. |
| Three additive enum values (`slack`, `teams`, `sms`) | Required for first-class routing through the existing `DeliveryMethod` enum, which is referenced by `delivery_method` columns and FK-style relationships. | A separate `channel_kind` text column would split the model and confuse downstream consumers; additive enum is the conventional path (rule 6). |
| `FEATURE_MULTI_CHANNEL_NOTIFICATIONS` flag (default OFF) | Brownfield rule 8 — new behavior changing defaults requires a flag for gradual rollout. | Defaulting to ON would change behaviour for every existing deployment with no warning. |
| Rule 45 deferred to UPD-042/UPD-043 | Frontend work for self-service channel CRUD and admin webhook CRUD is large enough to justify its own UPD slot. The backend remains independently testable via the existing `/api/v1/me/*` test fixtures and admin curl-fixtures. | Building the frontend in this feature would balloon scope from 3 SP to 8+ SP and entangle two separate frontend workbench efforts. |
| `webhook_deliveries` retention as a separate persistence layer | Provides the audit trail and replay surface for dead-letter operations without requiring full event-sourcing rework. | Storing only the last attempt would lose the at-least-once audit trail and make replay non-deterministic. |

## Dependencies

- **UPD-009 / existing `notifications/` BC** — extended, not replaced.
- **Audit chain (UPD-024 / `security_compliance/services/audit_chain_service.py`)** — required by rule 9, 32. Audit emissions are fire-and-forget per critical reminder #30 (must be durable but not block delivery).
- **DLP pipeline (feature 076 / `privacy_compliance/services/dlp_service.py`)** — outbound payload sanitization (rule 34). Called via in-process service interface from `channel_router`.
- **Residency configuration (feature 076 / `privacy_compliance/services/residency_service.py`)** — webhook URL acceptance and runtime delivery checks (rule 18).
- **SecretProvider (`common.secrets.secret_provider`)** — webhook HMAC secrets and SMS provider credentials (rule 39, 10).
- **Workspace and user repositories (existing)** — for membership/role authorization on workspace webhook CRUD; for user timezone lookup on quiet-hours evaluation.
- **APScheduler (existing)** — webhook retry worker, dead-letter-depth alerting worker, channel verification expiration worker.

## Wave Placement

Wave 5 — after the notifications BC baseline (UPD-009) and after the audit chain (UPD-024) and DLP/residency (feature 076) are in place. Compatible with later waves; no downstream features need to wait for it.
