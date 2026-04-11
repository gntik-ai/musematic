# Research: WebSocket Real-Time Gateway

**Feature**: 019-websocket-realtime-gateway  
**Date**: 2026-04-11  
**Phase**: Phase 0 — Research & Decisions

## Decision Log

### Decision 1: No SQLAlchemy, No Repository Layer

- **Decision**: The WebSocket gateway has **no database models and no repository layer**. All connection and subscription state is held in-memory within the `ws-hub` process.
- **Rationale**: WebSocket connection state is ephemeral by design. Connections exist only while a client is connected; they are meaningless after a process restart. Persisting this state to PostgreSQL would add write latency on every subscribe/unsubscribe and would need aggressive TTL cleanup. Redis session state already handles the token → user_id lookup during upgrade auth.
- **Alternatives considered**: Redis for connection registry (rejected — adds network hop per fan-out event; in-memory is sufficient for single-instance state); PostgreSQL subscription audit log (rejected — not needed at this phase; auditing subscriptions is a future requirement).
- **Constitution compliance**: §III (dedicated stores — Redis is for hot state, but connection routing is process-local, not shared hot state); §IV (no cross-boundary DB access — no DB access at all).

---

### Decision 2: Per-Instance Unique Kafka Consumer Group

- **Decision**: Each `ws-hub` process gets a **unique Kafka consumer group ID**: `ws-hub-{hostname}-{pid}`. This means every instance independently consumes all events from all topics it subscribes to.
- **Rationale**: A shared consumer group would partition events across instances, so only one instance would receive each event. Since each instance manages its own connections, every instance must see every event to fan it out to its local clients. Per-instance groups achieve this with zero coordination.
- **Alternatives considered**: Shared consumer group with cross-instance forwarding via Redis Pub/Sub (rejected — adds complexity and latency; violates §III "no in-memory caches for shared state" for routing tables); topic-partitioned sticky routing via consistent hashing (rejected — requires sticky load balancer configuration and adds deployment complexity).
- **Constitution compliance**: §III (Kafka for async events, not polling); §I (ws-hub is the `ws-hub` runtime profile of the modular monolith, running independently).

---

### Decision 3: Dynamic Topic Subscription (Zero-Waste Consumption)

- **Decision**: The `KafkaFanout` service dynamically starts and stops topic consumers based on **active subscriptions across all connected clients**. When the last client unsubscribes from a topic, the consumer for that topic is stopped. FR-020 compliance.
- **Rationale**: The gateway may be deployed with no active clients, or clients may only subscribe to a subset of topics. Consuming unused topics wastes CPU and Kafka broker resources. Dynamic subscription enables zero-waste consumption aligned with FR-020.
- **Alternatives considered**: Subscribe to all topics at startup (rejected — wastes resources, violates FR-020); topic pools with idle timeout (rejected — adds complexity without benefit over dynamic on/off).
- **Implementation detail**: `SubscriptionRegistry` maintains a reference count per Kafka topic. When count goes from 0→1, start consumer. When count goes from 1→0, stop consumer.

---

### Decision 4: asyncio.Queue Backpressure Per Connection

- **Decision**: Each `WebSocketConnection` has a dedicated `asyncio.Queue(maxsize=WS_CLIENT_BUFFER_SIZE)`. The fan-out loop puts events into the queue without blocking (`put_nowait`). If the queue is full, the oldest item is dropped (via `get_nowait` discard + `put_nowait`) and a dropped-count counter is incremented. A separate writer coroutine per connection reads from the queue and sends over WebSocket. When the writer catches up and the drop counter is non-zero, it sends an `events_dropped` notification first.
- **Rationale**: `asyncio.Queue` is the idiomatic Python async bounded buffer. Separate producer (fan-out) and consumer (writer) coroutines decouple event ingestion from network send. Dropping oldest (not newest) events gives the client the most recent state — suitable for live monitoring use cases.
- **Alternatives considered**: Drop newest on full queue (rejected — client sees stale state); semaphore-based throttling (rejected — blocks fan-out coroutine and delays other clients); unbounded queue (rejected — violates US6 and FR-014).

---

