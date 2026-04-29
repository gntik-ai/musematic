from __future__ import annotations

import asyncio
import time
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.debug_logging.redaction import redact_body, redact_headers, redact_path
from platform.common.debug_logging.repository import DebugLoggingRepository
from platform.common.debug_logging.service import DebugLoggingService
from platform.common.logging import get_logger
from typing import cast
from uuid import UUID

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER = get_logger(__name__)


class DebugCaptureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_body = await request.body()
        buffered_messages: list[Message] = []
        response_chunks: list[bytes] = []
        response_status = 500
        response_headers: dict[str, str] = {}
        receive_consumed = False
        receive_empty_sent = False
        disconnect_event = asyncio.Event()
        passthrough_response = False
        start = time.perf_counter()

        async def replay_receive() -> Message:
            nonlocal receive_consumed, receive_empty_sent
            if receive_consumed:
                if not receive_empty_sent:
                    receive_empty_sent = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                await disconnect_event.wait()
                return {"type": "http.disconnect"}
            receive_consumed = True
            return {"type": "http.request", "body": request_body, "more_body": False}

        async def capture_send(message: Message) -> None:
            nonlocal response_status, response_headers, passthrough_response
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                response_headers = {
                    key.decode("latin-1"): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
                content_type = response_headers.get("content-type", "").split(";", 1)[0].lower()
                passthrough_response = content_type == "text/event-stream"
            if passthrough_response:
                await send(message)
                return
            buffered_messages.append(message)
            if message["type"] == "http.response.body":
                response_chunks.append(cast(bytes, message.get("body", b"")))

        await self.app(scope, replay_receive, capture_send)
        duration_ms = max(int((time.perf_counter() - start) * 1000), 0)

        try:
            await self._capture_if_needed(
                request,
                request_body=request_body,
                response_status=response_status,
                response_headers=response_headers,
                response_body=b"".join(response_chunks),
                duration_ms=duration_ms,
            )
        except Exception:
            LOGGER.exception("debug logging capture failed")

        for message in buffered_messages:
            await send(message)

    async def _capture_if_needed(
        self,
        request: Request,
        *,
        request_body: bytes,
        response_status: int,
        response_headers: dict[str, str],
        response_body: bytes,
        duration_ms: int,
    ) -> None:
        candidates = self._candidate_targets(request)
        if not candidates:
            return

        settings = cast(PlatformSettings, request.app.state.settings)
        redis_client = request.app.state.clients.get("redis")
        if not isinstance(redis_client, AsyncRedisClient):
            return

        async with database.AsyncSessionLocal() as session:
            service = DebugLoggingService(
                repository=DebugLoggingRepository(session),
                redis_client=redis_client,
                settings=settings,
                producer=request.app.state.clients.get("kafka"),
            )
            correlation_id = self._correlation_id(request)
            request_headers = dict(request.headers.items())
            path = redact_path(self._raw_path(request))
            for target_type, target_id in candidates:
                debug_session = await service.find_active_session(target_type, target_id)
                if debug_session is None:
                    continue
                await service.record_capture(
                    debug_session.id,
                    method=request.method,
                    path=path,
                    request_headers=redact_headers(request_headers),
                    request_body=redact_body(
                        request_body,
                        request.headers.get("content-type", "text/plain"),
                    )
                    if request_body
                    else None,
                    response_status=response_status,
                    response_headers=redact_headers(response_headers),
                    response_body=redact_body(
                        response_body,
                        response_headers.get("content-type", "text/plain"),
                    )
                    if response_body
                    else None,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                )
            await session.commit()

    @staticmethod
    def _candidate_targets(request: Request) -> list[tuple[str, UUID]]:
        candidates: list[tuple[str, UUID]] = []
        state_user = getattr(request.state, "user", None)
        if isinstance(state_user, dict) and state_user.get("principal_type") == "user":
            principal_id = state_user.get("principal_id") or state_user.get("sub")
            try:
                candidates.append(("user", UUID(str(principal_id))))
            except (TypeError, ValueError):
                pass
        workspace_id = request.headers.get("X-Workspace-ID")
        if workspace_id:
            try:
                candidates.append(("workspace", UUID(workspace_id)))
            except ValueError:
                pass
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _raw_path(request: Request) -> str:
        query_string = request.scope.get("query_string", b"").decode("latin-1")
        if not query_string:
            return request.url.path
        return f"{request.url.path}?{query_string}"

    @staticmethod
    def _correlation_id(request: Request) -> UUID:
        raw = getattr(request.state, "correlation_id", None) or request.headers.get(
            "X-Correlation-ID"
        )
        try:
            return UUID(str(raw))
        except (TypeError, ValueError):
            return UUID("00000000-0000-0000-0000-000000000000")
