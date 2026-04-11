# Feature Specification: WebSocket Real-Time Gateway

**Feature Branch**: `019-websocket-realtime-gateway`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement authenticated WebSocket gateway with Kafka fan-out, subscription management for all channel types, visibility filtering, and backpressure handling."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Authenticated WebSocket Connection (Priority: P1)

A user opens the platform's web application and the frontend establishes a WebSocket connection to the real-time gateway. The connection request includes the user's authentication token. The gateway validates the token before completing the upgrade. If the token is valid, the connection is established and the user receives a confirmation message. If the token is invalid or expired, the connection is rejected immediately. When the user's session expires or is invalidated, the existing WebSocket connection is closed gracefully with a reason code indicating authentication failure.

**Why this priority**: No real-time feature works without an authenticated connection. This is the absolute foundation — every other user story depends on a live, authenticated WebSocket.

**Independent Test**: Attempt WebSocket connection with a valid token — verify the connection succeeds and a welcome/confirmation message is received. Attempt connection with an invalid token — verify the connection is rejected. Attempt connection with an expired token — verify rejection. Establish a valid connection, then invalidate the session — verify the connection is closed with an appropriate reason code.

**Acceptance Scenarios**:

1. **Given** a user with a valid authentication token, **When** they initiate a WebSocket connection, **Then** the connection is established and the user receives a connection-established confirmation within 1 second
2. **Given** a user with an invalid or expired token, **When** they attempt a WebSocket connection, **Then** the connection is rejected before upgrade with an appropriate error
3. **Given** an established WebSocket connection, **When** the user's session is invalidated, **Then** the connection is closed within 5 seconds with a session-expired reason code
4. **Given** a user with a valid token, **When** they connect, **Then** the gateway associates the connection with the user's identity and workspace memberships for subsequent authorization checks

---

### User Story 2 — Channel Subscription Management (Priority: P1)

Once connected, a user subscribes to one or more real-time channels to receive specific event streams. Channels correspond to platform concepts: executions, interactions, conversations, workspaces, fleets, reasoning traces, self-correction events, simulations, test results, and system alerts. The user sends a subscribe message with the channel type and resource identifier (e.g., subscribe to execution events for execution ID X). The gateway validates that the user is authorized to see events for that resource (workspace scope and role checks). On success, the user starts receiving events from that channel. The user can unsubscribe from channels and query their active subscriptions.

**Why this priority**: Subscription management determines which events a user receives — it is inseparable from the connection itself. Without subscriptions, the WebSocket delivers nothing.

**Independent Test**: Connect with valid token. Subscribe to a workspace channel — verify subscription confirmation. Subscribe to an execution channel — verify confirmation. Send a subscribe message for a resource the user has no access to — verify rejection. Unsubscribe from the workspace channel — verify unsubscription confirmation. List active subscriptions — verify the execution channel is listed and the workspace channel is not.

**Acceptance Scenarios**:

1. **Given** an authenticated WebSocket connection, **When** the user sends a subscribe message for a valid channel, **Then** the subscription is confirmed and the user begins receiving events for that channel
2. **Given** an authenticated connection, **When** the user subscribes to a channel they are not authorized to access, **Then** the subscription is rejected with a clear error (unauthorized or resource not found)
3. **Given** an active subscription, **When** the user sends an unsubscribe message, **Then** the subscription is removed and no further events from that channel are delivered
4. **Given** multiple active subscriptions, **When** the user requests a subscription list, **Then** all currently active subscriptions are returned with their channel types and resource identifiers
5. **Given** an active subscription to an execution channel, **When** an event occurs for that execution, **Then** the event is delivered to the user within 500 milliseconds of being produced

---

### User Story 3 — Event Fan-Out from Message Backbone (Priority: P1)

The gateway consumes events from the platform's event backbone and delivers them to connected clients based on their active subscriptions. Each gateway instance consumes events relevant to the subscriptions it manages (dynamic consumption based on active subscriptions, not all events globally). When an event arrives, the gateway matches it to all clients subscribed to the corresponding channel and delivers the event to each of them. The fan-out must handle thousands of concurrent connections efficiently.

**Why this priority**: Fan-out is the core value of the gateway — it bridges backend event streams to frontend WebSocket clients. Without it, subscriptions are meaningless.

**Independent Test**: Connect two clients and subscribe both to the same execution channel. Produce an execution event in the backend. Verify both clients receive the event. Produce an event for a different execution — verify neither client receives it (not subscribed). Connect a third client to a workspace channel. Produce a workspace event — verify only the workspace-subscribed client receives it.

**Acceptance Scenarios**:

1. **Given** multiple clients subscribed to the same channel, **When** an event is produced for that channel, **Then** all subscribed clients receive the event
2. **Given** a client subscribed to channel A, **When** an event is produced for channel B, **Then** the client does not receive the event
3. **Given** an event produced in the backend, **When** a subscribed client is connected, **Then** the event is delivered within 500 milliseconds of production
4. **Given** 1,000 concurrent connections with mixed subscriptions, **When** events are produced across multiple channels, **Then** all events are delivered correctly to the right subscribers without cross-contamination
5. **Given** a gateway instance with zero subscriptions for a particular topic, **When** events are produced on that topic, **Then** the gateway does not consume those events (no wasted processing)

---

### User Story 4 — Visibility and Authorization Filtering (Priority: P1)

Even after subscription, the gateway applies fine-grained visibility filtering to every event before delivery. A user only sees events they are authorized to access — events are scoped by workspace membership and workspace role. If a user's workspace membership changes (e.g., they are removed from a workspace), events from that workspace stop being delivered even if the subscription is still active. Events that contain data from multiple workspaces are filtered to show only the workspace(s) the user belongs to.

**Why this priority**: Visibility filtering is a security requirement — delivering unauthorized events would violate the zero-trust security model. This must ship with the fan-out to prevent any data leakage.

**Independent Test**: Subscribe a user to a workspace channel they belong to — verify events arrive. Remove the user from the workspace (via membership change) — verify events stop arriving. Subscribe a user to an execution channel — produce an event for an execution in a workspace the user does not belong to — verify the event is not delivered despite the channel subscription.

**Acceptance Scenarios**:

1. **Given** a user subscribed to events in workspace A, **When** the user is removed from workspace A, **Then** events from workspace A stop being delivered within 10 seconds
2. **Given** a user who subscribes to an execution channel, **When** the execution belongs to a workspace the user is not a member of, **Then** the subscription is rejected or events are filtered out
3. **Given** an event with workspace context, **When** it is delivered to a client, **Then** only events matching the client's current workspace memberships are included
4. **Given** a platform administrator, **When** they subscribe to channels, **Then** their visibility is determined by their workspace memberships plus any platform-level overrides

---

### User Story 5 — Attention Channel for Agent-Initiated Urgency (Priority: P2)

The gateway provides a dedicated attention channel that delivers real-time urgent signals from agents to specific users. When an agent signals that it needs human input or peer assistance, the system creates an attention request targeted at a specific user. The gateway delivers this attention request to the targeted user's WebSocket connection via a dedicated attention channel, separate from regular alerts. Attention events carry urgency information, a context summary, the requesting agent's identity, and links to the related execution context. Users can subscribe to their attention channel automatically upon connection.

