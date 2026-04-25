# Tasks: Multi-Channel Notifications

**Feature**: 077-multi-channel-notifications
**Branch**: `077-multi-channel-notifications`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

User stories (from spec.md):
- **US1 (P1)** — Per-user multi-channel routing with quiet hours
- **US2 (P1)** — Workspace outbound webhooks (HMAC + at-least-once + DLQ)
- **US3 (P2)** — Slack channel
- **US4 (P2)** — Microsoft Teams channel
- **US5 (P2)** — Operator dead-letter inspection and replay
- **US6 (P3)** — SMS for critical-only alerts

Each user story is independently testable as described in spec.md.

---

## Phase 1: Setup

- [X] T001 Create new submodule directories under `apps/control-plane/src/platform/notifications/`: `routers/`, `workers/`; add empty `__init__.py` to each
- [X] T002 [P] Add `NotificationsChannelSettings` extension fields (`multi_channel_enabled`, `webhook_default_backoff_seconds`, `webhook_max_retry_window_seconds`, `webhook_replay_window_seconds`, `channels_per_user_max`, `webhooks_per_workspace_max`, `dead_letter_retention_days`, `dead_letter_warning_threshold`, `sms_default_severity_floor`, `sms_provider`, `sms_workspace_monthly_cost_cap_eur`, `allow_http_webhooks`, `quiet_hours_default_severity_bypass`) to `apps/control-plane/src/platform/common/config.py` `NotificationsSettings`; default `multi_channel_enabled=False`
- [X] T003 [P] Wire `FEATURE_MULTI_CHANNEL_NOTIFICATIONS` and `FEATURE_ALLOW_HTTP_WEBHOOKS` env-var bootstrap in `apps/control-plane/src/platform/common/config.py`; refuse to enable `allow_http_webhooks` when `ENV=production`

## Phase 2: Foundational (blocks every user story)

