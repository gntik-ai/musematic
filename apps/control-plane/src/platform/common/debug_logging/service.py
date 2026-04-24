from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.debug_logging.events import (
    DebugLoggingCaptureWrittenPayload,
    DebugLoggingSessionCreatedPayload,
    DebugLoggingSessionExpiredPayload,
    publish_debug_logging_event,
)
from platform.common.debug_logging.models import (
    DebugLoggingCapture,
    DebugLoggingSession,
    DebugLoggingTargetType,
    DebugLoggingTerminationReason,
)
from platform.common.debug_logging.repository import DebugLoggingRepository
from platform.common.events.producer import EventProducer
from platform.common.exceptions import (
    AuthorizationError,
    NotFoundError,
    PlatformError,
    ValidationError,
)
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

DEBUG_SESSION_CACHE_CONTEXT = "debug-session-active"
DEBUG_SESSION_SENTINEL = ""
DEBUG_SESSION_SENTINEL_TTL_SECONDS = 30
MAX_DEBUG_SESSION_DURATION_MINUTES = 240
MIN_DEBUG_SESSION_JUSTIFICATION_LENGTH = 10


class DebugLoggingConflictError(PlatformError):
    status_code = 409


class DebugLoggingService:
    def __init__(
        self,
        *,
        repository: DebugLoggingRepository,
        redis_client: AsyncRedisClient,
        settings: PlatformSettings,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.settings = settings
        self.producer = producer
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def open_session(
        self,
        *,
        target_type: str,
        target_id: UUID,
        justification: str,
        duration_minutes: int,
        requested_by: UUID,
        correlation_id: UUID,
    ) -> DebugLoggingSession:
        normalized_target_type = self._normalize_target_type(target_type)
        normalized_justification = justification.strip()
        if len(normalized_justification) < MIN_DEBUG_SESSION_JUSTIFICATION_LENGTH:
            raise ValidationError(
                "DEBUG_LOGGING_JUSTIFICATION_TOO_SHORT",
                "Justification must be at least 10 characters",
            )
        if duration_minutes < 1 or duration_minutes > MAX_DEBUG_SESSION_DURATION_MINUTES:
            raise ValidationError(
                "DEBUG_LOGGING_DURATION_INVALID",
                "duration_minutes must be between 1 and 240",
            )

        existing = await self.repository.find_active_session_for_target(
            normalized_target_type,
            target_id,
        )
        if existing is not None:
            raise DebugLoggingConflictError(
                "DEBUG_LOGGING_SESSION_CONFLICT",
                "An active debug logging session already exists for this target",
                {"session_id": str(existing.id)},
            )

        started_at = datetime.now(UTC)
        expires_at = min(
            started_at + timedelta(minutes=duration_minutes),
            started_at + timedelta(minutes=MAX_DEBUG_SESSION_DURATION_MINUTES),
        )
        debug_session = DebugLoggingSession(
            target_type=normalized_target_type,
            target_id=target_id,
            requested_by=requested_by,
            justification=normalized_justification,
            started_at=started_at,
            expires_at=expires_at,
            capture_count=0,
            correlation_id=correlation_id,
        )
        debug_session = await self.repository.create_session(debug_session)
        await self._cache_active_session(debug_session)
        await publish_debug_logging_event(
            "debug_logging.session.created",
            DebugLoggingSessionCreatedPayload(
                session_id=debug_session.id,
                requested_by=debug_session.requested_by,
                target_type=debug_session.target_type,
                target_id=debug_session.target_id,
                justification=debug_session.justification,
                started_at=debug_session.started_at,
                expires_at=debug_session.expires_at,
                correlation_id=debug_session.correlation_id,
            ),
            debug_session.correlation_id,
            self.producer,
        )
        return debug_session

    async def get_session(self, session_id: UUID) -> DebugLoggingSession:
        debug_session = await self.repository.get_session(session_id)
        if debug_session is None:
            raise NotFoundError(
                "DEBUG_LOGGING_SESSION_NOT_FOUND",
                "Debug logging session not found",
            )
        return debug_session

    async def list_sessions(
        self,
        *,
        active_only: bool,
        requested_by: UUID | None,
        target_type: str | None,
        target_id: UUID | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[DebugLoggingSession], str | None]:
        normalized_target_type = (
            None if target_type is None else self._normalize_target_type(target_type)
        )
        return await self.repository.list_sessions(
            active_only=active_only,
            requested_by=requested_by,
            target_type=normalized_target_type,
            target_id=target_id,
            limit=limit,
            cursor=cursor,
        )

    async def terminate_session(
        self,
        session_id: UUID,
        *,
        actor_id: UUID,
        is_superadmin: bool,
        reason: DebugLoggingTerminationReason = DebugLoggingTerminationReason.manual_close,
    ) -> DebugLoggingSession:
        debug_session = await self.get_session(session_id)
        if debug_session.terminated_at is not None:
            raise DebugLoggingConflictError(
                "DEBUG_LOGGING_SESSION_ALREADY_TERMINATED",
                "Debug logging session is already terminated",
            )
        if not is_superadmin and debug_session.requested_by != actor_id:
            raise AuthorizationError(
                "PERMISSION_DENIED",
                "Only the requester or a superadmin can terminate this session",
            )
        terminated_at = datetime.now(UTC)
        debug_session = await self.repository.terminate_session(
            debug_session,
            terminated_at=terminated_at,
            termination_reason=reason.value,
        )
        await self.redis_client.cache_delete(
            DEBUG_SESSION_CACHE_CONTEXT,
            self._cache_key(debug_session.target_type, debug_session.target_id),
        )
        await publish_debug_logging_event(
            "debug_logging.session.expired",
            DebugLoggingSessionExpiredPayload(
                session_id=debug_session.id,
                duration_ms=max(
                    int((terminated_at - debug_session.started_at).total_seconds() * 1000),
                    0,
                ),
                capture_count=debug_session.capture_count,
                termination_reason=reason.value,
            ),
            debug_session.correlation_id,
            self.producer,
        )
        return debug_session

    async def list_captures(
        self,
        session_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[DebugLoggingCapture], str | None]:
        await self.get_session(session_id)
        return await self.repository.list_captures(session_id, limit=limit, cursor=cursor)

    async def find_active_session(
        self,
        target_type: str,
        target_id: UUID,
        *,
        use_cache: bool = True,
    ) -> DebugLoggingSession | None:
        normalized_target_type = self._normalize_target_type(target_type)
        cache_key = self._cache_key(normalized_target_type, target_id)
        current = datetime.now(UTC)

        if use_cache:
            cached = await self.redis_client.cache_get(DEBUG_SESSION_CACHE_CONTEXT, cache_key)
            if cached is not None:
                session_id = str(cached.get("session_id", DEBUG_SESSION_SENTINEL))
                if session_id == DEBUG_SESSION_SENTINEL:
                    return None
                try:
                    debug_session = await self.repository.get_session(UUID(session_id))
                except ValueError:
                    debug_session = None
                if debug_session is not None and self._is_active(debug_session, current):
                    return debug_session
                if debug_session is not None:
                    await self._expire_session_if_needed(debug_session, now=current)
                await self.redis_client.cache_delete(DEBUG_SESSION_CACHE_CONTEXT, cache_key)

        debug_session = await self.repository.find_active_session_for_target(
            normalized_target_type,
            target_id,
            now=current,
        )
        if debug_session is None:
            if use_cache:
                await self.redis_client.cache_set(
                    DEBUG_SESSION_CACHE_CONTEXT,
                    cache_key,
                    {"session_id": DEBUG_SESSION_SENTINEL},
                    ttl_seconds=DEBUG_SESSION_SENTINEL_TTL_SECONDS,
                )
            return None

        if use_cache:
            await self._cache_active_session(debug_session, now=current)
        return debug_session

    async def record_capture(
        self,
        session_id: UUID,
        *,
        method: str,
        path: str,
        request_headers: dict[str, str],
        request_body: str | None,
        response_status: int,
        response_headers: dict[str, str],
        response_body: str | None,
        duration_ms: int,
        correlation_id: UUID,
    ) -> DebugLoggingCapture | None:
        debug_session = await self.repository.get_session(session_id)
        current = datetime.now(UTC)
        if debug_session is None or not self._is_active(debug_session, current):
            return None
        capture = DebugLoggingCapture(
            session_id=session_id,
            captured_at=current,
            method=method,
            path=path,
            request_headers=request_headers,
            request_body=request_body,
            response_status=response_status,
            response_headers=response_headers,
            response_body=response_body,
            duration_ms=max(duration_ms, 0),
            correlation_id=correlation_id,
        )
        capture = await self.repository.append_capture(capture)
        await self.repository.increment_capture_count(session_id)
        if self.producer is not None:
            task = asyncio.create_task(
                publish_debug_logging_event(
                    "debug_logging.capture.written",
                    DebugLoggingCaptureWrittenPayload(
                        session_id=session_id,
                        capture_id=capture.id,
                        captured_at=capture.captured_at,
                        method=capture.method,
                        path=capture.path,
                        response_status=capture.response_status,
                        duration_ms=capture.duration_ms,
                        correlation_id=capture.correlation_id,
                    ),
                    correlation_id,
                    self.producer,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        return capture

    async def purge_old_captures(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.governance.retention_days)
        return await self.repository.purge_old_captures(cutoff)

    async def _expire_session_if_needed(
        self,
        debug_session: DebugLoggingSession,
        *,
        now: datetime,
    ) -> None:
        if debug_session.terminated_at is not None or debug_session.expires_at > now:
            return
        debug_session = await self.repository.terminate_session(
            debug_session,
            terminated_at=now,
            termination_reason=DebugLoggingTerminationReason.expired.value,
        )
        await self.redis_client.cache_delete(
            DEBUG_SESSION_CACHE_CONTEXT,
            self._cache_key(debug_session.target_type, debug_session.target_id),
        )
        await publish_debug_logging_event(
            "debug_logging.session.expired",
            DebugLoggingSessionExpiredPayload(
                session_id=debug_session.id,
                duration_ms=max(
                    int((now - debug_session.started_at).total_seconds() * 1000),
                    0,
                ),
                capture_count=debug_session.capture_count,
                termination_reason=DebugLoggingTerminationReason.expired.value,
            ),
            debug_session.correlation_id,
            self.producer,
        )

    async def _cache_active_session(
        self,
        debug_session: DebugLoggingSession,
        *,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        ttl_seconds = max(int((debug_session.expires_at - current).total_seconds()), 1)
        await self.redis_client.cache_set(
            DEBUG_SESSION_CACHE_CONTEXT,
            self._cache_key(debug_session.target_type, debug_session.target_id),
            {"session_id": str(debug_session.id)},
            ttl_seconds=ttl_seconds,
        )

    @staticmethod
    def _cache_key(target_type: str, target_id: UUID) -> str:
        return f"{target_type}:{target_id}"

    @staticmethod
    def _normalize_target_type(target_type: str) -> str:
        try:
            return DebugLoggingTargetType(target_type).value
        except ValueError as exc:
            raise ValidationError(
                "DEBUG_LOGGING_TARGET_TYPE_INVALID",
                "target_type must be one of: user, workspace",
            ) from exc

    @staticmethod
    def _is_active(debug_session: DebugLoggingSession, now: datetime) -> bool:
        return debug_session.terminated_at is None and debug_session.expires_at > now


async def purge_debug_captures(
    *,
    session_factory: Callable[[], AsyncSession],
    redis_client: AsyncRedisClient,
    settings: PlatformSettings,
    producer: EventProducer | None = None,
) -> int:
    async with session_factory() as session:
        service = DebugLoggingService(
            repository=DebugLoggingRepository(session),
            redis_client=redis_client,
            settings=settings,
            producer=producer,
        )
        try:
            deleted = await service.purge_old_captures()
            await session.commit()
            return deleted
        except Exception:
            await session.rollback()
            raise
