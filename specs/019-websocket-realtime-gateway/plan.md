# Implementation Plan: WebSocket Real-Time Gateway

**Branch**: `019-websocket-realtime-gateway` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/019-websocket-realtime-gateway/spec.md`

## Summary

Build the `ws_hub/` bounded context within `apps/control-plane/src/platform/` as the `ws-hub` runtime profile. This covers authenticated WebSocket connections (JWT validation on upgrade), in-memory subscription management (11 channel types), dynamic Kafka topic consumption (per-instance consumer group, zero-waste — only consume topics with active subscribers), event fan-out with asyncio.Queue backpressure per client, workspace-scoped visibility filtering (via workspaces service in-process interface), attention channel auto-subscription on connect (consuming `interaction.attention`, filtered by target_id), heartbeat/ping-pong for stale connection cleanup, and graceful shutdown with close-frame broadcast.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+ (WebSocket), Pydantic v2, aiokafka 0.11+, PyJWT 2.x (RS256 token validation at upgrade)  
**Storage**: None — all connection/subscription state is in-memory (no SQLAlchemy, no Alembic, no database tables)  
**Testing**: pytest 8.x + pytest-asyncio  
**Target Platform**: Linux server, Kubernetes `platform-control` namespace, `ws-hub` runtime profile  
**Project Type**: WebSocket hub module within modular monolith control plane  
**Performance Goals**: 5,000 concurrent connections per instance; event delivery < 500ms (Kafka → client); subscription operations < 100ms  
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; no cross-boundary DB access; no in-memory cache for shared state (per-connection state is process-local, not shared)  
**Scale/Scope**: 7 user stories, 20 FRs, 10 SCs, 11 channel types, 11 Kafka topics consumed, 0 database tables

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated; WebSocket via Starlette built-in |
| Pydantic v2 for all schemas | PASS | §2.1 mandated; WS protocol message schemas |
| All code async | PASS | Coding conventions: "All code is async" |
| SQLAlchemy 2.x async only | N/A | No DB access — ws_hub is stateless (in-memory) |
| Alembic for schema changes | N/A | No schema changes — no database tables |
| Bounded context structure | PASS | ws_hub/ package with router, connection, subscription, fanout, writer, heartbeat, visibility, schemas, exceptions, dependencies |
| No cross-boundary DB access | PASS | §IV — ws_hub reads workspace memberships via in-process workspaces_service interface only; auth validation via in-process auth_service |
| Kafka for async events (not DB polling) | PASS | §III — all event delivery via aiokafka consumers; no polling |
| Canonical EventEnvelope | PASS | Events delivered as-is from EventEnvelope (feature 013); no transformation |
| CorrelationContext everywhere | PASS | EventEnvelope correlation context passes through unchanged to client |
| Repository pattern | N/A | No persistent storage — in-memory registries (ConnectionRegistry, SubscriptionRegistry) |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | N/A | No secrets in this context; JWT validated in-process |
| No full-text search in PostgreSQL | N/A | No search operations |
| No vectors in PostgreSQL | N/A | No vector operations |
| Zero-trust default visibility | PASS | §IX — subscription authorization checks workspace membership; events filtered by workspace scope before delivery |
| Goal ID as first-class correlation | PASS | §X — GID passes through in EventEnvelope.correlation; ws_hub does not strip or modify it |
| Attention pattern (§XIII) | PASS | §XIII — dedicated `interaction.attention` topic consumer; auto-subscribed channel per user; distinct from `monitor.alerts` |
| Dynamic consumption (FR-020) | PASS | KafkaFanout tracks topic refcounts; consumers started/stopped when subscriptions go 0→1 and 1→0 |
| Per-instance consumer group | PASS | Consumer group ID: `ws-hub-{hostname}-{pid}` — each instance independently consumes all events |
| Redis not used directly | PASS | No Redis dependency in ws_hub; session validation delegated to auth_service (which may use Redis internally) |

**All 23 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/019-websocket-realtime-gateway/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 decisions (13 decisions)
├── data-model.md        # Phase 1 — in-memory models, protocol schemas, service classes
├── quickstart.md        # Phase 1 — run/test guide
├── contracts/
│   └── ws-protocol.md   # WebSocket message protocol contracts
└── tasks.md             # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── entrypoints/
│   └── ws_main.py                         # ws-hub uvicorn entrypoint (port 8001)
└── src/platform/
    └── ws_hub/
        ├── __init__.py
        ├── router.py                      # FastAPI WebSocket route: GET /ws
        ├── connection.py                  # WebSocketConnection dataclass + ConnectionRegistry
        ├── subscription.py                # Subscription dataclass + SubscriptionRegistry + ChannelType enum + CHANNEL_TOPIC_MAP
        ├── fanout.py                      # KafkaFanout — dynamic topic consumers + event routing
        ├── writer.py                      # ConnectionWriter — per-connection send coroutine
        ├── heartbeat.py                   # ConnectionHeartbeat — ping/pong per connection
        ├── visibility.py                  # VisibilityFilter — workspace-scoped event filtering
        ├── schemas.py                     # Pydantic WS protocol message schemas (all message types)
        ├── exceptions.py                  # SubscriptionAuthError, ProtocolViolationError, etc.
        └── dependencies.py                # FastAPI DI: get_connection_registry, get_subscription_registry, get_fanout

tests/
├── unit/
│   ├── test_ws_hub_connection.py          # ConnectionRegistry, WebSocketConnection state
│   ├── test_ws_hub_subscription.py        # SubscriptionRegistry topic refcount logic
│   ├── test_ws_hub_visibility.py          # VisibilityFilter workspace scope checks
│   ├── test_ws_hub_schemas.py             # Pydantic message parsing + validation
│   └── test_ws_hub_backpressure.py        # Queue drop logic, events_dropped counter
└── integration/
    ├── test_ws_connection_flow.py         # Auth accept/reject, welcome message, attention auto-sub
    ├── test_ws_subscription_flow.py       # Subscribe/unsubscribe/list, authz rejection
    ├── test_ws_fanout_flow.py             # Kafka event → client delivery, multi-client fan-out
    ├── test_ws_visibility_flow.py         # Membership change → event stop within 10s
    ├── test_ws_attention_flow.py          # Attention event → target user, not other users
    ├── test_ws_backpressure_flow.py       # Slow client drops + events_dropped notification
    └── test_ws_lifecycle_flow.py          # Heartbeat stale detection, graceful shutdown
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/ws_hub/` package with all module stubs (`__init__.py` + empty files)
- Create `entrypoints/ws_main.py`: FastAPI app factory for ws-hub profile (mounts `/ws` route only, includes lifespan for KafkaFanout startup/shutdown)
- Add ws-hub settings to `PlatformSettings`: `WS_CLIENT_BUFFER_SIZE`, `WS_HEARTBEAT_INTERVAL_SECONDS`, `WS_HEARTBEAT_TIMEOUT_SECONDS`, `WS_MAX_MALFORMED_MESSAGES`, `WS_CONSUMER_GROUP_ID` (auto-generated)