- [X] T004 Create Alembic migration `apps/control-plane/migrations/versions/058_multi_channel_notifications.py` that: (a) `ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'slack'/'teams'/'sms'`; (b) creates `notification_channel_configs`, `outbound_webhooks`, `webhook_deliveries` per data-model.md; (c) creates indexes (`idx_channel_configs_user_enabled`, `idx_channel_configs_user_type_active` partial WHERE enabled AND verified_at IS NOT NULL, `idx_outbound_webhooks_workspace_active`, `idx_webhook_deliveries_status_next_attempt`, `idx_webhook_deliveries_workspace_dlq` partial WHERE status='dead_letter`); chained on top of current head (rebase at merge time)
- [X] T005 [P] Add SQLAlchemy models `NotificationChannelConfig`, `OutboundWebhook`, `WebhookDelivery` to `apps/control-plane/src/platform/notifications/models.py` (preserving existing `UserAlertSettings`, `UserAlert`, `AlertDeliveryOutcome`); extend `DeliveryMethod` StrEnum with `slack`, `teams`, `sms`
- [X] T006 [P] Add Pydantic request/response schemas to `apps/control-plane/src/platform/notifications/schemas.py`: `ChannelConfigCreate`, `ChannelConfigUpdate`, `ChannelConfigRead`, `QuietHoursConfig`, `OutboundWebhookCreate`, `OutboundWebhookUpdate`, `OutboundWebhookRead`, `OutboundWebhookCreateResponse` (one-time secret), `WebhookDeliveryRead`, `DeadLetterListItem`, `DeadLetterReplayRequest`, `DeadLetterResolveRequest`
- [X] T007 [P] Add domain exceptions to `apps/control-plane/src/platform/notifications/exceptions.py`: `ChannelVerificationError`, `ChannelNotFoundError`, `WebhookNotFoundError`, `WebhookInactiveError`, `ResidencyViolationError`, `DlpBlockedError`, `QuotaExceededError`, `InvalidWebhookUrlError`, `DeadLetterNotReplayableError`
- [X] T008 Extend `apps/control-plane/src/platform/notifications/repository.py` with: `list_enabled_channel_configs(user_id)`, `create_channel_config`, `update_channel_config`, `delete_channel_config`, `get_channel_config_by_token_hash`, `list_outbound_webhooks(workspace_id)`, `create_outbound_webhook`, `update_outbound_webhook`, `get_outbound_webhook`, `count_active_webhooks(workspace_id)`, `count_user_channels(user_id, channel_type)`, `insert_delivery`, `list_due_deliveries(now, limit)`, `update_delivery_status`, `list_dead_letters(workspace_id, filters)`, `aggregate_dead_letter_depth_by_workspace`, `delete_dead_letter_older_than(cutoff)`
- [X] T009 [P] Create payload canonicalisation helpers in `apps/control-plane/src/platform/notifications/canonical.py`: `canonicalise_payload(envelope) -> bytes` (JCS-compatible: sorted keys, no whitespace, UTF-8 NFC), `build_signature_headers(*, webhook_id, payload, secret, idempotency_key, platform_version) -> dict[str, str]` returning `X-Musematic-Signature`/`X-Musematic-Timestamp`/`X-Musematic-Idempotency-Key`/`Content-Type`/`User-Agent`, `derive_idempotency_key(webhook_id, event_id) -> UUID` using `uuid.uuid5(NAMESPACE, f"{webhook_id}:{event_id}")`
- [X] T010 [P] Create quiet-hours evaluator in `apps/control-plane/src/platform/notifications/quiet_hours.py`: `in_quiet_hours(now_utc, qh, *, severity, bypass_severity) -> bool` using `zoneinfo.ZoneInfo`; handle midnight-crossing windows; return False on `severity >= bypass_severity`
- [X] T011 Create `apps/control-plane/src/platform/notifications/channel_router.py` skeleton with `ChannelRouter.__init__` (deps: repo, accounts_repo, workspaces_service, dlp_service, residency_service, secrets, audit_chain, producer, settings, deliverers); `route(alert, recipient, *, workspace_id, severity)` and `route_workspace_event(envelope, workspace_id)` method stubs that raise `NotImplementedError` (filled in subsequent phases)
- [X] T012 [P] Add channel-router-related events to `apps/control-plane/src/platform/notifications/events.py`: `ChannelConfigChangedPayload`, `WebhookRegisteredPayload`, `WebhookDeactivatedPayload`, `WebhookSecretRotatedPayload`, `DeliveryAttemptedPayload`, `DeliveryDeadLetteredPayload`, `DlqDepthThresholdReachedPayload`; publishers reuse `monitor.alerts` topic
- [X] T013 Wire dependency-injection providers in `apps/control-plane/src/platform/notifications/dependencies.py`: `get_channel_router`, `get_audit_chain_service`, `get_dlp_service`, `get_residency_service`, `get_secret_provider`, `get_deliverer_registry`; ensure all consumers (existing AlertService and new routers) resolve via DI
- [X] T014 Modify `apps/control-plane/src/platform/notifications/service.py` `_dispatch_for_settings`: when `settings.notifications.multi_channel_enabled` is True, delegate to `ChannelRouter.route(alert, user, workspace_id=workspace_id, severity=alert.urgency)`; otherwise keep the existing legacy path verbatim (rule 7 — backwards compat). Inject `ChannelRouter` via constructor; preserve existing call signatures and existing tests

---

## Phase 3: User Story 1 — Per-user multi-channel routing with quiet hours (P1) 🎯 MVP

**Story goal**: Users register email + in-app channels with quiet hours and alert-type filters; alerts route through the channel router honouring those rules.

**Independent test**: Register an email channel with quiet hours 22:00–08:00 (Europe/Madrid) and an alert-type filter; trigger a non-critical alert inside the window (no email) and outside the window (email arrives); trigger a critical alert inside the window (email arrives — bypass).

- [X] T015 [P] [US1] Implement `quiet_hours.in_quiet_hours` unit tests in `tests/control-plane/unit/notifications/test_quiet_hours.py` covering: simple window, midnight-crossing window, DST spring-forward (Europe/Madrid 2026-03-29), DST fall-back (Europe/Madrid 2026-10-25), critical bypass, non-IANA timezone error
- [X] T016 [US1] Fill `ChannelRouter.route` per `contracts/channel-router.md` algorithm: read enabled+verified configs, evaluate alert-type filter and severity floor, run quiet-hours, call DLP `scan_outbound`, dispatch via deliverer registry, persist `AlertDeliveryOutcome`, emit `notifications.delivery.attempted`; backwards-compat fallback paths (no rows + flag off → legacy; no rows + flag on → legacy as single channel; ≥1 rows → ignore legacy)
- [X] T017 [US1] Modify `apps/control-plane/src/platform/notifications/deliverers/email_deliverer.py` to accept a `ChannelConfig` instead of an SMTP-settings dict (additive overload, keep legacy signature); add HTML/text format selection from `config.extra.email_format`; preserve existing tests
- [X] T018 [US1] Implement self-service channel CRUD router at `apps/control-plane/src/platform/notifications/routers/channels_router.py` with `/api/v1/me/notifications/channels` GET/POST, `/{id}` PATCH/DELETE, `/{id}/verify` POST, `/{id}/resend-verification` POST; enforce rule 46 (no `user_id` parameter); 403 on cross-user access without information leakage; per-user channel cap from settings; mount on app router
- [X] T019 [US1] Implement email verification dispatch path in `apps/control-plane/src/platform/notifications/service.py` (or a new `verification_service.py`): SHA-256 hash 32-byte URL-safe token, store hash on row, set `verification_expires_at = now + 24h`, send tokenized link via existing email deliverer; `verify(channel_id, token)` lookup by `Sha256(token)`, set `verified_at`, clear hash
- [X] T020 [US1] Create `apps/control-plane/src/platform/notifications/workers/channel_verification_worker.py` (APScheduler) that archives `notification_channel_configs` rows where `verified_at IS NULL AND verification_expires_at < now()`; runs hourly; emits `notifications.channel.config.changed` with `reason=verification_expired`
- [X] T021 [US1] Wire audit-chain emissions in `routers/channels_router.py` for create/update/enable-disable/delete: call `audit_chain_service.append({event:"notifications.channel.config.changed", actor, subject, scope, diff, occurred_at})` (rule 9 — PII operations on email/phone targets)
- [X] T022 [US1] Add unit tests `tests/control-plane/unit/notifications/test_channel_router.py` covering CR1–CR12 from `contracts/channel-router.md` (fan-out, disable mid-call, midnight-cross + DST, critical bypass, alert-type filter, severity floor, DLP block + redact, residency violation on webhook, flag off legacy path, flag on no rows fallback, flag on with rows ignores legacy)
- [X] T023 [US1] Add integration test `tests/control-plane/integration/notifications/test_multi_channel_e2e.py::test_us1_email_channel_with_quiet_hours` exercising verification flow + quiet-hours + critical bypass + filter end-to-end against Postgres + Redis fixtures

**Checkpoint**: US1 deliverable. Email + in-app routing through the new ChannelRouter works for users who configure per-channel rows; backwards-compat preserved for existing users.

---

## Phase 4: User Story 2 — Workspace outbound webhooks with HMAC + at-least-once + DLQ (P1)

**Story goal**: Workspace admins register HTTPS outbound webhooks with HMAC-SHA-256 signing; events fan out with stable idempotency keys; failures retry on a configured exponential backoff; permanently failed deliveries dead-letter.

**Independent test**: Register a webhook to a local receiver; trigger 5 events with one event repeated; verify (1) every event arrives at least once, (2) HMAC verifies with the shared secret, (3) duplicate event reuses idempotency key, (4) 5xx retries follow backoff, (5) 4xx permanent dead-letters immediately.

- [X] T024 [P] [US2] Add unit tests `tests/control-plane/unit/notifications/test_webhook_deliverer_hmac.py` covering OWH1–OWH14 contract: registration response carries one-time secret, HTTP rejected, residency rejected at registration, HMAC verifiable, idempotency key stable across retries, 503/503/200 sequence, 4xx permanent dead-letter, 429 with Retry-After, DLP block, deactivate-mid-retry, secret rotation does not echo, retry window exceeded, Redis lease prevents double-dispatch, receiver-side verification snippet round-trip
- [X] T025 [US2] Modify `apps/control-plane/src/platform/notifications/deliverers/webhook_deliverer.py` to: build canonical body via `canonical.canonicalise_payload`; add HMAC-SHA-256 headers via `canonical.build_signature_headers`; classify HTTP outcomes per `contracts/outbound-webhooks.md` failure-classification table (2xx success; 408/429/5xx transient; other 4xx permanent; honour `Retry-After`; redirect-loop detection up to 3 hops); 10s default timeout
- [X] T026 [US2] Implement webhook registration helper in `apps/control-plane/src/platform/notifications/service.py` (or new `webhooks_service.py`): generate 32-byte base64 HMAC secret, write to Vault path `secret/data/notifications/webhook-secrets/{webhook_id}` via `SecretProvider`, persist row with `signing_secret_ref`, return secret in `OutboundWebhookCreateResponse` exactly once; rotate-secret endpoint never echoes new secret in response (rule 44)
- [X] T027 [US2] Implement HTTPS-only validation + residency check at registration in webhook service: reject HTTP unless `allow_http_webhooks=True` and `ENV != "production"`; resolve URL region via `residency_service.resolve_region_for_url(url)`; reject when `not residency_service.check_egress(workspace_id, region)`; raise `InvalidWebhookUrlError` / `ResidencyViolationError` with clear messages
- [X] T028 [US2] Implement workspace-admin webhook router at `apps/control-plane/src/platform/notifications/routers/webhooks_router.py` with endpoints from `contracts/outbound-webhooks.md`: POST `/api/v1/notifications/webhooks`, GET (list), GET `/{id}`, PATCH `/{id}`, POST `/{id}/rotate-secret`, DELETE `/{id}` (soft, hard requires superadmin + 2PA), POST `/{id}/test`; enforce workspace_admin role gate; per-workspace webhook cap from settings; mount on app router
- [X] T029 [US2] Fill `ChannelRouter.route_workspace_event(envelope, workspace_id)`: list active webhooks subscribed to `envelope.event_type`; for each call DLP `scan_outbound` (rule 34) and residency check (rule 18); INSERT `webhook_deliveries` row with deterministic `idempotency_key`; queue first attempt via direct dispatch + status='pending'/'delivering' transition with Redis lease
- [X] T030 [US2] Create `apps/control-plane/src/platform/notifications/workers/webhook_retry_worker.py` (APScheduler, 30s tick): query `repo.list_due_deliveries(now, limit=200)`; acquire Redis lease `notifications:webhook_lease:{delivery_id}` TTL 60s; call dispatch; on transient failure increment `attempts`, set `next_attempt_at` to next backoff; on success set `status='delivered'`; on permanent failure or budget exhaustion set `status='dead_letter'`, `dead_lettered_at`, `failure_reason`; release lease in finally
- [X] T031 [US2] Audit-chain emissions for webhook lifecycle in `routers/webhooks_router.py` (rule 32): emit on create/update/activate-deactivate/delete/rotate-secret with `event:"notifications.webhook.{registered|deactivated|rotated|deleted}"`; pass actor, subject, workspace_id scope, before/after diff; secret material NEVER appears in payload
- [X] T032 [US2] Add integration tests `tests/control-plane/integration/notifications/test_webhook_idempotency.py`: end-to-end round trip against an aiohttp test receiver — register, send 5 events including a forced duplicate, verify all arrive, verify HMAC verifies with the secret retrieved from Vault stub, verify idempotency key stability across the duplicate; force 503/503/200 sequence and confirm one row with attempts=3 status=delivered
- [X] T033 [US2] Document and ship the receiver-side verification snippet (Python) in `docs/integrations/webhook-verification.md` as the canonical example (FR-014 acceptance + SC-012); add a CI smoke test that imports the snippet and round-trips a real platform delivery

**Checkpoint**: US2 deliverable. Workspace admins can register webhooks; events fan out with HMAC + at-least-once; retry + DLQ persistence works.

---

## Phase 5: User Story 3 — Slack channel (P2)

**Story goal**: Users connect a Slack incoming-webhook URL; alerts fan out via the Block Kit payload; quiet hours and filters honoured.

**Independent test**: Register a Slack channel against a local Slack-emulator; trigger an attention.requested alert; verify the Block Kit message appears with title, severity, deep link.

- [X] T034 [P] [US3] Create `apps/control-plane/src/platform/notifications/deliverers/slack_deliverer.py` implementing the `ChannelDeliverer` Protocol from `contracts/channel-adapters.md`; build Block Kit payload (header / fields / section / actions with deep link); 10s timeout; classify HTTP outcomes (2xx success, 4xx non-429 dead-letter, 5xx + 429 retry honouring Retry-After)
- [X] T035 [US3] Register `slack` in the `ChannelDelivererRegistry` in `dependencies.py`; ensure `ChannelRouter.route` resolves the Slack deliverer when `channel_type='slack'`
- [X] T036 [US3] Implement Slack channel verification path: on registration POST a one-time test card containing a verification code; store SHA-256(code) on `verification_token_hash`; user enters code via existing `/verify` endpoint
- [X] T037 [US3] Add unit tests `tests/control-plane/unit/notifications/test_slack_teams_sms_adapters.py::test_slack_*` for CA2: Block Kit payload structurally valid; 429 with Retry-After honoured; 4xx non-429 → dead-letter; 5xx → retry; deep link present and well-formed

**Checkpoint**: US3 deliverable.

---

## Phase 6: User Story 4 — Microsoft Teams channel (P2)

**Story goal**: Users connect a Teams connector URL; alerts fan out via Adaptive Card; quiet hours and filters honoured.

**Independent test**: Register a Teams channel against a local Teams-emulator; trigger an alert; verify the Adaptive Card renders.

- [X] T038 [P] [US4] Create `apps/control-plane/src/platform/notifications/deliverers/teams_deliverer.py` implementing the `ChannelDeliverer` Protocol; build Adaptive Card payload per `contracts/channel-adapters.md`; same retry semantics as Slack
- [X] T039 [US4] Register `teams` in the `ChannelDelivererRegistry`; verify routing path
- [X] T040 [US4] Implement Teams channel verification path (one-time test card with verification code; same `/verify` flow)
- [X] T041 [US4] Add unit tests `tests/control-plane/unit/notifications/test_slack_teams_sms_adapters.py::test_teams_*` for CA3: Adaptive Card payload structurally valid; same retry semantics as Slack tests

**Checkpoint**: US4 deliverable.

---

## Phase 7: User Story 5 — Operator dead-letter inspection and replay (P2)

**Story goal**: Operators (and workspace admins for their own workspaces) list, inspect, and replay dead-lettered deliveries; replay reuses the original idempotency key; threshold breaches alert operators.

**Independent test**: Force-fail a webhook receiver, generate 10 events that exhaust their retry budget; list dead-letter (returns 10), restore receiver, batch-replay; verify all 10 deliver and reuse original idempotency keys.

- [X] T042 [P] [US5] Add unit tests `tests/control-plane/unit/notifications/test_dead_letter.py` covering DL1–DL9: list filtered by workspace; cross-workspace forbidden; replay creates new row with same idempotency_key + replayed_from set; replay non-dead-letter row → 409; batch replay accepts filter and returns job id; resolve sets reason and emits audit; threshold worker emits exactly once per cooldown; retention GC scope is dead-letter-only; audit chain entry on replay carries actor + dead_lettered_at
- [X] T043 [US5] Implement dead-letter REST router at `apps/control-plane/src/platform/notifications/routers/deadletter_router.py` per `contracts/dead-letter.md`: GET list with workspace/webhook/since/until/reason filters and authorization scoping (workspace_admin → own workspace only); GET `/{id}`; POST `/{id}/replay` (single); POST `/replay-batch` (returns job_id, dispatches asynchronously); POST `/{id}/resolve`
- [X] T044 [US5] Implement replay logic in webhook service: validate `status='dead_letter'`; INSERT new `webhook_deliveries` row with same `idempotency_key`, `replayed_from=<original_id>`, `replayed_by=actor.id`, `status='pending'`, `next_attempt_at=now()`; emit audit chain entry; original row preserved untouched
- [X] T045 [US5] Implement batch-replay job: filter rows matching criteria; INSERT replay rows in a single transaction; return job_id; subsequent retry-worker tick picks them up; emit per-row outcomes via `monitor.alerts` events
- [X] T046 [US5] Create `apps/control-plane/src/platform/notifications/workers/deadletter_threshold_worker.py` (APScheduler, 60s): aggregate DLQ depth per workspace; when ≥ `dead_letter_warning_threshold`, check Redis cooldown key (1h TTL); if not active emit `notifications.dlq.depth.threshold_reached` to `monitor.alerts` and set cooldown
- [X] T047 [US5] Add dead-letter retention to existing GC: extend `AlertService.run_retention_gc` (or add dedicated `run_dead_letter_retention_gc`) to delete `webhook_deliveries WHERE status='dead_letter' AND dead_lettered_at < now() - interval ':dead_letter_retention_days'::days` (default 30); call from existing daily scheduler entrypoint

**Checkpoint**: US5 deliverable.

---

## Phase 8: User Story 6 — SMS for critical-only alerts (P3)

**Story goal**: Users register a phone number, verify via 6-digit code, and receive SMS for critical-severity alerts only; per-workspace cost cap is enforced.

**Independent test**: Register phone, verify, configure SMS for `severity_floor=critical`; trigger high-severity alert (no SMS) and critical alert (SMS sent); verify cost counter incremented; trigger another critical alert with cost cap exceeded → outcome `fallback`, no SMS.

- [X] T048 [P] [US6] Define `SmsProvider` Protocol and Twilio adapter in `apps/control-plane/src/platform/notifications/deliverers/sms_deliverer.py`: `send_sms(to, body, sender)` signature; resolve credentials via `SecretProvider` from `secret/data/notifications/sms-providers/{deployment}`; never log token, account_sid, or full phone number
- [X] T049 [US6] Implement SMS deliverer adapter per `contracts/channel-adapters.md`: pre-flight cost-cap check via `Redis INCR notifications:sms_cost:{workspace_id}:{yyyy-mm}` against `sms_workspace_monthly_cost_cap_eur`; truncate body to ≤160 chars with deep-link suffix; on cost-cap exceeded return outcome=fallback; classify provider response
- [X] T050 [US6] Implement phone verification path: generate 6-digit code; store SHA-256(code) on `verification_token_hash`; set `verification_expires_at = now + 10min`; send SMS via Twilio adapter; user submits code via existing `/verify` endpoint
- [X] T051 [US6] Register `sms` in `ChannelDelivererRegistry`; in `ChannelRouter.route`, enforce SMS-specific rule: refuse to dispatch if `severity < channel_config.severity_floor` even when filter passes (the floor is hard, not advisory); default `severity_floor='critical'` for SMS rows on insert
- [X] T052 [US6] Add E.164 phone-format validation in channels schema (`schemas.py`); enforce in `routers/channels_router.py` POST handler for `channel_type='sms'`
- [X] T053 [US6] Add unit tests `tests/control-plane/unit/notifications/test_slack_teams_sms_adapters.py::test_sms_*` for CA4–CA6: cost cap exceeded → fallback + counter not incremented + body not sent; body truncation to 160 chars with ellipsis/suffix; secrets never in error_detail or structured-log fields

**Checkpoint**: US6 deliverable.

---

## Phase 9: Polish & Cross-Cutting

- [X] T054 [P] Update `apps/control-plane/src/platform/notifications/dependencies.py` final wiring: ensure `ChannelRouter`, all 6 deliverers, retry worker, threshold worker, verification worker are all registered for the appropriate runtime profiles (api + worker)
- [X] T055 [P] Add OpenAPI tags `notifications-channels` (self-service), `notifications-webhooks` (admin), `notifications-dead-letter` (operator) and ensure all new routers carry them so docs render cleanly
- [X] T056 Add Grafana dashboard JSON `deploy/helm/observability/templates/dashboards/notifications-channels.json` (rule 24, 27): per-channel success rate, p95 latency, retry-rate, DLQ depth per workspace, channel-type fan-out
- [X] T057 [P] Add E2E journey extension test (optional) `tests/e2e/journeys/test_j10_multi_channel_notifications.py` exercising the headline path across user → channel → webhook → DLQ → replay; opt-in via existing journey flag; gated by feature-flag fixture
- [ ] T058 Smoke-run the 12 quickstart scenarios in `quickstart.md` against a local control-plane; record any deviations and either patch behaviour or update quickstart; capture final smoke-checklist outcome
- [ ] T059 [P] Run `ruff check .`, `mypy --strict apps/control-plane/src/platform/notifications`, and `pytest tests/control-plane/{unit,integration}/notifications -q`; resolve all warnings
- [ ] T060 Update `CLAUDE.md` Recent Changes section to surface this feature; verify the auto-generated entry from `update-agent-context.sh` is accurate; commit any edits

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, P1) ──▶ Checkpoint MVP
                                              ──▶ Phase 4 (US2, P1) ──▶ Checkpoint MVP
                                                          │
                                                          ▼
                                              ┌─────────────┐
                                              │ Phase 5 US3 │ (P2, depends on Phase 3 deliverer registry)
                                              │ Phase 6 US4 │ (P2, depends on Phase 3 deliverer registry)
                                              │ Phase 7 US5 │ (P2, depends on Phase 4 webhook + DLQ)
                                              │ Phase 8 US6 │ (P3, depends on Phase 3 deliverer registry)
                                              └─────────────┘
                                                          │
                                                          ▼
                                                 Phase 9 (Polish)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 + Phase 4. Delivers email channel + workspace outbound webhooks with HMAC + at-least-once + DLQ persistence. Slack/Teams/SMS/dead-letter UI come in subsequent phases.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 (different config sections).
