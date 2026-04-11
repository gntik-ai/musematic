# WebSocket Protocol Contracts: Real-Time Gateway

**Feature**: 019-websocket-realtime-gateway  
**Date**: 2026-04-11  
**Phase**: Phase 1 — Contracts

## Overview

The WebSocket gateway exposes a single endpoint: `ws://<host>/ws` (or `wss://` in production). All messages are JSON-encoded UTF-8 text frames. The protocol is message-based (not streaming): each frame is one complete message.

---

## Connection Establishment

### Endpoint

```
GET /ws
Upgrade: websocket
Connection: Upgrade
Authorization: Bearer <access_token>
```

**OR** via query parameter (for browser clients that cannot set headers):

```
GET /ws?token=<access_token>
```

The `Authorization` header takes precedence. Query parameter is accepted but discouraged.

### Authentication

The gateway validates the JWT during the WebSocket upgrade (HTTP 101 handshake). If validation fails, the connection is rejected with an HTTP error response before the WebSocket upgrade completes:

| Failure | HTTP Response |
|---------|--------------|
| Missing token | 401 Unauthorized |
| Invalid token | 401 Unauthorized |
| Expired token | 401 Unauthorized |
| User suspended/blocked | 403 Forbidden |

### Server Welcome Message

On successful connection, the server immediately sends:

```json
{
  "type": "connection_established",
  "connection_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "server_time": "2026-04-11T14:23:00.000Z",
  "auto_subscriptions": [
    {
      "channel": "attention",
      "resource_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "subscribed_at": "2026-04-11T14:23:00.000Z",
      "auto": true
    }
  ]
}
```

The `auto_subscriptions` list confirms all channels that were automatically subscribed on the client's behalf (always includes `attention:{user_id}`).

---

## Client → Server Messages

### 1. Subscribe

Subscribe to a channel and resource. Requires the connection to be authenticated.

```json
{
  "type": "subscribe",
  "channel": "<channel_type>",
  "resource_id": "<resource_uuid>"
}
```

**Channel types**: `execution`, `interaction`, `conversation`, `workspace`, `fleet`, `reasoning`, `correction`, `simulation`, `testing`, `alerts`, `attention`

**resource_id**: UUID string of the resource to watch. Channel-type-specific:

| Channel | resource_id |
|---------|------------|
| `execution` | Execution UUID |
| `interaction` | Interaction UUID |
| `conversation` | Conversation UUID |
| `workspace` | Workspace UUID |
| `fleet` | Fleet UUID |
| `reasoning` | Execution UUID (the reasoning execution) |
| `correction` | Execution UUID (the self-correction execution) |
| `simulation` | Simulation run UUID |
| `testing` | Test suite UUID |
| `alerts` | User UUID (own user_id only) |
| `attention` | User UUID (own user_id only — auto-subscribed, but can also be sent explicitly) |

**Example**:
```json
{
  "type": "subscribe",
  "channel": "execution",
  "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90"
}
```

### 2. Unsubscribe

Remove a subscription.

```json
{
  "type": "unsubscribe",
  "channel": "<channel_type>",
  "resource_id": "<resource_uuid>"
}
```

**Note**: Auto-subscribed channels (`attention:{user_id}`) cannot be unsubscribed. An unsubscribe attempt for an auto-subscription returns a `subscription_error` with code `cannot_unsubscribe_auto`.

### 3. List Subscriptions

Request a list of all active subscriptions.

```json
{
  "type": "list_subscriptions"
}
```

---

## Server → Client Messages

### 1. Subscription Confirmed

Sent after a successful subscribe.

```json
{
  "type": "subscription_confirmed",
  "channel": "execution",
  "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90",
  "subscribed_at": "2026-04-11T14:23:05.123Z"
}
```

### 2. Subscription Error

Sent when a subscribe (or invalid unsubscribe) fails.

```json
{
  "type": "subscription_error",
  "channel": "execution",
  "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90",
  "error": "You are not authorized to subscribe to this execution",
  "code": "unauthorized"
}
```

**Error codes**:

| Code | Meaning |
|------|---------|
| `unauthorized` | User is not a member of the workspace that owns this resource |
| `resource_not_found` | The resource_id does not exist or is not accessible |
| `invalid_channel` | Unknown channel type |
| `invalid_resource_id` | resource_id is not a valid UUID |
| `cannot_unsubscribe_auto` | Attempted to unsubscribe from an auto-managed channel |
| `already_subscribed` | Duplicate subscription (non-fatal, returns this error + implicit confirmation) |

### 3. Subscription Removed

Sent after a successful unsubscribe.

