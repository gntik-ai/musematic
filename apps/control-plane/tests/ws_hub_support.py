from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from platform.common.config import PlatformSettings
from platform.ws_hub.connection import ConnectionRegistry, WebSocketConnection
from platform.ws_hub.subscription import SubscriptionRegistry
from platform.ws_hub.visibility import VisibilityFilter
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from starlette.websockets import WebSocketDisconnect


class FakeWebSocket:
    def __init__(
        self,
        state: Any,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        incoming: list[str | Exception] | None = None,
        fail_send_text: bool = False,
        fail_send_bytes: bool = False,
    ) -> None:
        self.app = SimpleNamespace(state=state)
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.incoming = list(incoming or [])
        self.fail_send_text = fail_send_text
        self.fail_send_bytes = fail_send_bytes
        self.accepted = False
        self.sent_text: list[str] = []
        self.sent_bytes: list[bytes] = []
        self.close_calls: list[tuple[int, str | None]] = []
        self.denial_status_code: int | None = None
        self.denial_body: dict[str, Any] | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.fail_send_text:
            raise RuntimeError("send_text failed")
        self.sent_text.append(text)

    async def send_bytes(self, data: bytes) -> None:
        if self.fail_send_bytes:
            raise RuntimeError("send_bytes failed")
        self.sent_bytes.append(data)

    async def receive_text(self) -> str:
        if not self.incoming:
            raise WebSocketDisconnect(code=1000)
        item = self.incoming.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_calls.append((code, reason))

    async def send_denial_response(self, response: Any) -> None:
        self.denial_status_code = int(response.status_code)
        self.denial_body = json.loads(response.body.decode("utf-8"))

    def decoded_messages(self) -> list[dict[str, Any]]:
        return [json.loads(item) for item in self.sent_text]


class RecordingFanout:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.ensured: list[list[str]] = []
        self.released: list[list[str]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def ensure_consuming(self, topics: list[str]) -> None:
        self.ensured.append(sorted(topics))

    async def release_topics(self, topics: list[str]) -> None:
        self.released.append(sorted(topics))


class StaticAuthService:
    def __init__(self, token_payloads: dict[str, dict[str, Any]] | None = None) -> None:
        self.token_payloads = token_payloads or {}

    async def validate_token(self, token: str) -> dict[str, Any]:
        payload = self.token_payloads.get(token)
        if payload is None:
            error = RuntimeError("invalid token")
            error.status_code = 401
            error.message = "Invalid authentication token"
            raise error
        return payload


class StaticWorkspacesService:
    def __init__(
        self,
        *,
        workspace_ids_by_user: dict[UUID, list[UUID]] | None = None,
        resource_workspace_map: dict[tuple[str, UUID], UUID] | None = None,
    ) -> None:
        self.workspace_ids_by_user = workspace_ids_by_user or {}
        self.resource_workspace_map = resource_workspace_map or {}

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        return list(self.workspace_ids_by_user.get(user_id, []))

    async def get_workspace_id_for_resource(self, channel: Any, resource_id: UUID) -> UUID | None:
        channel_key = channel.value if hasattr(channel, "value") else str(channel)
        return self.resource_workspace_map.get((channel_key, resource_id))


def build_connection(
    *,
    user_id: UUID | None = None,
    workspace_ids: set[UUID] | None = None,
    websocket: FakeWebSocket | None = None,
    connection_id: str | None = None,
    queue_size: int = 4,
) -> WebSocketConnection:
    return WebSocketConnection(
        connection_id=connection_id or str(uuid4()),
        user_id=user_id or uuid4(),
        workspace_ids=workspace_ids or set(),
        websocket=websocket or FakeWebSocket(SimpleNamespace()),
        send_queue=asyncio.Queue(maxsize=queue_size),
    )


def build_state(
    *,
    settings: PlatformSettings | None = None,
    auth_service: StaticAuthService | None = None,
    workspaces_service: StaticWorkspacesService | None = None,
    fanout: RecordingFanout | None = None,
) -> Any:
    resolved_settings = settings or PlatformSettings(
        AUTH_JWT_SECRET_KEY="a" * 32,
        AUTH_JWT_ALGORITHM="HS256",
        WS_CLIENT_BUFFER_SIZE=4,
        WS_HEARTBEAT_INTERVAL_SECONDS=1,
        WS_HEARTBEAT_TIMEOUT_SECONDS=10,
        WS_MAX_MALFORMED_MESSAGES=2,
    )
    resolved_auth_service = auth_service or StaticAuthService()
    resolved_workspaces_service = workspaces_service or StaticWorkspacesService()
    resolved_fanout = fanout or RecordingFanout()

    @asynccontextmanager
    async def auth_service_factory():
        yield resolved_auth_service

    @asynccontextmanager
    async def workspaces_service_factory():
        yield resolved_workspaces_service

    state = SimpleNamespace(
        settings=resolved_settings,
        auth_service_factory=auth_service_factory,
        workspaces_service_factory=workspaces_service_factory,
        connection_registry=ConnectionRegistry(),
        subscription_registry=SubscriptionRegistry(),
    )
    state.visibility_filter = VisibilityFilter(state.workspaces_service_factory)
    state.fanout = resolved_fanout
    return state
