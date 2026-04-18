# Implementation Plan: Attention Pattern and Configurable User Alerts

**Branch**: `060-attention-user-alerts` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/060-attention-user-alerts/spec.md`

## Summary

New `notifications` bounded context that consumes `interaction.attention` Kafka events and a new `interaction.state_changed` event (additive publish in interactions service), applies per-user alert preference filtering, persists `UserAlert` records, and delivers via three channels: in-app (WebSocket via new `notifications.alerts` Kafka topic consumed by ws_hub), email (aiosmtplib with platform SMTP settings), and webhook (httpx with exponential-backoff retry scanner). Two new tables (`user_alert_settings`, `user_alerts`) plus one tracking table (`alert_delivery_outcomes`) in migration 047.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, aiokafka 0.11+ (Kafka consumer), SQLAlchemy 2.x async, redis-py 5.x async (rate limiting), aiosmtplib 3.0+ (email), httpx 0.27+ (webhook), APScheduler 3.x (retry + GC scheduler)  
**Storage**: PostgreSQL 16 (3 new tables), Redis 7 (sliding-window rate limit), Kafka (2 consumer groups), no new stores  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Linux/Kubernetes (platform-control namespace)  
**Project Type**: Bounded context in the Python control-plane modular monolith  
**Performance Goals**: p95 in-app delivery ≤ 2s (SC-001), email ≤ 60s p95 (SC-005), webhook ≤ 5s p95 (SC-006)  
**Constraints**: No cross-boundary DB access; no new external data stores; additive changes to interactions only  
**Scale/Scope**: One bounded context, ~12 files, migration 047, 2 small interaction file modifications, 1 ws_hub file modification

## Constitution Check

| Rule | Status | Notes |
|---|---|---|
| Brownfield Rule 1: Never rewrite | ✅ PASS | All changes are additive; no file replaced wholesale |
| Brownfield Rule 2: Alembic migrations | ✅ PASS | Migration 047; no raw DDL |
| Brownfield Rule 3: Preserve existing tests | ✅ PASS | Existing interaction + ws_hub tests unaffected |
| Brownfield Rule 4: Use existing patterns | ✅ PASS | Follows connectors bounded context structure exactly; APScheduler retry from connectors/retry.py; Redis rate limit from common/clients/redis.py |
| Brownfield Rule 5: Reference exact files | ✅ PASS | All modified files cited below with line references |
| Brownfield Rule 6: Additive enum values | ✅ PASS | New enums `deliverymethod`, `deliveryoutcome` (not extending existing enums) |
| Brownfield Rule 7: Backward-compatible APIs | ✅ PASS | New endpoints under `/me/` prefix; `context_summary` added as optional field to payload |
| Brownfield Rule 8: Feature flags | ✅ PASS | No default behavior changed; notifications is entirely new — no feature flag needed |
| Principle I: Modular monolith | ✅ PASS | New bounded context in control plane; no new process |
| Principle IV: No cross-boundary DB access | ✅ PASS | notifications only reads its own tables; gets user data via `get_current_user` dependency; `context_summary` added to Kafka payload to avoid needing to read interactions tables |
| Principle XIII: Attention pattern | ✅ PASS | This feature IS the consumer side of the attention pattern |
| Kafka-first for async | ✅ PASS | WebSocket delivery via `notifications.alerts` topic (fanout); no direct ConnectionRegistry calls from notifications |

**POST-DESIGN RE-CHECK**: All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/060-attention-user-alerts/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── rest-api.md      ← Phase 1 output
└── tasks.md             ← Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
apps/control-plane/src/platform/

# NEW — notifications bounded context
notifications/
├── __init__.py
├── models.py             ← UserAlertSettings, UserAlert, AlertDeliveryOutcome
├── schemas.py            ← Pydantic request/response schemas
├── service.py            ← AlertService (business logic + transition matching)
├── repository.py         ← NotificationsRepository (async SQLAlchemy queries)
├── router.py             ← FastAPI router (/me/alerts, /me/alert-settings)
├── events.py             ← Event type definitions + publish_alert_created()
├── dependencies.py       ← get_notifications_service()
├── exceptions.py         ← NotificationsError, AlertNotFoundError
├── consumers/
│   ├── __init__.py
│   ├── attention_consumer.py   ← Kafka consumer: interaction.attention topic
│   └── state_change_consumer.py ← Kafka consumer: interaction.events (state_changed filter)
└── deliverers/
    ├── __init__.py
    ├── email_deliverer.py    ← aiosmtplib wrapper
    └── webhook_deliverer.py  ← httpx + retry recording

# MODIFIED — interactions bounded context
interactions/events.py        ← Add state_changed event type + InteractionStateChangedPayload + publish fn
interactions/interaction_service.py ← Call publish_interaction_state_changed() on each state transition

# MODIFIED — ws_hub
ws_hub/fanout.py              ← Add notifications.alerts topic consumer; route to alerts channel
ws_hub/channels.py            ← Add ALERTS ChannelType (if not present)

# MODIFIED — infrastructure
migrations/versions/047_notifications_alerts.py   ← New migration
main.py                        ← Wire up consumers + APScheduler jobs (retry, GC, email poll)
common/config.py               ← Add NotificationsSettings section
```

