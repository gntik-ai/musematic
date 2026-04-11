# Data Model: WebSocket Real-Time Gateway

**Feature**: 019-websocket-realtime-gateway  
**Date**: 2026-04-11  
**Phase**: Phase 1 — Design

## Overview

The WebSocket gateway has **no database models**. All state is in-memory, scoped to the lifetime of the `ws-hub` process. The data model consists of:

1. **In-memory state** — Python dataclasses representing live connections and subscriptions
2. **Pydantic protocol schemas** — JSON message contracts for the WebSocket wire protocol
3. **Channel type enum and topic mapping** — the subscription → Kafka topic resolution table

---

## 1. In-Memory State

### 1.1 Enums

```python
from enum import StrEnum

class ChannelType(StrEnum):
    EXECUTION    = "execution"
    INTERACTION  = "interaction"
    CONVERSATION = "conversation"
    WORKSPACE    = "workspace"
    FLEET        = "fleet"
    REASONING    = "reasoning"
    CORRECTION   = "correction"
    SIMULATION   = "simulation"
    TESTING      = "testing"
    ALERTS       = "alerts"
    ATTENTION    = "attention"

class CloseCode(int):
    """Custom WebSocket close codes (4000–4999 are application-defined)."""
    SESSION_EXPIRED     = 4401
    UNAUTHORIZED        = 4403
    PROTOCOL_VIOLATION  = 4400
    SERVER_SHUTDOWN     = 1001  # Standard Going Away
```

### 1.2 CHANNEL_TOPIC_MAP

```python
from typing import Sequence

CHANNEL_TOPIC_MAP: dict[ChannelType, Sequence[str]] = {
    ChannelType.EXECUTION:    ["workflow.runtime", "runtime.lifecycle"],
    ChannelType.INTERACTION:  ["interaction.events"],
    ChannelType.CONVERSATION: ["interaction.events"],
    ChannelType.WORKSPACE:    ["workspaces.events"],
    ChannelType.FLEET:        ["runtime.lifecycle"],
    ChannelType.REASONING:    ["runtime.reasoning"],
    ChannelType.CORRECTION:   ["runtime.selfcorrection"],
    ChannelType.SIMULATION:   ["simulation.events"],
    ChannelType.TESTING:      ["testing.results"],
    ChannelType.ALERTS:       ["monitor.alerts"],
    ChannelType.ATTENTION:    ["interaction.attention"],
}
```

### 1.3 Subscription Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

@dataclass
class Subscription:
    channel: ChannelType
    resource_id: str          # entity UUID or user_id (str form)
    subscribed_at: datetime
    auto: bool = False        # True for auto-subscribed attention channel
```

### 1.4 WebSocketConnection Dataclass

```python
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

@dataclass
class WebSocketConnection:
    connection_id: str                              # UUID str, generated on connect
    user_id: UUID
    workspace_ids: set[UUID]                        # current workspace memberships (cached)
    websocket: Any                                  # Starlette WebSocket object
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    # key: f"{channel}:{resource_id}"
    send_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    # maxsize overridden by WS_CLIENT_BUFFER_SIZE at runtime
    dropped_count: int = 0
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_pong_at: datetime = field(default_factory=datetime.utcnow)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    malformed_message_count: int = 0               # for abuse detection (>10 → close)
```

### 1.5 ConnectionRegistry

```python
class ConnectionRegistry:
    """Thread-safe (asyncio-safe) registry of active WebSocket connections.
    
    Keyed by connection_id (str UUID). All operations are O(1) dict operations.
    """
    
    def __init__(self) -> None:
        self._connections: dict[str, WebSocketConnection] = {}
    
    def add(self, conn: WebSocketConnection) -> None: ...
    def remove(self, connection_id: str) -> None: ...
    def get(self, connection_id: str) -> WebSocketConnection | None: ...
    def get_by_user_id(self, user_id: UUID) -> list[WebSocketConnection]: ...
    def all(self) -> list[WebSocketConnection]: ...
    def count(self) -> int: ...
