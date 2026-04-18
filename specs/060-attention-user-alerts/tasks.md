# Tasks: Attention Pattern and Configurable User Alerts

**Input**: Design documents from `specs/060-attention-user-alerts/`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/rest-api.md ✅ quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- Exact file paths from `apps/control-plane/src/platform/` unless otherwise noted

---

## Dependency Graph

```
Phase 1 (Setup) ──► Phase 2 (Foundation) ──► Phase 3 (US2: Settings)
                                           ──► Phase 4 (US1: Attention/In-App)  ← needs US2
                                           ──► Phase 5 (US3: Read/History)      ← needs US4
                                           ──► Phase 6 (US4: State-Change/Offline) ← needs US1
                                           ──► Phase 7 (US5: Webhook)            ← needs US2
                                           ──► Final Phase (Polish)
```

**Story completion order**: US2 → US1 → US3 → US4 → US5

---

## Phase 1: Setup

**Purpose**: Migration and configuration — unblocks all bounded context work

- [X] T001 Create Alembic migration `apps/control-plane/migrations/versions/047_notifications_alerts.py` with `revision="047_notifications_alerts"`, `down_revision="046_workspace_goal_lifecycle_and_decision"`, enums `deliverymethod`/`deliveryoutcome`, and tables `user_alert_settings`, `user_alerts`, `alert_delivery_outcomes` per DDL in `specs/060-attention-user-alerts/data-model.md` Section 1
- [X] T002 Add `NotificationsSettings` Pydantic sub-model to `apps/control-plane/src/platform/common/config.py` with fields `rate_limit_per_source_per_minute: int = 20`, `alert_retention_days: int = 90`, `webhook_max_retries: int = 5`, `retry_scan_interval_seconds: int = 30`, `gc_interval_hours: int = 24`; mount as `notifications: NotificationsSettings` in `PlatformSettings`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core bounded context files that ALL user story phases depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create `apps/control-plane/src/platform/notifications/__init__.py` and package directory structure including `consumers/` and `deliverers/` sub-packages with their `__init__.py` files
- [X] T004 [P] Create `apps/control-plane/src/platform/notifications/models.py` — `DeliveryMethod(StrEnum)`, `DeliveryOutcome(StrEnum)`, `UserAlertSettings`, `UserAlert`, `AlertDeliveryOutcome` SQLAlchemy models with mixins per `data-model.md` Section 2
- [X] T005 [P] Create `apps/control-plane/src/platform/notifications/schemas.py` — `UserAlertSettingsRead`, `UserAlertSettingsUpdate` (with `@model_validator` webhook_url check), `UserAlertRead`, `AlertDeliveryOutcomeRead`, `UserAlertDetail`, `AlertListResponse`, `UnreadCountResponse` per `data-model.md` Section 3
- [X] T006 [P] Create `apps/control-plane/src/platform/notifications/events.py` — `NotificationsEventType(StrEnum)` with `alert_created="notifications.alert_created"` and `alert_read="notifications.alert_read"`; `AlertCreatedPayload`, `AlertReadPayload` Pydantic models; `publish_alert_created(producer, payload, correlation_ctx)` publishing to `notifications.alerts` topic with `user_id` as key
- [X] T007 [P] Create `apps/control-plane/src/platform/notifications/exceptions.py` — `NotificationsError(PlatformError)`, `AlertNotFoundError(NotFoundError)`, `AlertAuthorizationError(AuthorizationError)`; create `apps/control-plane/src/platform/notifications/dependencies.py` — `get_notifications_service()` FastAPI dependency factory
- [X] T008 Create `apps/control-plane/src/platform/notifications/repository.py` — `NotificationsRepository(AsyncSession)` with methods: `get_settings(user_id)`, `upsert_settings(user_id, data)`, `create_alert(...)`, `list_alerts(user_id, read_filter, cursor, limit)` returning `(list[UserAlert], str|None, int)`, `get_alert(alert_id, user_id)`, `mark_read(alert_id, user_id)`, `get_unread_count(user_id)`, `get_pending_webhook_deliveries()`, `update_delivery_outcome(outcome_id, ...)`, `delete_expired_alerts(retention_days)`
- [X] T009 [P] Modify `apps/control-plane/src/platform/interactions/events.py` — add `state_changed = "interaction.state_changed"` to `InteractionsEventType`; add `InteractionStateChangedPayload(BaseModel)` with `interaction_id`, `workspace_id`, `from_state`, `to_state`, `occurred_at`; add `publish_interaction_state_changed(producer, payload, correlation_ctx)` publishing to `interaction.events`; add `context_summary: str | None = None` to existing `AttentionRequestedPayload`
- [X] T010 Modify `apps/control-plane/src/platform/interactions/interaction_service.py` — call `publish_interaction_state_changed()` at each state transition (start, wait, complete, fail, cancel, pause, resume) passing the previous and new state values; preserve all existing `publish_interaction_started/completed/failed/canceled` calls

