from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.ws_hub.subscription import Subscription
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class WebSocketConnection:
    connection_id: str
    user_id: UUID
    workspace_ids: set[UUID]
    websocket: Any
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    pending_subscriptions: set[str] = field(default_factory=set)
    send_queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    dropped_count: int = 0
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_pong_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    malformed_message_count: int = 0
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocketConnection] = {}

    def add(self, conn: WebSocketConnection) -> None:
        if conn.connection_id in self._connections:
            raise ValueError(f"Connection already registered: {conn.connection_id}")
        self._connections[conn.connection_id] = conn

    def remove(self, connection_id: str) -> WebSocketConnection | None:
        return self._connections.pop(connection_id, None)

    def get(self, connection_id: str) -> WebSocketConnection | None:
        return self._connections.get(connection_id)

    def get_by_user_id(self, user_id: UUID) -> list[WebSocketConnection]:
        return [
            conn
            for conn in self._connections.values()
            if conn.user_id == user_id
        ]

    def all(self) -> list[WebSocketConnection]:
        return list(self._connections.values())

    def count(self) -> int:
        return len(self._connections)