### Phase 2 — US1: Authenticated WebSocket Connection
- `schemas.py`: `ConnectionEstablishedMessage`, `ErrorMessage` + base `ClientMessage` union
- `exceptions.py`: `SubscriptionAuthError`, `ProtocolViolationError`, `WebSocketGatewayError`
- `connection.py`: `WebSocketConnection` dataclass + `ConnectionRegistry` class
- `router.py`: `GET /ws` endpoint — JWT validation on upgrade (via `auth_service.validate_token()`), extract user_id + workspace_ids, create `WebSocketConnection`, send `connection_established`, launch writer + heartbeat tasks
- `dependencies.py`: `get_connection_registry()`, `get_fanout()` DI factories
- Unit test: `test_ws_hub_connection.py` (ConnectionRegistry CRUD)
- Integration test: `test_ws_connection_flow.py` (valid/invalid token, session expiry close)

### Phase 3 — US2: Subscription Management
- `subscription.py`: `ChannelType` enum, `CHANNEL_TOPIC_MAP`, `Subscription` dataclass, `SubscriptionRegistry` class
- `schemas.py`: Add `SubscribeMessage`, `UnsubscribeMessage`, `ListSubscriptionsMessage`, `SubscriptionConfirmedMessage`, `SubscriptionErrorMessage`, `SubscriptionRemovedMessage`, `SubscriptionListMessage`
- `visibility.py`: `VisibilityFilter.authorize_subscription()` — checks resource workspace membership before confirming subscription
- `router.py`: Message dispatch loop — parse incoming JSON, route to subscribe/unsubscribe/list handlers
- Unit test: `test_ws_hub_subscription.py` (topic refcount logic, channel key generation)
- Integration test: `test_ws_subscription_flow.py`