**Checkpoint**: Foundation ready — all user story phases can now proceed

---

## Phase 3: User Story 2 — User configures alert preferences (Priority: P1)

**Goal**: Users can read and update their alert delivery preferences (subscribed transitions, delivery method, webhook URL).

**Independent Test** (quickstart.md S4, S7, S8): PUT settings with `["any_to_failed"]` only, trigger an `any_to_complete` event — no alert generated. Trigger `any_to_failed` — alert generated. Verify PUT with `delivery_method=webhook` and no `webhook_url` returns 422.

- [X] T011 [US2] Create `apps/control-plane/src/platform/notifications/service.py` — `AlertService` skeleton with `__init__(repo, redis, producer, settings)`, `_STATE_ALIASES` dict, `matches_transition_pattern(pattern, from_state, to_state)` function, `get_or_default_settings(user_id)` (returns defaults if no DB record), `upsert_settings(user_id, data: UserAlertSettingsUpdate)` with webhook_url validation
- [X] T012 [US2] Create `apps/control-plane/src/platform/notifications/router.py` with `router = APIRouter(prefix="/me", tags=["notifications"])` and two endpoints: `GET /alert-settings` → `get_alert_settings(current_user, service)` returning `UserAlertSettingsRead`; `PUT /alert-settings` → `upsert_alert_settings(data, current_user, service)` returning `UserAlertSettingsRead`
- [X] T013 [US2] Register `notifications.router` in `apps/control-plane/src/platform/main.py` with `app.include_router(notifications_router, prefix="/api/v1")` in the router registration section (follow existing bounded context registration pattern)

---

## Phase 4: User Story 1 — Attention request reaches user (Priority: P1) 🎯 MVP

**Goal**: Agent-emitted attention requests create persisted alerts and are delivered to online users via WebSocket within 2 seconds; offline users receive them on next login.

**Independent Test** (quickstart.md S1, S2, S3): Publish `AttentionRequestedPayload` to `interaction.attention` targeting an online user. Verify WebSocket `alerts` channel receives `notifications.alert_created` within 2 seconds. Verify `user_alerts` row created. Repeat for offline user: verify row created, no WebSocket attempt. Log in, verify alert appears in GET /me/alerts.

- [X] T014 [P] [US1] Create `apps/control-plane/src/platform/notifications/deliverers/email_deliverer.py` — `EmailDeliverer` class with `async send(alert: UserAlert, recipient_email: str, smtp_settings) -> DeliveryOutcome`; use `aiosmtplib.send()` per pattern in `connectors/implementations/email.py`; return `DeliveryOutcome.SUCCESS` on send, `DeliveryOutcome.FAILED` on exception
- [X] T015 [P] [US1] Modify `apps/control-plane/src/platform/ws_hub/fanout.py` — in `_route_message()` add branch for `topic == "notifications.alerts"`: extract `user_id` from `payload.get("user_id")`, append `(ChannelType.ALERTS, str(user_id))` to matches; modify `apps/control-plane/src/platform/ws_hub/router.py` to auto-subscribe every connection to the `alerts` channel on connect (same pattern as existing `_auto_subscribe_attention`)
- [X] T016 [US1] Add `process_attention_request(payload: AttentionRequestedPayload)` to `apps/control-plane/src/platform/notifications/service.py` — resolve `target_identity` to `user_id` via `get_current_user` pattern; load user settings via `get_or_default_settings`; rate-limit via `redis.check_rate_limit("notifications", f"{payload.source_agent_fqn}:{user_id}", settings.notifications.rate_limit_per_source_per_minute, 60_000)`; if allowed: call `repo.create_alert(...)` with `alert_type="attention_request"`, populate `title` from `source_agent_fqn`, `body` from `payload.context_summary`, `urgency` from payload (default `medium` if unknown, log warning); call `publish_alert_created(producer, ...)` for in-app delivery
- [X] T017 [US1] Create `apps/control-plane/src/platform/notifications/consumers/attention_consumer.py` — `AttentionConsumer` class; consumer group `notifications-attention`; subscribe to `interaction.attention` topic; deserialize envelope, extract `AttentionRequestedPayload`; call `alert_service.process_attention_request(payload)`; handle nonexistent `target_identity` by logging and skipping (no alert created)
- [X] T018 [US1] Start `AttentionConsumer` in `apps/control-plane/src/platform/main.py` lifespan startup block — instantiate with service dependencies; call `await consumer.start()`; register shutdown in lifespan teardown