- Phase 2: T005 ∥ T006 ∥ T007 ∥ T009 ∥ T010 ∥ T012 (independent files).
- Phase 3: T015 ∥ T022 (test files); T017 (deliverer modification) parallel to T018 (router) once T016 lands.
- Phase 4: T024 (tests) parallel to T025–T031 implementation; T032 (integration test) sequential after T029+T030.
- Phase 5/6/8 can run in parallel once Phase 3 is complete (each is a self-contained adapter + small router/registry change).
- Phase 9: T054 ∥ T055 ∥ T056 ∥ T057 ∥ T059 (independent surfaces).

---

## Implementation strategy

1. **Wave A (MVP)** — Phases 1, 2, 3, 4. Two devs in parallel: dev A on Phase 3 (US1 channel router + email + verification + self-service router), dev B on Phase 4 (US2 webhook deliverer + signing + retry worker + admin router). Joint final integration test in Phase 4 step T032.
2. **Wave B (P2 expansion)** — Phases 5, 6, 7 in parallel. Phases 5/6 are isolated adapters; Phase 7 (DLQ admin) depends on Phase 4's `webhook_deliveries` rows existing.
3. **Wave C (P3)** — Phase 8 (SMS) — solo dev work; depends on the Phase 3 deliverer registry; minimal coupling to Phases 5/6/7.
4. **Wave D (Polish)** — Phase 9: dashboard + docs + lint/types/tests gate + smoke-run quickstart.