### Phase 4 — US3 + US4: Event Fan-Out + Visibility Filtering
- `fanout.py`: `KafkaFanout` service — per-topic aiokafka consumers with unique consumer group, `_route_event()` matching events to subscribers via `SubscriptionRegistry`, dynamic consumer start/stop on topic refcount 0↔1
- `writer.py`: `ConnectionWriter` coroutine — reads from `send_queue`, sends `EventMessage` JSON frames, sends `EventsDroppedMessage` when `dropped_count > 0`
- `visibility.py`: `VisibilityFilter.is_visible()` — workspace_id extraction from EventEnvelope, membership check against `conn.workspace_ids`, membership refresh on `workspaces.events` membership events
- `schemas.py`: Add `EventMessage`, `EventsDroppedMessage`
- Unit test: `test_ws_hub_visibility.py` + `test_ws_hub_backpressure.py`
- Integration test: `test_ws_fanout_flow.py` + `test_ws_visibility_flow.py`

### Phase 5 — US5 + US6: Attention Channel + Backpressure
- `subscription.py`: Auto-subscribe logic for `attention:{user_id}` — called from `router.py` after connection established
- `fanout.py`: Attention event filtering — `interaction.attention` consumer filters by `payload.target_id == resource_id`
- `schemas.py`: Update `ConnectionEstablishedMessage` to include `auto_subscriptions` list
- Backpressure drop logic in `writer.py`: when `send_queue` is full, `get_nowait()` discard + increment `conn.dropped_count` + `put_nowait(new_event)`
- Integration test: `test_ws_attention_flow.py` + `test_ws_backpressure_flow.py`

### Phase 6 — US7: Graceful Connection Lifecycle
- `heartbeat.py`: `ConnectionHeartbeat` coroutine — WebSocket ping every `WS_HEARTBEAT_INTERVAL_SECONDS`, close on pong timeout
- `router.py`: Handle session invalidation events from `auth.events` (close affected connections with code 4401); handle malformed message counting (close after `WS_MAX_MALFORMED_MESSAGES`)
- `ws_main.py`: Lifespan shutdown — iterate `ConnectionRegistry.all()`, send close frame (1001 Going Away), await cleanup with 5s timeout
- Integration test: `test_ws_lifecycle_flow.py`

### Phase 7 — Polish & Cross-Cutting Concerns
- Full test coverage audit (unit + integration ≥ 95%)
- ruff + mypy --strict clean run
- Kubernetes Helm chart additions: ws-hub Deployment (port 8001, terminationGracePeriodSeconds: 30, env vars)
- OpenTelemetry spans: connection duration, subscription count gauge, event delivery latency histogram

## Key Decisions (from research.md)

1. **No SQLAlchemy/repository**: ws_hub is stateless (no DB) — all state in-memory per process
2. **Per-instance consumer group**: `ws-hub-{hostname}-{pid}` — every instance independently consumes all events
3. **Dynamic topic subscription**: KafkaFanout tracks refcounts per topic; zero-waste consumption (FR-020)
4. **asyncio.Queue backpressure**: Per-connection bounded queue; drop oldest + increment counter; send `events_dropped` on catchup
5. **Workspace membership cache**: Cached on `WebSocketConnection.workspace_ids`; event-driven refresh from `workspaces.events` membership events
6. **Attention auto-subscription**: Auto-subscribed on connect to `attention:{user_id}`; `interaction.attention` topic filtered by `target_id`
7. **Starlette native WebSocket**: No additional WS library; uses FastAPI/Starlette built-in WebSocket support
8. **JSON protocol**: Type-discriminated JSON messages; `EventEnvelope` passed through unchanged in `event` message `payload`
9. **WebSocket ping/pong heartbeat**: RFC 6455 native ping/pong; stale connection cleanup within configurable timeout
10. **Session invalidation via Kafka**: Consumes `auth.events` for `auth.session.invalidated`; closes connections with code 4401
11. **Channel-to-topic map**: `CHANNEL_TOPIC_MAP` dict in `subscription.py`; each channel type maps to 1-2 Kafka topics with resource_id filter
12. **Graceful shutdown via lifespan**: SIGTERM → lifespan shutdown → broadcast close frame to all clients → stop Kafka consumers
13. **No Redis in ws_hub**: Session validation delegated in-process to auth_service; ws_hub has zero Redis dependency