### Decision 5: Workspace Membership Cache for Visibility Filtering

- **Decision**: On first subscription attempt, the gateway reads the user's workspace IDs via the in-process `workspaces_service.get_user_workspace_ids(user_id)` interface (feature 018). The result is stored on the `WebSocketConnection` object. The cache is **refreshed when `workspaces.events` membership events** (`workspaces.membership.added`, `workspaces.membership.removed`, `workspaces.membership.role_changed`) are consumed for the user's `user_id`.
- **Rationale**: Calling the workspaces service on every event delivery would be too expensive at 5,000 concurrent connections. Caching per connection with event-driven invalidation achieves near-real-time (sub-second) accuracy within the 10-second SC-005 requirement. The workspace membership topic is already consumed for workspace channel subscriptions.
- **Alternatives considered**: Periodic refresh every N seconds (accepted as fallback if no membership event arrives — refresh at most every 30s to catch edge cases); JWT claims embedding workspace IDs (rejected — JWT would need to be re-issued on every membership change, not feasible).

---

### Decision 6: Attention Channel Auto-Subscribed on Connection

- **Decision**: Upon successful connection establishment, the gateway **automatically subscribes each user to `attention:{user_id}`** without the client sending a subscribe message (FR-019). The attention channel consumes from the `interaction.attention` Kafka topic and filters events by `payload.target_id == user_id`.
- **Rationale**: The attention pattern (§XIII) requires zero-friction delivery — an agent-initiated urgency signal must reach the user immediately without the client needing to opt in. The channel is per-user (scoped to `user_id`) so no cross-user leakage is possible.
- **Implementation detail**: The attention subscription uses `resource_id = str(user_id)`. The `interaction.attention` topic consumer applies server-side filtering: only events where `envelope.payload["target_id"] == resource_id` are delivered. This is efficient because attention events are low-volume (each has a specific target_id).

---

### Decision 7: WebSocket Transport via Starlette/FastAPI Native Support

- **Decision**: Use **FastAPI's native WebSocket support** (built on Starlette's `WebSocket` class) for the WebSocket server. No additional WebSocket library needed.
- **Rationale**: FastAPI already includes WebSocket support via Starlette. Adding a separate library (e.g., `websockets`) would duplicate functionality. The `ws-hub` entry point runs the same FastAPI app with only WebSocket routes registered (no REST API routes mounted). This is the `ws-hub` runtime profile.
- **Alternative considered**: Standalone `websockets` library (rejected — unnecessary dependency alongside FastAPI); `socketio` (rejected — complex protocol not needed; plain JSON messages over native WS is sufficient).

---

### Decision 8: WebSocket JSON Protocol Design

- **Decision**: All WebSocket messages use **JSON with a `type` discriminator field**. Control messages (client → server): `subscribe`, `unsubscribe`, `list_subscriptions`. Server response messages: `connection_established`, `subscription_confirmed`, `subscription_error`, `subscription_removed`, `subscription_list`, `event`, `events_dropped`, `error`. The payload in `event` messages is the raw `EventEnvelope` JSON from feature 013.
- **Rationale**: Simple JSON with a type discriminator is readable, debuggable, and compatible with the frontend `WebSocketClient` in `lib/ws.ts` (feature 015) which already implements topic-based subscriptions over plain WS. Binary protocol (MsgPack, protobuf) is premature optimization — JSON is sufficient at 5,000 connections.
- **Design detail**: Channel + resource_id form the subscription key: `{"type": "subscribe", "channel": "execution", "resource_id": "abc-123"}`. For the alerts channel, `resource_id` is the user's user_id. For workspace channel, `resource_id` is the workspace_id.

---

### Decision 9: Heartbeat via WebSocket Ping/Pong (RFC 6455)

- **Decision**: Use **WebSocket native ping/pong frames** (RFC 6455) for heartbeat. The server sends a WebSocket `ping` frame every `WS_HEARTBEAT_INTERVAL_SECONDS` (default 30s). If no `pong` is received within `WS_HEARTBEAT_TIMEOUT_SECONDS` (default 10s), the connection is closed with code 1001 (Going Away).
- **Rationale**: Native WS ping/pong is transparent to application code and handled automatically by most browsers. This avoids a custom application-level heartbeat and keeps the protocol clean. Starlette's `WebSocket` supports `send_bytes` for ping frames via `websocket.send_bytes(b"ping")` or via the underlying WebSocket connection.
- **Implementation detail**: One asyncio task per connection manages heartbeat. The writer task and heartbeat task run concurrently; connection close is signalled via an asyncio `Event`.

