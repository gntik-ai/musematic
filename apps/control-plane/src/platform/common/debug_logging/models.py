from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DebugLoggingTargetType(StrEnum):
    user = "user"
    workspace = "workspace"


class DebugLoggingTerminationReason(StrEnum):
    expired = "expired"
    rtbf_cascade = "rtbf_cascade"
    manual_close = "manual_close"


class DebugLoggingSession(Base, UUIDMixin):
    __tablename__ = "debug_logging_sessions"
    __table_args__ = (
        Index(
            "ix_debug_logging_sessions_target",
            "target_type",
            "target_id",
            "expires_at",
            postgresql_where=text("terminated_at IS NULL"),
        ),
        Index("ix_debug_logging_sessions_requested_by", "requested_by", "started_at"),
        Index("ix_debug_logging_sessions_expires_at", "expires_at"),
    )

    target_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    justification: Mapped[str] = mapped_column(Text(), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    capture_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correlation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    captures: Mapped[list[DebugLoggingCapture]] = relationship(
        "platform.common.debug_logging.models.DebugLoggingCapture",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by=("platform.common.debug_logging.models.DebugLoggingCapture.captured_at.asc()"),
    )


class DebugLoggingCapture(Base, UUIDMixin):
    __tablename__ = "debug_logging_captures"
    __table_args__ = (
        Index("ix_debug_logging_captures_session", "session_id", "captured_at"),
        Index("ix_debug_logging_captures_captured_at", "captured_at"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("debug_logging_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(length=10), nullable=False)
    path: Mapped[str] = mapped_column(Text(), nullable=False)
    request_headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    request_body: Mapped[str | None] = mapped_column(Text(), nullable=True)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    response_body: Mapped[str | None] = mapped_column(Text(), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    session: Mapped[DebugLoggingSession] = relationship(
        "platform.common.debug_logging.models.DebugLoggingSession",
        back_populates="captures",
    )