---

## Phase 5: User Story 3 — Users read, dismiss, and review alert history (Priority: P1)

**Goal**: Users see their alerts list, unread count, can mark individual alerts read, and unread count propagates to all sessions.

**Independent Test** (quickstart.md S13, S16): Create 3 alerts for user. GET /me/alerts returns all 3 unread. GET /me/alerts/unread-count returns `{"count": 3}`. PATCH /me/alerts/{id}/read → read=true, count=2. Both WebSocket sessions receive `notifications.alert_read` push. GET /me/alerts/{other_user_alert_id} returns 403.

- [X] T019 [P] [US3] Add `list_alerts(user_id, read_filter, cursor, limit)`, `get_alert(alert_id, user_id)`, `mark_alert_read(alert_id, user_id)`, `get_unread_count(user_id)` methods to `apps/control-plane/src/platform/notifications/service.py` — `mark_alert_read` must publish `notifications.alert_read` event to `notifications.alerts` Kafka topic (with `alert_id` + `unread_count`) for cross-session propagation
- [X] T020 [US3] Add four endpoints to `apps/control-plane/src/platform/notifications/router.py`: `GET /alerts` (query params: `read=all|read|unread`, `limit`, `cursor`) returning `AlertListResponse`; `GET /alerts/unread-count` returning `UnreadCountResponse`; `PATCH /alerts/{alert_id}/read` returning `UserAlertRead`; `GET /alerts/{alert_id}` returning `UserAlertDetail`

---

## Phase 6: User Story 4 — Offline alerts deliver on next login (Priority: P2)

**Goal**: State-change events generate alerts for subscribed users; offline users receive all unread alerts when they reconnect.

**Independent Test** (quickstart.md S2, S4, S15): Log user out. Trigger `interaction.state_changed` for a transition the user is subscribed to. Log back in. GET /me/alerts shows the new alert as unread with correct timestamp. Trigger a non-subscribed transition — no alert created.

- [X] T021 [P] [US4] Create `apps/control-plane/src/platform/notifications/consumers/state_change_consumer.py` — `StateChangeConsumer` class; consumer group `notifications-state-change`; subscribe to `interaction.events` topic; deserialize `EventEnvelope`; filter for `event_type == "interaction.state_changed"`; call `alert_service.process_state_change(payload, workspace_id)`; discard events with missing `workspace_id` or unrecognized states (log + skip)
- [X] T022 [US4] Add `process_state_change(payload: InteractionStateChangedPayload, workspace_id: UUID)` to `apps/control-plane/src/platform/notifications/service.py` — query workspace members from workspaces service (internal interface); for each member load settings via `get_or_default_settings`; call `matches_transition_pattern` for each subscribed pattern; if matched: create alert and dispatch per delivery method; apply rate limiting per source (use interaction_id as source key)
- [X] T023 [US4] Wire `StateChangeConsumer` startup + retention GC in `apps/control-plane/src/platform/main.py` — start `StateChangeConsumer` in lifespan; register APScheduler job `notifications-retention-gc` with interval `settings.notifications.gc_interval_hours * 3600` seconds calling `_run_retention_gc()`; add `_run_retention_gc()` async function calling `alert_service.run_retention_gc()`

---

## Phase 7: User Story 5 — Webhook delivery for external integrations (Priority: P3)

**Goal**: Alerts deliver via HTTP POST to user-configured URLs with exponential-backoff retry and recorded outcomes.

**Independent Test** (quickstart.md S10, S11, S12): Configure user with webhook URL. Trigger qualifying event. Verify POST at endpoint within 5 seconds with payload containing `id`, `alert_type`, `title`, `urgency` but NO credentials. Take endpoint down, trigger again — retry scanner retries with 4^(n-1)s backoff. After max retries, `outcome=failed`. Configure user with `delivery_method=webhook` but no URL — verify fallback to in_app, `outcome=fallback`.