## Implementation Tasks

### Task 1 — Alembic migration 047
**File**: `apps/control-plane/migrations/versions/047_notifications_alerts.py`  
Create migration with `revision="047_notifications_alerts"`, `down_revision="046_workspace_goal_lifecycle_and_decision"`. Add enums `deliverymethod`, `deliveryoutcome`. Create tables `user_alert_settings`, `user_alerts`, `alert_delivery_outcomes` per DDL in `data-model.md` Section 1.

### Task 2 — NotificationsSettings in config.py
**File**: `apps/control-plane/src/platform/common/config.py`  
Add `NotificationsSettings` Pydantic sub-model with fields:
- `rate_limit_per_source_per_minute: int = 20`
- `alert_retention_days: int = 90`
- `webhook_max_retries: int = 5`
- `retry_scan_interval_seconds: int = 30`
- `gc_interval_hours: int = 24`
Mount as `notifications: NotificationsSettings` in `PlatformSettings`.

### Task 3 — notifications/models.py
**File**: `apps/control-plane/src/platform/notifications/models.py`  
Create `DeliveryMethod(StrEnum)`, `DeliveryOutcome(StrEnum)`, `UserAlertSettings`, `UserAlert`, `AlertDeliveryOutcome` models per `data-model.md` Section 2. Follow `connectors/models.py` import style.

### Task 4 — notifications/schemas.py
**File**: `apps/control-plane/src/platform/notifications/schemas.py`  
Create `UserAlertSettingsRead`, `UserAlertSettingsUpdate` (with webhook_url validation), `UserAlertRead`, `AlertDeliveryOutcomeRead`, `UserAlertDetail`, `AlertListResponse`, `UnreadCountResponse` per `data-model.md` Section 3 and `contracts/rest-api.md`.

### Task 5 — notifications/repository.py
**File**: `apps/control-plane/src/platform/notifications/repository.py`  
`NotificationsRepository` class with `AsyncSession`:
- `get_settings(user_id)` → `UserAlertSettings | None`
- `upsert_settings(user_id, data)` → `UserAlertSettings`
- `create_alert(...)` → `UserAlert`
- `list_alerts(user_id, read_filter, cursor, limit)` → `(list[UserAlert], next_cursor | None, unread_count)`
- `get_alert(alert_id, user_id)` → `UserAlert` (raises `AlertNotFoundError` or `AuthorizationError`)
- `mark_read(alert_id, user_id)` → `UserAlert`
- `get_unread_count(user_id)` → `int`
- `get_pending_webhook_deliveries()` → `list[AlertDeliveryOutcome]` (for retry scanner)
- `update_delivery_outcome(outcome_id, ...)` → `AlertDeliveryOutcome`
- `delete_expired_alerts(retention_days)` → `int` (count deleted)