```

### 1.6 SubscriptionRegistry

```python
class SubscriptionRegistry:
    """Tracks which connections are subscribed to which channels.
    
    Used by KafkaFanout to:
    1. Look up connections to deliver events to (by channel+resource_id)
    2. Track active Kafka topics (by reference count) for dynamic consumer management
    """
    
    def __init__(self) -> None:
        # channel_key (f"{channel}:{resource_id}") → set of connection_ids
        self._subscribers: dict[str, set[str]] = {}
        # kafka_topic → reference count (number of active subscriptions needing it)
        self._topic_refcount: dict[str, int] = {}
    
    def subscribe(self, conn_id: str, sub: Subscription) -> list[str]:
        """Returns list of newly-needed Kafka topics (refcount 0→1)."""
        ...
    
    def unsubscribe(self, conn_id: str, channel_key: str) -> list[str]:
        """Returns list of no-longer-needed Kafka topics (refcount 1→0)."""
        ...
    
    def unsubscribe_all(self, conn_id: str) -> list[str]:
        """Called on disconnect. Returns topics that dropped to zero refcount."""
        ...
    
    def get_subscribers(self, channel: ChannelType, resource_id: str) -> set[str]:
        """Returns connection_ids subscribed to this channel+resource."""
        ...
    
    def get_active_topics(self) -> set[str]:
        """Returns Kafka topics with at least one active subscription."""
        ...
```

---

## 2. WebSocket Protocol Schemas (Pydantic v2)

### 2.1 Client → Server Messages

```python
from pydantic import BaseModel, model_validator
from typing import Literal

class SubscribeMessage(BaseModel):
    type: Literal["subscribe"]
    channel: ChannelType
    resource_id: str  # UUID string of the resource to watch

class UnsubscribeMessage(BaseModel):
    type: Literal["unsubscribe"]
    channel: ChannelType
    resource_id: str

class ListSubscriptionsMessage(BaseModel):
    type: Literal["list_subscriptions"]

# Discriminated union for parsing incoming messages
ClientMessage = SubscribeMessage | UnsubscribeMessage | ListSubscriptionsMessage
```

### 2.2 Server → Client Messages

```python
from datetime import datetime

class ConnectionEstablishedMessage(BaseModel):
    type: Literal["connection_established"]
    connection_id: str
    user_id: str
    server_time: datetime

class SubscriptionConfirmedMessage(BaseModel):
    type: Literal["subscription_confirmed"]
    channel: str
    resource_id: str
    subscribed_at: datetime

class SubscriptionErrorMessage(BaseModel):
    type: Literal["subscription_error"]
    channel: str
    resource_id: str
    error: str               # human-readable reason
    code: str                # machine-readable: "unauthorized" | "resource_not_found" | "invalid_channel"

class SubscriptionRemovedMessage(BaseModel):
    type: Literal["subscription_removed"]
    channel: str
    resource_id: str

class SubscriptionListMessage(BaseModel):
    type: Literal["subscription_list"]
    subscriptions: list[SubscriptionInfo]

class SubscriptionInfo(BaseModel):
    channel: str
    resource_id: str
    subscribed_at: datetime
    auto: bool               # True for auto-subscribed channels (attention)

class EventMessage(BaseModel):
    type: Literal["event"]
    channel: str
    resource_id: str
    payload: dict            # raw EventEnvelope as dict (from feature 013)
    received_at: datetime

class EventsDroppedMessage(BaseModel):
    type: Literal["events_dropped"]
    channel: str | None      # None if drops span multiple channels
    count: int               # number of events dropped since last delivery
    dropped_at: datetime

class ErrorMessage(BaseModel):
    type: Literal["error"]
    error: str
    code: str                # "protocol_violation" | "internal_error"
```

---

## 3. Service Classes (ws_hub package)

### 3.1 KafkaFanout

```python
class KafkaFanout:
    """Manages dynamic Kafka topic consumers and fans out events to subscribers.
    
    Lifecycle:
      - start(): called in FastAPI lifespan startup
      - stop(): called in FastAPI lifespan shutdown
    
    Per active Kafka topic:
      - One AIOKafkaConsumer per topic, unique consumer group ws-hub-{hostname}-{pid}
      - Consumer task: polls events, calls _route_event()
    
    _route_event(topic, envelope):
      1. Match envelope to channel + resource_id via topic-to-channel reverse map
      2. Look up subscribers via SubscriptionRegistry.get_subscribers()
      3. For each subscriber connection:
         a. Check visibility (conn.workspace_ids)
         b. If authorized: enqueue to conn.send_queue (non-blocking)
    """
    
    def __init__(
        self,
        connection_registry: ConnectionRegistry,
        subscription_registry: SubscriptionRegistry,
        settings: PlatformSettings,
    ) -> None: ...
    
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def ensure_consuming(self, topics: list[str]) -> None: ...
    async def release_topics(self, topics: list[str]) -> None: ...
