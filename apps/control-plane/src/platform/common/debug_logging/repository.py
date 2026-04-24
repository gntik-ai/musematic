from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from platform.common.debug_logging.models import DebugLoggingCapture, DebugLoggingSession
from platform.common.pagination import decode_cursor, encode_cursor
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, literal, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class _PageCursorItem(Protocol):
    id: UUID


class DebugLoggingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, debug_session: DebugLoggingSession) -> DebugLoggingSession:
        self.session.add(debug_session)
        await self.session.flush()
        await self.session.refresh(debug_session)
        return debug_session

    async def get_session(self, session_id: UUID) -> DebugLoggingSession | None:
        query = (
            select(DebugLoggingSession)
            .where(DebugLoggingSession.id == session_id)
            .options(selectinload(DebugLoggingSession.captures))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_active_session_for_target(
        self,
        target_type: str,
        target_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DebugLoggingSession | None:
        current = now or datetime.now(UTC)
        query = (
            select(DebugLoggingSession)
            .where(DebugLoggingSession.target_type == target_type)
            .where(DebugLoggingSession.target_id == target_id)
            .where(DebugLoggingSession.terminated_at.is_(None))
            .where(DebugLoggingSession.expires_at > current)
            .order_by(DebugLoggingSession.started_at.desc(), DebugLoggingSession.id.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        *,
        active_only: bool,
        requested_by: UUID | None,
        target_type: str | None,
        target_id: UUID | None,
        limit: int,
        cursor: str | None,
        now: datetime | None = None,
    ) -> tuple[list[DebugLoggingSession], str | None]:
        current = now or datetime.now(UTC)
        query: Any = select(DebugLoggingSession)
        if active_only:
            query = query.where(DebugLoggingSession.terminated_at.is_(None)).where(
                DebugLoggingSession.expires_at > current
            )
        if requested_by is not None:
            query = query.where(DebugLoggingSession.requested_by == requested_by)
        if target_type is not None:
            query = query.where(DebugLoggingSession.target_type == target_type)
        if target_id is not None:
            query = query.where(DebugLoggingSession.target_id == target_id)
        query = _apply_cursor(
            query,
            DebugLoggingSession.started_at,
            DebugLoggingSession.id,
            cursor,
        ).order_by(DebugLoggingSession.started_at.desc(), DebugLoggingSession.id.desc())
        rows = list((await self.session.execute(query.limit(limit + 1))).scalars().all())
        return _page(rows, limit, lambda item: item.started_at)

    async def terminate_session(
        self,
        debug_session: DebugLoggingSession,
        *,
        terminated_at: datetime,
        termination_reason: str,
    ) -> DebugLoggingSession:
        debug_session.terminated_at = terminated_at
        debug_session.termination_reason = termination_reason
        await self.session.flush()
        await self.session.refresh(debug_session)
        return debug_session

    async def append_capture(self, capture: DebugLoggingCapture) -> DebugLoggingCapture:
        self.session.add(capture)
        await self.session.flush()
        await self.session.refresh(capture)
        return capture

    async def increment_capture_count(self, session_id: UUID) -> None:
        await self.session.execute(
            update(DebugLoggingSession)
            .where(DebugLoggingSession.id == session_id)
            .values(capture_count=DebugLoggingSession.capture_count + 1)
        )

    async def list_captures(
        self,
        session_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[DebugLoggingCapture], str | None]:
        query: Any = select(DebugLoggingCapture).where(DebugLoggingCapture.session_id == session_id)
        query = _apply_cursor(
            query,
            DebugLoggingCapture.captured_at,
            DebugLoggingCapture.id,
            cursor,
        ).order_by(DebugLoggingCapture.captured_at.desc(), DebugLoggingCapture.id.desc())
        rows = list((await self.session.execute(query.limit(limit + 1))).scalars().all())
        return _page(rows, limit, lambda item: item.captured_at)

    async def purge_old_captures(self, cutoff: datetime, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        active_session_ids = (
            select(DebugLoggingSession.id)
            .where(
                or_(
                    DebugLoggingSession.terminated_at.is_not(None),
                    DebugLoggingSession.expires_at < current,
                )
            )
            .subquery()
        )
        result = await self.session.execute(
            delete(DebugLoggingCapture).where(
                DebugLoggingCapture.captured_at < cutoff,
                DebugLoggingCapture.session_id.in_(select(active_session_ids.c.id)),
            )
        )
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)


def _apply_cursor(query: Any, column: Any, id_column: Any, cursor: str | None) -> Any:
    if not cursor:
        return query
    cursor_id, cursor_at = decode_cursor(cursor)
    return query.where(tuple_(column, id_column) < tuple_(literal(cursor_at), literal(cursor_id)))


def _page[PageItemT: _PageCursorItem](
    items: list[PageItemT],
    limit: int,
    timestamp_getter: Callable[[PageItemT], datetime],
) -> tuple[list[PageItemT], str | None]:
    next_cursor = None
    page_items = items[:limit]
    if len(items) > limit and page_items:
        next_cursor = encode_cursor(page_items[-1].id, timestamp_getter(page_items[-1]))
    return page_items, next_cursor