**Constitution coverage matrix**:

| Rule | Where applied | Tasks |
|---|---|---|
| 1, 4, 5, 6 (brownfield) | All phases — extends `notifications/`, additive enum, exact files cited | T004 (additive enum), T005 (model extensions), T014 (no rewrite) |
| 7 (backwards compat), 8 (feature flag) | Phase 1, 2, 3 | T003, T014, T016 |
| 9 (PII audit) | US1, US2 | T021 (channel CRUD), T031 (webhook CRUD) |
| 10, 39 (Vault, SecretProvider) | US2, US6 | T026 (webhook secret), T048 (SMS provider) |
| 17 (HMAC + at-least-once + DLQ) | US2 | T025, T026, T029, T030 |
| 18 (residency) | US2, US7 (DLQ residency_violation reason) | T027, T029 |
| 20 (structured JSON logs), 23 (no secrets in logs) | All deliverers | T034, T038, T048 (call out in code review) |
| 32 (audit chain on config changes) | US1, US2, US5 | T021, T031, T044 |
| 34 (DLP outbound) | US1 (all channels), US2 | T016, T029 |
| 44 (rotation does not echo secret) | US2 | T026, T028 |
| 45 (backend has UI) | Deferred to UPD-042 (channel CRUD UI) and UPD-043 (admin webhook CRUD UI). Recorded in plan.md Complexity Tracking. |
| 46 (self-service current_user only) | US1 | T018 |
| 47 (workspace vs platform scope) | US2, US5 | T028, T043 |
| AD-22 (structured logs) | All workers and adapters | implicit via existing `structlog` setup |

---

## Format validation

All 60 tasks above use the required format `- [ ] T### [P?] [Story?] Description with file path`. Every task identifies an exact path under `apps/control-plane/src/platform/notifications/` or `apps/control-plane/migrations/versions/` or `tests/control-plane/{unit,integration}/notifications/` so an LLM can complete each task without further context.