```

### 3.2 ConnectionWriter

```python
class ConnectionWriter:
    """Per-connection coroutine that reads from send_queue and sends over WebSocket.
    
    - Runs as asyncio task for each connection
    - Before each send: checks dropped_count; if > 0, sends EventsDroppedMessage first
    - Exits when conn.closed is set
    """
    
    async def run(self, conn: WebSocketConnection) -> None: ...
```

### 3.3 ConnectionHeartbeat

```python
class ConnectionHeartbeat:
    """Per-connection coroutine that sends WebSocket ping and checks pong timeout.
    
    - Sends ping every WS_HEARTBEAT_INTERVAL_SECONDS (default 30s)
    - If time since last_pong_at > WS_HEARTBEAT_TIMEOUT_SECONDS: close connection
    - Updates conn.last_pong_at when pong frame received
    """
    
    async def run(self, conn: WebSocketConnection) -> None: ...
```

### 3.4 VisibilityFilter

```python
class VisibilityFilter:
    """Determines whether an event envelope is visible to a given connection.
    
    Rules:
    - Extract workspace_id from envelope.correlation.workspace_id
    - If workspace_id is None: event is not workspace-scoped → allow delivery
    - If workspace_id in conn.workspace_ids: allow
    - Else: deny
    
    Membership refresh:
    - On workspaces.events with type matching membership.added/removed: 
      refresh conn.workspace_ids for affected user_id connections
    """
    
    def is_visible(self, envelope: dict, conn: WebSocketConnection) -> bool: ...
    
    async def refresh_membership(self, user_id: UUID, conn: WebSocketConnection) -> None:
        """Calls workspaces_service.get_user_workspace_ids(user_id) in-process."""
        ...
```

---

## 4. Configuration (PlatformSettings additions)

```python
# New settings for ws-hub profile
WS_CLIENT_BUFFER_SIZE: int = 1000        # asyncio.Queue maxsize per connection
WS_HEARTBEAT_INTERVAL_SECONDS: int = 30  # How often to send ping
WS_HEARTBEAT_TIMEOUT_SECONDS: int = 10   # How long to wait for pong
WS_MAX_MALFORMED_MESSAGES: int = 10      # Close connection after N malformed messages
WS_CONSUMER_GROUP_ID: str = ""           # Auto-generated: ws-hub-{hostname}-{pid}
```

---

## 5. Module Structure

```text
apps/control-plane/
├── entrypoints/
│   └── ws_main.py                        # ws-hub uvicorn entrypoint
└── src/platform/
    └── ws_hub/
        ├── __init__.py
        ├── router.py                     # FastAPI WebSocket route: /ws
        ├── connection.py                 # WebSocketConnection, ConnectionRegistry dataclasses
        ├── subscription.py               # Subscription, SubscriptionRegistry, ChannelType, CHANNEL_TOPIC_MAP
        ├── fanout.py                     # KafkaFanout service
        ├── writer.py                     # ConnectionWriter coroutine
        ├── heartbeat.py                  # ConnectionHeartbeat coroutine
        ├── visibility.py                 # VisibilityFilter
        ├── schemas.py                    # Pydantic WS protocol message schemas
        ├── exceptions.py                 # WebSocketError, SubscriptionAuthError, etc.
        └── dependencies.py              # FastAPI DI: get_connection_registry, get_fanout
```

---

## 6. Key Invariants

| Invariant | Description |
|-----------|-------------|
| No database access | ws_hub has zero SQLAlchemy/Alembic dependencies |
| Per-connection queue isolation | Slow client never blocks fan-out loop |
| Attention auto-subscription | Every connection immediately subscribed to `attention:{user_id}` |
| Dynamic Kafka consumers | Zero topics consumed when zero clients connected |
| Workspace membership freshness | Max 30s staleness (event-driven + periodic fallback) |
| Unique consumer group | Each ws-hub process consumes all events independently |