### Task 6 — notifications/deliverers/email_deliverer.py
**File**: `apps/control-plane/src/platform/notifications/deliverers/email_deliverer.py`  
`EmailDeliverer` class with `send(alert, recipient_email, smtp_settings)`. Use `aiosmtplib.send()` pattern from `connectors/implementations/email.py`. Return `DeliveryOutcome.SUCCESS` or `DeliveryOutcome.FAILED`.

### Task 7 — notifications/deliverers/webhook_deliverer.py
**File**: `apps/control-plane/src/platform/notifications/deliverers/webhook_deliverer.py`  
`WebhookDeliverer` class with `send(alert, webhook_url)`. POST JSON payload via `httpx.AsyncClient`. Return `(DeliveryOutcome, error_detail | None)`. Payload must NOT include credentials (only: `id`, `alert_type`, `title`, `body`, `urgency`, `created_at`). Handle 5xx and timeout → `TIMED_OUT`, 2xx → `SUCCESS`, 4xx permanent → `FAILED`.

### Task 8 — notifications/service.py
**File**: `apps/control-plane/src/platform/notifications/service.py`  
`AlertService` class with:
- `get_or_default_settings(user_id)` → `UserAlertSettings` (returns defaults if no record)
- `upsert_settings(user_id, data)` → `UserAlertSettings`
- `process_attention_request(payload: AttentionRequestedPayload)` → dispatch per user settings
- `process_state_change(payload: InteractionStateChangedPayload, workspace_id)` → dispatch per workspace member settings
- `list_alerts(user_id, ...)` → `AlertListResponse`
- `get_alert(alert_id, user_id)` → `UserAlertDetail`
- `mark_alert_read(alert_id, user_id)` → `UserAlertRead` + trigger read-propagation event
- `get_unread_count(user_id)` → `UnreadCountResponse`
- `run_webhook_retry_scan()` → retry pending webhook deliveries
- `run_retention_gc()` → delete expired alerts

Include `matches_transition_pattern()` and `_STATE_ALIASES` per `data-model.md` Section 6. Rate-limit via `redis_client.check_rate_limit("notifications", f"{source_fqn}:{user_id}", limit, 60_000)`. For in-app delivery publish to `notifications.alerts` Kafka topic. For email use `EmailDeliverer`. For webhook use `WebhookDeliverer` + create `AlertDeliveryOutcome` record.

### Task 9 — notifications/events.py
**File**: `apps/control-plane/src/platform/notifications/events.py`  
Define `NotificationsEventType(StrEnum)` with `alert_created`, `alert_read`. Define `AlertCreatedPayload`, `AlertReadPayload`. Add `publish_alert_created(producer, payload, correlation_ctx)` publishing to `notifications.alerts` topic with `user_id` as key.

### Task 10 — notifications/consumers/attention_consumer.py
**File**: `apps/control-plane/src/platform/notifications/consumers/attention_consumer.py`  
`AttentionConsumer` class. Consumer group: `notifications-attention`. Subscribe to `interaction.attention` topic. On each event: deserialize `AttentionRequestedPayload`, call `alert_service.process_attention_request(payload)`. Handle unknown urgency → default `medium`, log warning. Discard events with nonexistent `target_identity` (log + skip). Rate limiting enforced inside `process_attention_request`.

### Task 11 — notifications/consumers/state_change_consumer.py
**File**: `apps/control-plane/src/platform/notifications/consumers/state_change_consumer.py`  
`StateChangeConsumer` class. Consumer group: `notifications-state-change`. Subscribe to `interaction.events` topic. On each event: deserialize `EventEnvelope`, filter for `event_type == "interaction.state_changed"`. Deserialize payload as `InteractionStateChangedPayload`. Call `alert_service.process_state_change(payload, correlation_ctx.workspace_id)`. Discard events with missing workspace_id or unknown interaction state (log + skip).

