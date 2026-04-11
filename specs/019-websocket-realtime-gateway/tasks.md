# Tasks: WebSocket Real-Time Gateway

**Input**: Design documents from `specs/019-websocket-realtime-gateway/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ws-protocol.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Tests are included (spec requires ≥95% coverage).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Package Structure)

**Purpose**: Create the `ws_hub` package skeleton and entrypoint — no logic yet, just stubs.

- [x] T001 Create `apps/control-plane/src/platform/ws_hub/` package with empty stubs: `__init__.py`, `router.py`, `connection.py`, `subscription.py`, `fanout.py`, `writer.py`, `heartbeat.py`, `visibility.py`, `schemas.py`, `exceptions.py`, `dependencies.py`
- [x] T002 Create `apps/control-plane/entrypoints/ws_main.py`: FastAPI app factory for `ws-hub` runtime profile, mounts `/ws` WebSocket route only, includes lifespan context manager stubs for KafkaFanout start/stop
- [x] T003 [P] Add ws-hub settings to `PlatformSettings` in `apps/control-plane/src/platform/common/config.py`: `WS_CLIENT_BUFFER_SIZE: int = 1000`, `WS_HEARTBEAT_INTERVAL_SECONDS: int = 30`, `WS_HEARTBEAT_TIMEOUT_SECONDS: int = 10`, `WS_MAX_MALFORMED_MESSAGES: int = 10`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data structures and schemas used by all user stories — MUST be complete before any story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 [P] Implement `ChannelType(StrEnum)` (11 values: execution/interaction/conversation/workspace/fleet/reasoning/correction/simulation/testing/alerts/attention) and `CHANNEL_TOPIC_MAP` dict (channel → Kafka topics list) in `apps/control-plane/src/platform/ws_hub/subscription.py`
- [x] T005 [P] Implement all Pydantic v2 WS protocol message schemas in `apps/control-plane/src/platform/ws_hub/schemas.py`: client messages (`SubscribeMessage`, `UnsubscribeMessage`, `ListSubscriptionsMessage`) and server messages (`ConnectionEstablishedMessage`, `SubscriptionConfirmedMessage`, `SubscriptionErrorMessage`, `SubscriptionRemovedMessage`, `SubscriptionListMessage`, `SubscriptionInfo`, `EventMessage`, `EventsDroppedMessage`, `ErrorMessage`) — all with `type: Literal[...]` discriminator fields
- [x] T006 [P] Implement WebSocketError hierarchy in `apps/control-plane/src/platform/ws_hub/exceptions.py`: `WebSocketGatewayError`, `SubscriptionAuthError` (code: unauthorized/resource_not_found), `ProtocolViolationError` (code: protocol_violation/invalid_channel/invalid_resource_id)

**Checkpoint**: Foundation ready — all user story phases can now start.

---

## Phase 3: User Story 1 — Authenticated WebSocket Connection (Priority: P1) 🎯 MVP

**Goal**: Authenticated clients connect via WebSocket, receive a welcome message with auto-subscriptions list, and get their connection registered in-memory.

**Independent Test**: Connect with valid JWT → receive `connection_established` message. Connect with invalid token → HTTP 401 (upgrade rejected). Session invalidated → connection closed with code 4401.

- [x] T007 [P] [US1] Implement `WebSocketConnection` dataclass (fields: `connection_id`, `user_id`, `workspace_ids`, `websocket`, `subscriptions`, `send_queue`, `dropped_count`, `connected_at`, `last_pong_at`, `closed`, `malformed_message_count`) and `ConnectionRegistry` class (add/remove/get/get_by_user_id/all/count) in `apps/control-plane/src/platform/ws_hub/connection.py`
- [x] T008 [US1] Implement FastAPI WebSocket route `GET /ws` in `apps/control-plane/src/platform/ws_hub/router.py`: accept `Authorization` header or `?token=` query param, validate JWT via in-process `auth_service.validate_token()`, extract `user_id` + fetch `workspace_ids` via `workspaces_service.get_user_workspace_ids()`, create `WebSocketConnection` with `asyncio.Queue(maxsize=WS_CLIENT_BUFFER_SIZE)`, register in `ConnectionRegistry`, send `connection_established` JSON, launch `ConnectionWriter` and `ConnectionHeartbeat` asyncio tasks
- [x] T009 [US1] Implement `get_connection_registry()` and `get_fanout()` FastAPI DI factories in `apps/control-plane/src/platform/ws_hub/dependencies.py` (singleton scoped to app lifespan)
- [x] T010 [P] [US1] Write unit tests for `ConnectionRegistry` CRUD operations in `apps/control-plane/tests/unit/test_ws_hub_connection.py`: add/remove/get/get_by_user_id, duplicate add, remove non-existent, count
- [x] T011 [US1] Write integration tests for WebSocket connection auth in `apps/control-plane/tests/integration/test_ws_connection_flow.py`: valid token → `connection_established`, invalid token → HTTP 401, expired token → HTTP 401, valid connect + produce `auth.events` session invalidated → connection closed with code 4401, `auto_subscriptions` contains `attention:{user_id}`

**Checkpoint**: US1 complete — WebSocket connections authenticated, registered, and receive welcome message.

---

## Phase 4: User Story 2 — Channel Subscription Management (Priority: P1)

**Goal**: Authenticated clients send subscribe/unsubscribe/list messages. The gateway validates authorization (workspace membership) and manages subscription state via `SubscriptionRegistry`.

**Independent Test**: Subscribe to a valid channel → `subscription_confirmed`. Subscribe to unauthorized resource → `subscription_error` (code: unauthorized). Unsubscribe → `subscription_removed`. List subscriptions → returns current subscriptions including auto-subscribed attention.

- [x] T012 [P] [US2] Implement `Subscription` dataclass (fields: `channel`, `resource_id`, `subscribed_at`, `auto`) and `SubscriptionRegistry` class (subscribe/unsubscribe/unsubscribe_all/get_subscribers/get_active_topics with topic refcount tracking) in `apps/control-plane/src/platform/ws_hub/subscription.py`
- [x] T013 [US2] Implement `VisibilityFilter.authorize_subscription()` in `apps/control-plane/src/platform/ws_hub/visibility.py`: given a connection + channel + resource_id, call `workspaces_service.get_workspace_id_for_resource(channel, resource_id)` to resolve the owning workspace, then check `resource_workspace_id in conn.workspace_ids`; allow alerts/attention subscriptions only for own `user_id`
- [x] T014 [US2] Implement message dispatch loop in `apps/control-plane/src/platform/ws_hub/router.py`: parse incoming JSON frame → deserialize to `ClientMessage` union → route to `_handle_subscribe()`, `_handle_unsubscribe()`, `_handle_list_subscriptions()`; send `subscription_confirmed`/`subscription_error`/`subscription_removed`/`subscription_list` responses; increment `malformed_message_count` on parse failure; notify `KafkaFanout.ensure_consuming()` for newly needed topics
- [x] T015 [P] [US2] Write unit tests for `SubscriptionRegistry` topic refcount logic in `apps/control-plane/tests/unit/test_ws_hub_subscription.py`: subscribe/unsubscribe/get_subscribers, topic refcount 0→1→0, multi-connection same channel, unsubscribe_all on disconnect
- [x] T016 [US2] Write integration tests for subscription management in `apps/control-plane/tests/integration/test_ws_subscription_flow.py`: subscribe to workspace channel (authorized) → confirmed; subscribe to execution in wrong workspace → `subscription_error` unauthorized; unsubscribe → `subscription_removed`; list_subscriptions → returns execution + attention; subscribe with invalid channel name → `subscription_error` invalid_channel; attempt to unsubscribe auto-subscribed attention → `subscription_error` cannot_unsubscribe_auto

**Checkpoint**: US2 complete — full subscribe/unsubscribe/list cycle working with authorization checks.

---

## Phase 5: User Story 3 — Event Fan-Out from Message Backbone (Priority: P1)

**Goal**: `KafkaFanout` dynamically starts/stops Kafka topic consumers based on active subscriptions and delivers events to subscribed clients via their `asyncio.Queue`.

**Independent Test**: Two clients subscribe to same execution channel → produce event → both receive it. Client unsubscribes from last subscription on a topic → verify consumer stops (zero refcount). Produce event for different resource → neither client receives it.

- [x] T017 [US3] Implement `KafkaFanout` service in `apps/control-plane/src/platform/ws_hub/fanout.py`: `start()` / `stop()` lifecycle, `ensure_consuming(topics)` → starts `AIOKafkaConsumer` per new topic with consumer group `ws-hub-{hostname}-{pid}`, `release_topics(topics)` → stops consumers when refcount reaches zero, `_consumer_loop(topic)` → polls events + calls `_route_event(topic, raw_message)`
- [x] T018 [US3] Implement `_route_event()` in `apps/control-plane/src/platform/ws_hub/fanout.py`: parse raw Kafka message as `EventEnvelope` dict, resolve matching `(channel, resource_id)` pairs from topic via reverse lookup on `CHANNEL_TOPIC_MAP` + envelope correlation fields, call `SubscriptionRegistry.get_subscribers(channel, resource_id)`, for each subscriber connection enqueue `EventMessage` to `conn.send_queue` via `put_nowait` (non-blocking; drop + increment `conn.dropped_count` if full)
- [x] T019 [US3] Implement `ConnectionWriter` coroutine in `apps/control-plane/src/platform/ws_hub/writer.py`: `async def run(conn)` loop — `await conn.send_queue.get()`, if `conn.dropped_count > 0` send `EventsDroppedMessage` first then reset counter, serialize event to JSON and send via `conn.websocket.send_text()`, exit when `conn.closed` is set
- [x] T020 [P] [US3] Write unit tests for `KafkaFanout` routing logic in `apps/control-plane/tests/unit/test_ws_hub_fanout.py`: mock `AIOKafkaConsumer`, verify `_route_event()` delivers to correct subscribers, verify non-matching events not delivered, verify multi-subscriber fan-out, verify topic consumer start/stop on refcount
- [x] T021 [US3] Write integration tests for event fan-out in `apps/control-plane/tests/integration/test_ws_fanout_flow.py`: connect 2 clients subscribe to same channel → produce event → both receive within 500ms; connect client to channel A only → produce channel B event → not received; connect 0 clients → verify topic not consumed (SC-010)

**Checkpoint**: US3 complete — real Kafka events flowing to subscribed WebSocket clients.

---

## Phase 6: User Story 4 — Visibility and Authorization Filtering (Priority: P1)

**Goal**: Every event delivery checks that the client's current workspace memberships authorize seeing the event. Membership changes propagate within 10 seconds.

**Independent Test**: Subscribe to workspace A channel → events arrive. Get removed from workspace A (produce `workspaces.membership.removed` event) → within 10s events stop. Subscribe to execution in workspace B (not a member) → subscription rejected.

- [x] T022 [US4] Implement `VisibilityFilter.is_visible()` in `apps/control-plane/src/platform/ws_hub/visibility.py`: extract `workspace_id` from `envelope["correlation"]["workspace_id"]`; if `None` (non-workspace-scoped event) → allow; if `workspace_id in conn.workspace_ids` → allow; else → deny
- [x] T023 [US4] Wire `VisibilityFilter.is_visible()` check into `KafkaFanout._route_event()` in `apps/control-plane/src/platform/ws_hub/fanout.py`: after looking up subscribers, filter out connections where `visibility_filter.is_visible(envelope, conn)` returns False; events failing visibility silently dropped (not counted as backpressure drops)
- [x] T024 [US4] Implement workspace membership refresh in `apps/control-plane/src/platform/ws_hub/fanout.py` + `visibility.py`: consume `workspaces.events` topic (already consumed for workspace channel subscriptions), detect `workspaces.membership.added` / `workspaces.membership.removed` event types, call `workspaces_service.get_user_workspace_ids(user_id)` to refresh `conn.workspace_ids` for all connections belonging to affected `user_id`
- [x] T025 [P] [US4] Write unit tests for `VisibilityFilter` in `apps/control-plane/tests/unit/test_ws_hub_visibility.py`: workspace-scoped event (member) → visible; workspace-scoped event (non-member) → not visible; non-workspace-scoped event → visible; workspace_id None → visible
- [x] T026 [US4] Write integration tests for visibility enforcement in `apps/control-plane/tests/integration/test_ws_visibility_flow.py`: user in workspace A → workspace A events arrive; produce `workspaces.membership.removed` → workspace A events stop within 10s (SC-005); subscribe to execution in workspace B (not a member) → subscription_error unauthorized

**Checkpoint**: US4 complete — zero unauthorized event delivery; membership changes propagate within 10s.

---

## Phase 7: User Story 5 — Attention Channel for Agent-Initiated Urgency (Priority: P2)

**Goal**: Each connection is automatically subscribed to `attention:{user_id}`. Attention events from `interaction.attention` are filtered by `target_id` and delivered exclusively to the targeted user.

**Independent Test**: Connect → welcome message contains `attention:{user_id}` in `auto_subscriptions`. Produce attention event with `target_id = user_id` → arrives within 500ms. Produce attention event with different `target_id` → not received.

- [x] T027 [US5] Implement attention auto-subscription in `apps/control-plane/src/platform/ws_hub/router.py`: after creating `WebSocketConnection`, call `_auto_subscribe_attention(conn)` which adds `Subscription(channel=ChannelType.ATTENTION, resource_id=str(user_id), auto=True)` to `conn.subscriptions` + `SubscriptionRegistry`, notifies `KafkaFanout.ensure_consuming(["interaction.attention"])`; include resulting `auto_subscriptions` list in `ConnectionEstablishedMessage`
- [x] T028 [US5] Implement attention event filtering in `apps/control-plane/src/platform/ws_hub/fanout.py`: in `_route_event()` for `interaction.attention` topic, extract `envelope["payload"]["target_id"]`; only deliver to connections where `sub.resource_id == target_id` (i.e., `SubscriptionRegistry.get_subscribers(ChannelType.ATTENTION, target_id)`)
- [x] T029 [US5] Write integration tests for attention channel in `apps/control-plane/tests/integration/test_ws_attention_flow.py`: connect user A → attention auto-subscribed; produce attention event targeting user A → user A receives within 500ms; produce attention event targeting user B → user A does not receive; verify `channel == "attention"` and payload contains `source_agent_fqn`, `urgency_level`, `context_summary`; verify attention event does not appear on alerts channel

**Checkpoint**: US5 complete — attention events delivered exclusively to targeted users within 500ms.

---

## Phase 8: User Story 6 — Backpressure and Slow Client Handling (Priority: P2)

**Goal**: When a client's `asyncio.Queue` fills up, the oldest event is dropped and a counter is incremented. When the client catches up, an `events_dropped` notification is sent before the next real event.

**Independent Test**: Connect client, subscribe to high-volume channel. Pause client reading. Produce 1,001 events (1 more than buffer). Verify gateway does not crash. Resume reading → first message is `events_dropped` with count ≥ 1. Verify other connected clients were not delayed.

- [x] T030 [US6] Implement drop-oldest backpressure in `apps/control-plane/src/platform/ws_hub/fanout.py` `_enqueue()` helper: attempt `conn.send_queue.put_nowait(event_msg)` — on `asyncio.QueueFull`, call `conn.send_queue.get_nowait()` to discard oldest, then `conn.send_queue.put_nowait(event_msg)`, increment `conn.dropped_count`
- [x] T031 [US6] Implement `EventsDroppedMessage` send in `apps/control-plane/src/platform/ws_hub/writer.py` `ConnectionWriter.run()`: before sending the next queued event, check `if conn.dropped_count > 0` → send `EventsDroppedMessage(count=conn.dropped_count, dropped_at=utcnow())` → reset `conn.dropped_count = 0` → then send the actual event
- [x] T032 [P] [US6] Write unit tests for backpressure queue logic in `apps/control-plane/tests/unit/test_ws_hub_backpressure.py`: queue at maxsize → enqueue new item → oldest dropped, count=1; enqueue 5 more → count=5; ConnectionWriter sends events_dropped before event; dropped_count resets to 0 after notification sent
- [x] T033 [US6] Write integration tests for slow client backpressure in `apps/control-plane/tests/integration/test_ws_backpressure_flow.py`: two clients (A slow, B normal) subscribe same channel → produce 1,100 events → B receives all events without delay; A catches up → receives `events_dropped` first → A and B continue receiving new events; gateway memory stable (no unbounded growth)

**Checkpoint**: US6 complete — slow clients drop events without affecting other clients; dropped count notified on catchup.

---

## Phase 9: User Story 7 — Graceful Connection Lifecycle (Priority: P3)

**Goal**: Stale connections detected via heartbeat timeout; server shutdown sends close frames to all clients; malformed message abuse closes connection; clean and unclean disconnect both clean up subscriptions.

**Independent Test**: Kill client network → server closes connection within 30s (heartbeat timeout). Send 11 malformed messages → connection closed with code 4400. Trigger `ws_main.py` shutdown → all clients receive close frame 1001 before process exits.

- [x] T034 [US7] Implement `ConnectionHeartbeat` coroutine in `apps/control-plane/src/platform/ws_hub/heartbeat.py`: `async def run(conn)` — every `WS_HEARTBEAT_INTERVAL_SECONDS` send WebSocket ping via `conn.websocket.send_bytes(b"")` (Starlette ping); update `conn.last_pong_at` on pong frame receipt; if `(utcnow() - conn.last_pong_at).seconds > WS_HEARTBEAT_TIMEOUT_SECONDS` close connection with code 1001; exit when `conn.closed` is set
- [x] T035 [US7] Implement session invalidation in `apps/control-plane/src/platform/ws_hub/fanout.py`: consume `auth.events` topic alongside other active topics; on `auth.session.invalidated` event, call `ConnectionRegistry.get_by_user_id(user_id)` and close each matching connection with code 4401
- [x] T036 [US7] Implement graceful shutdown in `apps/control-plane/entrypoints/ws_main.py` lifespan shutdown: iterate `ConnectionRegistry.all()`, send close frame (code 1001, reason `"server-shutting-down"`) to each connection, set `conn.closed`, await all writer/heartbeat tasks to complete (asyncio timeout: 5s), then call `KafkaFanout.stop()` to drain Kafka consumers
- [x] T037 [US7] Implement malformed message abuse protection in `apps/control-plane/src/platform/ws_hub/router.py`: on JSON parse failure or unknown `type` field, send `ErrorMessage(code="protocol_violation")`, increment `conn.malformed_message_count`; if `>= WS_MAX_MALFORMED_MESSAGES` close connection with code 4400; also handle clean disconnect (WebSocket disconnect exception → `ConnectionRegistry.remove()` + `SubscriptionRegistry.unsubscribe_all()`)
- [x] T038 [US7] Write integration tests for connection lifecycle in `apps/control-plane/tests/integration/test_ws_lifecycle_flow.py`: clean disconnect → subscriptions cleaned up within 1s; send 11 malformed messages → connection closed code 4400; trigger SIGTERM → all clients receive close 1001; produce `auth.session.invalidated` event → connection closed code 4401; reconnect after shutdown → can re-subscribe

**Checkpoint**: US7 complete — all lifecycle scenarios handled; stale connections cleaned up; graceful shutdown working.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Coverage audit, linting, Kubernetes deployment, and observability.

- [x] T039 [P] Run `ruff check . --fix` and `mypy --strict apps/control-plane/src/platform/ws_hub/` — fix all type errors and linting issues in `apps/control-plane/src/platform/ws_hub/`
- [x] T040 [P] Run `pytest apps/control-plane/tests/ -k "ws_hub" --cov=src/platform/ws_hub --cov-report=term` — ensure coverage ≥ 95%; add unit tests for any gaps in `apps/control-plane/tests/unit/`
- [x] T041 [P] Add `ws-hub` Kubernetes Helm Deployment in `deploy/helm/control-plane/templates/ws-hub-deployment.yaml`: 2 replicas, port 8001, `terminationGracePeriodSeconds: 30`, env vars `WS_CLIENT_BUFFER_SIZE`/`WS_HEARTBEAT_INTERVAL_SECONDS`/`WS_HEARTBEAT_TIMEOUT_SECONDS`
- [x] T042 [P] Add OpenTelemetry instrumentation in `apps/control-plane/src/platform/ws_hub/router.py` and `fanout.py`: `ws_hub.connections.active` gauge (inc/dec on connect/disconnect), `ws_hub.events.delivered` counter, `ws_hub.events.dropped` counter, `ws_hub.event_delivery_latency` histogram (Kafka produced_at → gateway_received_at delta)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1–US4 (Phases 3–6)**: All depend on Phase 2; US2 depends on US1 (needs ConnectionRegistry); US3 depends on US2 (needs SubscriptionRegistry); US4 depends on US3 (wraps fan-out with visibility)
- **US5–US6 (Phases 7–8)**: Depend on US3 fan-out infrastructure; can proceed in parallel after Phase 5
- **US7 (Phase 9)**: Depends on US1 (connection lifecycle) — can start after Phase 3
- **Polish (Phase 10)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — independent
- **US2 (P1)**: After US1 — needs `ConnectionRegistry` and established connection handler
- **US3 (P1)**: After US2 — needs `SubscriptionRegistry` for routing
- **US4 (P1)**: After US3 — wraps `_route_event()` with visibility check
- **US5 (P2)**: After US3 — attention is a special fan-out path
- **US6 (P2)**: After US3 — backpressure is implemented in `ConnectionWriter` + fan-out enqueue
- **US7 (P3)**: After US1 — heartbeat and shutdown use `ConnectionRegistry`

### Parallel Opportunities

- T004, T005, T006 (Phase 2) — parallel, different files
- T007, T010 (Phase 3) — parallel (dataclass + unit test)
- T012, T015 (Phase 4) — parallel (SubscriptionRegistry + unit test)
- T013, T015 (Phase 4) — T013 must complete before T014 dispatch wiring
- T020, T025 (Phase 6) — parallel (unit test + implementation)
- T039, T040, T041, T042 (Phase 10) — all parallel

---

## Parallel Example: Phase 2 (Foundational)

```bash
# All three foundational tasks are in different files — run in parallel:
Task T004: "Implement ChannelType enum + CHANNEL_TOPIC_MAP in subscription.py"
Task T005: "Implement Pydantic WS protocol schemas in schemas.py"
Task T006: "Implement WebSocketError hierarchy in exceptions.py"
```

## Parallel Example: User Story 3 (Fan-Out)

```bash
# Unit tests and implementation of different components:
Task T020: "Write unit tests for KafkaFanout routing in test_ws_hub_fanout.py"  # [P] with T017
Task T017: "Implement KafkaFanout service in fanout.py"
# T018 depends on T017, T019 is independent:
Task T019: "Implement ConnectionWriter coroutine in writer.py"
```

---

## Implementation Strategy

### MVP First (US1–US3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (authenticated connections)
4. Complete Phase 4: US2 (subscription management)
5. Complete Phase 5: US3 (event fan-out)
6. **STOP and VALIDATE**: WebSocket gateway delivers real events to subscribed clients
7. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 → authenticated connections working
3. US2 → subscribe/unsubscribe/list working
4. US3 → events flowing (MVP fan-out, no visibility yet)
5. US4 → add visibility filtering (security-hardened fan-out) ← **SC-003 met here**
6. US5 → attention channel (agent urgency signals)
7. US6 → backpressure (production stability)
8. US7 → graceful lifecycle (operations-ready)

---

## Notes

- **No SQLAlchemy/Alembic**: ws_hub is stateless — all state is in-memory, no DB migration needed
- **In-process service calls**: `auth_service.validate_token()` and `workspaces_service.get_user_workspace_ids()` are in-process (not REST calls)
- **Consumer group uniqueness**: `ws-hub-{hostname}-{pid}` computed at startup in `ws_main.py` — each instance fully independent
- **Visibility scope**: `CHANNEL_TOPIC_MAP` governs Kafka consumption; `VisibilityFilter` governs event delivery — two separate layers
- **Attention is always active**: `interaction.attention` topic consumer starts on first connection (attention auto-sub) and only stops when last client disconnects
- [P] tasks = different files, no dependencies between them
- Commit after each checkpoint to preserve working increments