```json
{
  "type": "subscription_removed",
  "channel": "execution",
  "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90"
}
```

### 4. Subscription List

Response to `list_subscriptions`.

```json
{
  "type": "subscription_list",
  "subscriptions": [
    {
      "channel": "execution",
      "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90",
      "subscribed_at": "2026-04-11T14:23:05.123Z",
      "auto": false
    },
    {
      "channel": "attention",
      "resource_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "subscribed_at": "2026-04-11T14:23:00.000Z",
      "auto": true
    }
  ]
}
```

### 5. Event Delivery

Delivers a backend event to the client. `payload` is the canonical `EventEnvelope` (feature 013) serialized as JSON object.

```json
{
  "type": "event",
  "channel": "execution",
  "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90",
  "payload": {
    "event_id": "...",
    "event_type": "execution.step.completed",
    "schema_version": "1.0",
    "produced_at": "2026-04-11T14:23:04.980Z",
    "producer": "execution-service",
    "correlation": {
      "workspace_id": "...",
      "execution_id": "...",
      "conversation_id": null,
      "fleet_id": null,
      "goal_id": null
    },
    "payload": { ... }
  },
  "gateway_received_at": "2026-04-11T14:23:05.000Z"
}
```

**Attention event example** (channel = `attention`):

```json
{
  "type": "event",
  "channel": "attention",
  "resource_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "payload": {
    "event_id": "...",
    "event_type": "interaction.attention_requested",
    "schema_version": "1.0",
    "produced_at": "...",
    "producer": "execution-service",
    "correlation": {
      "workspace_id": "...",
      "execution_id": "...",
      "conversation_id": "...",
      "fleet_id": null,
      "goal_id": "..."
    },
    "payload": {
      "target_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "source_agent_fqn": "finance-ops:kyc-verifier",
      "urgency_level": "high",
      "context_summary": "KYC verification blocked: missing document for client ABC Corp",
      "related_execution_id": "...",
      "related_interaction_id": "...",
      "related_goal_id": "..."
    }
  },
  "gateway_received_at": "..."
}
```

### 6. Events Dropped

Sent to the client when backpressure caused events to be dropped. Delivered before the next real event.

```json
{
  "type": "events_dropped",
  "channel": null,
  "count": 47,
  "dropped_at": "2026-04-11T14:25:00.000Z"
}
```

`channel` is `null` if drops span multiple channels; otherwise the specific channel name.

### 7. Error

Sent for protocol violations or internal errors.

```json
{
  "type": "error",
  "error": "Malformed message: 'channel' field is required",
  "code": "protocol_violation"
}
```

**Error codes**:

| Code | Meaning |
|------|---------|
| `protocol_violation` | Malformed JSON, unknown message type, missing required fields |
| `internal_error` | Server-side error (logged server-side; not exposed to client) |

---

## Connection Close Codes

| Code | Meaning | Client Action |
|------|---------|---------------|
| 1000 | Normal closure | Clean disconnect |
| 1001 | Going Away (server shutdown) | Reconnect to another instance |
| 4400 | Protocol violation threshold exceeded | Fix client implementation |
| 4401 | Session expired / invalidated | Re-authenticate and reconnect |
| 4403 | Forbidden (user blocked/suspended) | Do not reconnect automatically |

---

## Rate Limits and Abuse Protection

- **Malformed messages**: After `WS_MAX_MALFORMED_MESSAGES` (default 10) malformed messages within 60 seconds, the connection is closed with code 4400.
- **Subscribe rate**: No explicit rate limit at this phase. The subscription registry itself is O(1) per operation.
- **Message size**: Maximum incoming message size is 64 KB (configurable). Larger frames are rejected as `protocol_violation`.

---

## Session Token Refresh

The WebSocket protocol does not support mid-connection token refresh. Clients should:

1. Refresh the access token via REST (`POST /api/v1/auth/refresh`) before it expires
2. Close and reconnect with the new token

If the server detects an expired token (via `auth.events` session invalidation), it closes the connection with code 4401, signalling the client to re-authenticate.

---

## Integration with Frontend WebSocket Client (feature 015)

The `lib/ws.ts` WebSocketClient in the Next.js frontend maps to this protocol:

| `lib/ws.ts` concept | Wire protocol |
|---------------------|---------------|
| `subscribe(topic)` | `{"type": "subscribe", "channel": ..., "resource_id": ...}` |
| `unsubscribe(topic)` | `{"type": "unsubscribe", ...}` |
| Message handler callback | Called on `type: "event"` messages |
| Reconnection | Triggered by close codes 1001 and 4401 (with re-auth for 4401) |