### Task 12 — notifications/router.py
**File**: `apps/control-plane/src/platform/notifications/router.py`  
`router = APIRouter(prefix="/me", tags=["notifications"])`. Six endpoints per `contracts/rest-api.md`:
- `GET /alert-settings` → `get_alert_settings`
- `PUT /alert-settings` → `upsert_alert_settings`
- `GET /alerts` → `list_alerts`
- `GET /alerts/unread-count` → `get_unread_count`
- `PATCH /alerts/{alert_id}/read` → `mark_alert_read`
- `GET /alerts/{alert_id}` → `get_alert_detail`

All use `get_current_user` dependency. Router registered in `main.py` with prefix `/api/v1`.

### Task 13 — interactions/events.py — add state_changed event
**File**: `apps/control-plane/src/platform/interactions/events.py`  
Additive changes per `data-model.md` Section 4:
1. Add `state_changed = "interaction.state_changed"` to `InteractionsEventType`.
2. Add `InteractionStateChangedPayload(BaseModel)` with fields: `interaction_id`, `workspace_id`, `from_state`, `to_state`, `occurred_at`.
3. Add `publish_interaction_state_changed(producer, payload, correlation_ctx)` publishing to `interaction.events` topic with `interaction_id` as key.
4. Add `context_summary: str | None = None` to `AttentionRequestedPayload`.

### Task 14 — interactions/interaction_service.py — emit state_changed
**File**: `apps/control-plane/src/platform/interactions/interaction_service.py`  
In each method that transitions interaction state (start, wait, complete, fail, cancel, pause, resume), call `publish_interaction_state_changed()` with the old and new state values. Use the existing `CorrelationContext` in each method. This is additive — existing `publish_interaction_started()`, `publish_interaction_completed()`, etc. calls are preserved.

### Task 15 — ws_hub/fanout.py — add notifications.alerts consumer
**File**: `apps/control-plane/src/platform/ws_hub/fanout.py`  
In the `_route_message()` method (near line 278): add a branch for `topic == "notifications.alerts"`. Extract `user_id` from event payload (`payload.get("user_id")`). Append `(ChannelType.ALERTS, user_id)` to matches. Add `ChannelType.ALERTS` to auto-subscribe logic in `ws_hub/router.py` (same pattern as `ChannelType.ATTENTION` in `_auto_subscribe_attention()`).

### Task 16 — main.py — wire consumers and scheduler
**File**: `apps/control-plane/src/platform/main.py`  
Follow the existing connector/context-engineering patterns:
1. Instantiate `AttentionConsumer` and `StateChangeConsumer` in the lifespan startup block.
2. Start both consumers (aiokafka `start()`).
3. Register APScheduler jobs:
   - `notifications-webhook-retry`: interval `settings.notifications.retry_scan_interval_seconds`, calls `_run_webhook_retry_scan()`.
   - `notifications-retention-gc`: interval `settings.notifications.gc_interval_hours * 3600`, calls `_run_retention_gc()`.
4. Register `notifications.router` in `app.include_router()`.

### Task 17 — Tests
**Files**:
- `apps/control-plane/tests/unit/notifications/test_transition_matching.py` — unit tests for `matches_transition_pattern()` covering all patterns in S4–S7 of quickstart.md.
- `apps/control-plane/tests/unit/notifications/test_alert_service.py` — unit tests for `process_attention_request` (rate limiting, unknown urgency, nonexistent identity, preference filtering).
- `apps/control-plane/tests/integration/notifications/test_notifications_api.py` — integration tests for all 6 REST endpoints: CRUD, authorization isolation (S16), mark-read propagation.

## Complexity Tracking

No constitution violations. No complexity justification needed.

## Estimated Effort

2 story points (~1 day)

## Artifacts Generated

| Artifact | Path |
|---|---|
| Research | `specs/060-attention-user-alerts/research.md` |
| Data Model | `specs/060-attention-user-alerts/data-model.md` |
| REST API Contracts | `specs/060-attention-user-alerts/contracts/rest-api.md` |
| Quickstart / Scenarios | `specs/060-attention-user-alerts/quickstart.md` |
| Plan (this file) | `specs/060-attention-user-alerts/plan.md` |