---

### Decision 10: Session Invalidation Detection via Kafka

- **Decision**: The gateway consumes the `auth.events` topic and listens for `auth.session.invalidated` events. When received, it looks up all connections for the affected `user_id` and closes them with close code 4401 (custom: session expired).
- **Rationale**: Checking token expiry on every event delivery would add per-event overhead. Periodic token re-validation (e.g., every 60s) misses session revocations (e.g., forced logout). Kafka event on `auth.events` provides near-real-time invalidation. The `auth.events` topic is already a standard topic (feature 014).
- **Edge case**: The access token's JWT expiry time also serves as a fallback. If `auth.events` is delayed, the gateway checks `token.exp` on a background tick (every 60s) and closes expired connections.

---

### Decision 11: Channel-to-Kafka Topic Mapping

- **Decision**: Each channel type maps to one or more Kafka topics:

| Channel | Kafka Topic(s) | Filter |
|---------|---------------|--------|
| `execution` | `workflow.runtime`, `runtime.lifecycle` | `payload.execution_id == resource_id` |
| `interaction` | `interaction.events` | `payload.interaction_id == resource_id` |
| `conversation` | `interaction.events` | `payload.conversation_id == resource_id` |
| `workspace` | `workspaces.events` | `payload.workspace_id == resource_id` |
| `fleet` | `runtime.lifecycle` | `payload.fleet_id == resource_id` |
| `reasoning` | `runtime.reasoning` | `payload.execution_id == resource_id` |
| `correction` | `runtime.selfcorrection` | `payload.execution_id == resource_id` |
| `simulation` | `simulation.events` | `payload.simulation_id == resource_id` |
| `testing` | `testing.results` | `payload.suite_id == resource_id` |
| `alerts` | `monitor.alerts` | `payload.target_id == resource_id` (user_id) |
| `attention` | `interaction.attention` | `payload.target_id == resource_id` (user_id) |

- **Rationale**: Each channel type is a named subscription abstraction over one or more underlying Kafka topics. The filter is applied in the fan-out loop before event delivery. `resource_id` is channel-type-specific — for execution/interaction/workspace channels it is the entity's UUID; for alerts and attention channels it is the user's user_id.

---

### Decision 12: Graceful Shutdown via asyncio Lifespan

- **Decision**: The `ws-hub` FastAPI app uses a **lifespan context manager**. On shutdown signal (SIGTERM from Kubernetes rolling update), the lifespan context exit triggers a graceful shutdown: (1) stop accepting new connections, (2) send WebSocket close frame (code 1001 Going Away, reason "server-shutting-down") to all connected clients, (3) await all connection tasks to complete (with timeout), (4) stop all Kafka consumers.
- **Rationale**: Kubernetes rolling updates send SIGTERM before killing the pod. Clients that receive the close frame with a "server-shutting-down" reason know to reconnect. The frontend `WebSocketClient` in feature 015 already implements reconnection with exponential backoff.
- **Grace period**: Kubernetes `terminationGracePeriodSeconds: 30`. The gateway closes all connections within 5 seconds, then completes cleanup.

---

### Decision 13: No Redis Dependency in ws-hub

- **Decision**: The `ws-hub` profile does **not** use Redis directly for connection routing. Session validation at upgrade time is done by calling the auth service in-process (via `auth_service.validate_token(token)`) — which may internally use Redis for session lookup. The ws-hub itself has no Redis client.
- **Rationale**: Adding Redis as a dependency of the ws-hub for connection state management would require a shared data structure between instances, which conflicts with the per-instance approach (Decision 2). The only Redis-backed operation (session validation) is delegated to the auth bounded context.
- **Implication**: The `ws-hub` runtime profile does not need Redis configuration, simplifying its deployment footprint.