- [X] T024 [P] [US5] Create `apps/control-plane/src/platform/notifications/deliverers/webhook_deliverer.py` — `WebhookDeliverer` with `async send(alert: UserAlert, webhook_url: str) -> tuple[DeliveryOutcome, str | None]`; POST JSON payload `{id, alert_type, title, body, urgency, created_at}` (no credentials) via `httpx.AsyncClient(timeout=10.0)`; 2xx → `(SUCCESS, None)`; 5xx or timeout → `(TIMED_OUT, error_detail)`; 4xx permanent → `(FAILED, error_detail)`
- [X] T025 [US5] Add `_dispatch_webhook(alert, settings, delivery_outcome_record)` and `run_webhook_retry_scan()` to `apps/control-plane/src/platform/notifications/service.py` — `_dispatch_webhook` calls `WebhookDeliverer.send()`, updates `AlertDeliveryOutcome` record; on failure sets `next_retry_at = compute_next_retry_at(attempt_count)` from `connectors/retry.py`; `run_webhook_retry_scan()` fetches pending deliveries from repo and retries those past `next_retry_at` up to `settings.notifications.webhook_max_retries`
- [X] T026 [US5] Register APScheduler job `notifications-webhook-retry` in `apps/control-plane/src/platform/main.py` with interval `settings.notifications.retry_scan_interval_seconds` calling `_run_webhook_retry_scan()`; add `_run_webhook_retry_scan()` async function using session + service; also add `run_retention_gc()` method to `notifications/service.py` calling `repo.delete_expired_alerts(settings.notifications.alert_retention_days)`

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T027 [P] Create `apps/control-plane/tests/unit/notifications/test_transition_matching.py` — unit tests for `matches_transition_pattern()`: `working_to_pending` matches `running→waiting`; `any_to_complete` matches `paused→completed`; `any_to_failed` matches any→failed; unknown pattern ignored when valid pattern also present (quickstart.md S5, S6, S17)
- [X] T028 [P] Create `apps/control-plane/tests/unit/notifications/test_alert_service.py` — unit tests for `process_attention_request`: unknown urgency defaults to `medium`; rate-limited source drops alert and logs; nonexistent target_identity skips alert creation; offline user alert persisted without WebSocket delivery attempt
- [X] T029 [P] Create `apps/control-plane/tests/integration/notifications/test_notifications_api.py` — integration tests for all 6 REST endpoints: GET/PUT alert-settings, GET alerts with filters, GET unread-count, PATCH mark-read, GET alert detail; verify 403 on cross-user access (quickstart.md S16)

---

## Dependencies

| Story | Depends On | Reason |
|---|---|---|
| US2 (settings) | Phase 2 (foundation) | Needs models, schemas, repository |
| US1 (attention) | US2 | Needs `get_or_default_settings` to filter by preferences |
| US3 (read/history) | US1 | Needs alerts to exist; needs in-app delivery wired |
| US4 (offline/state-change) | US1 | Needs `create_alert` + in-app delivery service methods |
| US5 (webhook) | US2 | Needs settings for webhook_url; needs `create_alert` |

---

## Parallel Execution per Phase

### Phase 2 (Foundation) — 5 independent tasks:
```
T003 (package init) ──┐
T004 (models)         ├──► T008 (repository) ──► T009 (interactions/events.py)
T005 (schemas)        │                       ──► T010 (interaction_service.py)
T006 (events.py)      │
T007 (exceptions)  ───┘
```

### Phase 4 (US1) — 2 independent tasks:
```
T014 (email_deliverer)   ─┐
T015 (ws_hub fanout)      ├──► T016 (service.process_attention_request)
                          └──► T017 (attention_consumer) ──► T018 (main.py wire)
```

### Final Phase — 3 independent tasks:
```
T027 (test_transition_matching) ─┐
T028 (test_alert_service)        ├── all parallel
T029 (test_notifications_api)   ─┘
```

---

## Implementation Strategy

**MVP (deliver value fastest)**: Complete through Phase 4 (US1). This gives:
- Preference configuration (US2)
- Attention request delivery via WebSocket in real-time (US1)
- Alert persistence for offline users (US1)

**Increment 2**: Phase 5 (US3) — alerts list, mark-read, unread count. Completes the read surface.

**Increment 3**: Phase 6 (US4) — state-change consumer. Enables automatic alerts on interaction lifecycle events.

**Increment 4**: Phase 7 (US5) — webhook delivery. Enables external integrations.

**Estimated total effort**: 2 story points (~1 day)

---

## Summary

| Phase | Tasks | Story | Parallelizable |
|---|---|---|---|
| Setup | T001–T002 | — | T002 [P] after T001 |
| Foundation | T003–T010 | — | T003–T007 fully parallel; T009–T010 parallel |
| US2 (Settings) | T011–T013 | US2 (P1) | T012 [P] after T011 |
| US1 (Attention) | T014–T018 | US1 (P1) | T014, T015 parallel |
| US3 (Read) | T019–T020 | US3 (P1) | T019 [P] |
| US4 (Offline) | T021–T023 | US4 (P2) | T021 [P] |
| US5 (Webhook) | T024–T026 | US5 (P3) | T024 [P] |
| Polish | T027–T029 | — | All [P] |
| **Total** | **29 tasks** | | |