**Why this priority**: The attention pattern is an important real-time notification mechanism, but the platform functions without it (agents can still operate, they just can't urgently signal users in real time). It builds on the subscription and fan-out infrastructure from US1–US3.

**Independent Test**: Connect a user. Verify an attention subscription is automatically active for that user. Produce an attention event targeted at this user — verify it arrives within 500ms with urgency level, agent identity, and context summary. Produce an attention event targeted at a different user — verify this user does not receive it. Verify attention events are delivered separately from alert-channel events.

**Acceptance Scenarios**:

1. **Given** an authenticated WebSocket connection, **When** the connection is established, **Then** the user is automatically subscribed to their attention channel
2. **Given** an agent that signals attention for user X, **When** the attention event is produced, **Then** user X receives the event via their attention channel within 500 milliseconds
3. **Given** an attention event targeted at user X, **When** user Y is connected, **Then** user Y does not receive the event
4. **Given** an attention event, **When** delivered, **Then** it includes the source agent identity, urgency level, context summary, and correlation identifiers linking to the relevant execution or interaction
5. **Given** a user receiving both attention events and alert events, **When** both arrive, **Then** they are delivered on separate channels so the frontend can render them with distinct priority levels

---

### User Story 6 — Backpressure and Slow Client Handling (Priority: P2)

When a connected client falls behind in consuming events (e.g., due to a slow network or a paused browser tab), the gateway must not allow the per-client send buffer to grow unboundedly. Each client connection has a configurable maximum buffer size. When the buffer is full, the gateway drops the oldest events for that client and optionally sends a "events-dropped" notification indicating how many events were lost. This prevents a single slow client from affecting the performance of other connections or causing the gateway to run out of memory.

**Why this priority**: Backpressure handling is important for production stability but the gateway can function without it at small scale. During development and early deployment, unbounded buffers are tolerable. Backpressure becomes critical under load.

**Independent Test**: Connect a client. Subscribe to a high-volume channel. Pause the client's reading (simulate slow consumer). Produce events rapidly. Verify the gateway does not crash or run out of memory. Verify that when the client resumes, it receives an events-dropped notification indicating the gap. Verify other connected clients continue to receive events without delay.

**Acceptance Scenarios**:

1. **Given** a client with a full send buffer (e.g., 1,000 events queued), **When** a new event arrives for that client, **Then** the oldest event in the buffer is dropped and the new event is queued
2. **Given** a client whose events were dropped, **When** the client catches up, **Then** it receives an events-dropped notification with the count of dropped events
3. **Given** a slow client, **When** its buffer fills up, **Then** other clients' event delivery is not affected
4. **Given** the buffer size, **When** it is configured, **Then** it can be set per-gateway-instance via configuration (not hardcoded)
5. **Given** a client that disconnects and reconnects, **When** it re-subscribes, **Then** it does not receive events from the gap period (no replay — the client must handle catch-up via REST queries)

---

### User Story 7 — Graceful Connection Lifecycle (Priority: P3)

The gateway manages WebSocket connection lifecycle gracefully — handling client disconnection (clean and unexpected), server-initiated shutdown (for deployment rolling updates), and heartbeat/ping-pong for detecting stale connections. When the gateway is shutting down, it sends a close message to all connected clients with a "server-shutting-down" reason code, giving the frontend time to reconnect to another instance. Periodic heartbeats detect and clean up stale connections that failed to disconnect properly (e.g., network failure without TCP FIN).

**Why this priority**: Graceful lifecycle management improves reliability but is not required for core functionality. The gateway can function without heartbeats or graceful shutdown during development.

**Independent Test**: Establish a connection. Disconnect cleanly — verify the server cleans up subscriptions. Kill the client's network — verify the server detects the stale connection within the heartbeat timeout and cleans up. Trigger a server shutdown — verify all clients receive a close frame with shutdown reason. Reconnect after shutdown — verify the client can re-establish and re-subscribe.

**Acceptance Scenarios**:

1. **Given** a client that disconnects cleanly, **When** the server detects the close, **Then** all subscriptions are removed and resources are freed within 1 second
2. **Given** a client whose network fails silently, **When** the heartbeat timeout elapses (configurable, default 30 seconds), **Then** the server closes the connection and cleans up
3. **Given** a server that is shutting down, **When** it initiates graceful shutdown, **Then** all connected clients receive a close frame with a "server-shutting-down" code before the process exits
4. **Given** a client that receives a server-shutting-down close, **When** it reconnects to a different instance, **Then** it can re-establish subscriptions and resume receiving events

---

### Edge Cases

- What happens when a user's token expires during an active WebSocket session? The gateway periodically validates the connection's token (or listens for session invalidation events). When the token expires, the connection is closed with a session-expired reason code. The frontend is expected to refresh the token and reconnect.
- What happens when the event backbone is temporarily unreachable? The gateway retains existing connections and subscriptions. Event delivery pauses. When connectivity resumes, the gateway resumes consuming from the last committed offset. Events produced during the outage may arrive with higher latency but are not lost.
- What happens when a user subscribes to a channel that has no events? The subscription is valid and confirmed. The client simply receives no events until one is produced.
- What happens when two gateway instances have clients subscribed to the same channel? Both instances consume the relevant events independently (separate consumer groups per instance). Each instance delivers events to its own connected clients. No cross-instance coordination is needed for fan-out.
- What happens when a client sends malformed messages? The gateway sends an error response with a clear message describing the protocol violation. The connection is not closed for a single malformed message (to support debugging). Repeated malformed messages (e.g., 10 within 1 minute) close the connection.
- What happens when the buffer limit is set to zero? A buffer size of zero means no buffering — events are delivered synchronously. If the send blocks, the event is dropped immediately. This is a valid but aggressive configuration.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The gateway MUST authenticate users during WebSocket connection upgrade using their authentication token before establishing the connection
- **FR-002**: The gateway MUST reject WebSocket connections with invalid, expired, or missing authentication tokens
- **FR-003**: The gateway MUST support subscribe, unsubscribe, and list-subscriptions operations via WebSocket messages
- **FR-004**: The gateway MUST support subscriptions to the following channel types: execution, interaction, conversation, workspace, fleet, reasoning, correction, simulation, testing, alerts, and attention
- **FR-005**: The gateway MUST validate that the subscribing user is authorized to access the requested channel's resource (workspace membership and role check)
- **FR-006**: The gateway MUST consume events from the event backbone and deliver them to clients based on their active subscriptions
- **FR-007**: Event delivery from production to client MUST occur within 500 milliseconds under normal load
- **FR-008**: The gateway MUST support at least 5,000 concurrent WebSocket connections per instance
- **FR-009**: The gateway MUST apply visibility filtering to every event — events are delivered only if the client is authorized based on current workspace memberships
- **FR-010**: When a user's workspace membership changes, the gateway MUST update its authorization state within 10 seconds
- **FR-011**: The gateway MUST provide a dedicated attention channel per user that delivers agent-initiated attention requests targeted at that user
- **FR-012**: Attention events MUST include source agent identity, urgency level, context summary, and correlation identifiers
- **FR-013**: The attention channel MUST be separate from the alerts channel
- **FR-014**: The gateway MUST implement per-client backpressure with a configurable buffer limit; when the buffer is full, the oldest events are dropped
- **FR-015**: When events are dropped due to backpressure, the gateway MUST send an events-dropped notification to the client when it catches up
- **FR-016**: The gateway MUST implement heartbeat/ping-pong to detect and clean up stale connections within a configurable timeout
- **FR-017**: The gateway MUST support graceful shutdown by sending close frames to all connected clients with a server-shutting-down reason code before the process exits
- **FR-018**: The gateway MUST clean up all subscriptions and resources when a client disconnects (both clean and unexpected disconnections)
- **FR-019**: The gateway MUST automatically subscribe each connected user to their personal attention channel upon connection establishment
- **FR-020**: The gateway MUST NOT consume events from backbone topics that have zero active subscriptions across all connected clients

### Key Entities

- **WebSocketConnection**: A live authenticated connection between a client and the gateway — holds the user's identity, current workspace memberships, active subscriptions, and send buffer state.
- **Subscription**: A client's registration to receive events for a specific channel type and resource identifier (e.g., channel="execution", resource_id="abc-123"). Each subscription maps to one or more event backbone topics.
- **ChannelType**: The category of events a client can subscribe to — determines which backbone topic(s) to consume and how events are filtered. 11 types: execution, interaction, conversation, workspace, fleet, reasoning, correction, simulation, testing, alerts, attention.
- **EventBuffer**: The per-client queue of outbound events awaiting delivery. Has a configurable maximum size. When full, the oldest events are evicted.
- **AttentionEvent**: A special event type targeted at a specific user, carrying urgency and context from an agent that needs human attention. Consumed from a dedicated backbone topic and delivered exclusively to the targeted user's attention channel.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Events produced in the backend are delivered to subscribed WebSocket clients within 500 milliseconds under normal load (up to 5,000 concurrent connections)
- **SC-002**: The gateway supports at least 5,000 concurrent authenticated WebSocket connections per instance without degradation
- **SC-003**: 100% of events are delivered only to authorized clients — zero unauthorized event delivery
- **SC-004**: Unauthorized subscription attempts are rejected within 100 milliseconds
- **SC-005**: When a user's workspace membership is revoked, events from that workspace stop being delivered within 10 seconds
- **SC-006**: Attention events targeted at a specific user reach that user's attention channel within 500 milliseconds
- **SC-007**: A slow client's backpressure does not affect event delivery to other clients — other clients continue to receive events within the 500ms target
- **SC-008**: Stale connections (network failure without clean close) are detected and cleaned up within the heartbeat timeout (default 30 seconds)
- **SC-009**: During graceful shutdown, all connected clients receive a close frame before the process exits
- **SC-010**: The gateway consumes zero events from topics with no active subscriptions — no wasted processing

## Assumptions

- The authentication system (feature 014) provides a mechanism to validate tokens synchronously during WebSocket upgrade and a way to detect session invalidation (either via a Kafka event on `auth.events` or via a short-lived token TTL that the gateway checks periodically).
- The frontend WebSocket client (feature 015, `lib/ws.ts`) handles reconnection with exponential backoff. The gateway does not implement server-side reconnection or event replay — clients must catch up via REST queries after reconnection.
- Each gateway instance runs as a separate process (the `ws-hub` runtime profile from the control plane). Multiple instances can run behind a load balancer. There is no cross-instance state sharing — each instance manages its own connections and subscriptions independently.
- Events are consumed from the existing Kafka topics defined in the constitution's Kafka Topics Registry. The gateway does not create new topics — it reads from `interaction.events`, `workflow.runtime`, `runtime.lifecycle`, `runtime.reasoning`, `runtime.selfcorrection`, `sandbox.events`, `workspace.goal`, `monitor.alerts`, `interaction.attention`, `trust.events`, `evaluation.events`, `simulation.events`, `testing.results`, etc.
- The workspace membership state is either read from the workspaces bounded context (feature 018) via in-process service interface or cached from workspace membership change events on `workspaces.events`. The gateway needs near-real-time (within 10 seconds) awareness of membership changes for visibility filtering.
- The per-client buffer size is configured via an environment variable (e.g., `WS_CLIENT_BUFFER_SIZE`). Default: 1,000 events. This applies uniformly to all clients on a given gateway instance.
- The WebSocket protocol uses JSON messages for the subscribe/unsubscribe/list-subscriptions operations (not a binary protocol). Event payloads are delivered as-is from the canonical event envelope (JSON-serialized).
- The heartbeat timeout is configured via an environment variable (e.g., `WS_HEARTBEAT_TIMEOUT_SECONDS`). Default: 30 seconds. The gateway uses the WebSocket ping/pong mechanism for heartbeat detection.
