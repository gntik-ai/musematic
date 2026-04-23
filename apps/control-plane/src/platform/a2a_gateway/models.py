from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class A2ATaskState(StrEnum):
    submitted = "submitted"
    working = "working"
    input_required = "input_required"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    cancellation_pending = "cancellation_pending"


class A2ADirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class A2ATask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "a2a_tasks"
    __table_args__ = (
        Index("ix_a2a_tasks_state", "a2a_state"),
        Index("ix_a2a_tasks_workspace", "workspace_id"),
        Index("ix_a2a_tasks_principal", "principal_id"),
        Index("ix_a2a_tasks_interaction", "interaction_id"),
    )

    task_id: Mapped[str] = mapped_column(String(length=128), nullable=False, unique=True)
    direction: Mapped[A2ADirection] = mapped_column(
        SAEnum(A2ADirection, name="a2a_direction"),
        nullable=False,
    )
    a2a_state: Mapped[A2ATaskState] = mapped_column(
        SAEnum(A2ATaskState, name="a2a_task_state"),
        nullable=False,
        default=A2ATaskState.submitted,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    principal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    interaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    external_endpoint_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("a2a_external_endpoints.id", ondelete="SET NULL"),
        nullable=True,
    )
    protocol_version: Mapped[str] = mapped_column(String(length=16), nullable=False)
    submitted_message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    idle_timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class A2AExternalEndpoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "a2a_external_endpoints"
    __table_args__ = (
        Index("ix_a2a_endpoints_workspace", "workspace_id"),
        Index("ix_a2a_endpoints_status", "status"),
        Index("uq_a2a_endpoints_workspace_url", "workspace_id", "endpoint_url", unique=True),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(length=2048), nullable=False)
    agent_card_url: Mapped[str] = mapped_column(String(length=2048), nullable=False)
    auth_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    card_ttl_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=3600)
    cached_agent_card: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    card_cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    card_is_stale: Mapped[bool] = mapped_column(nullable=False, default=False)
    declared_version: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="active")
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class A2AAuditRecord(Base, UUIDMixin):
    __tablename__ = "a2a_audit_records"
    __table_args__ = (
        Index("ix_a2a_audit_task", "task_id"),
        Index("ix_a2a_audit_occurred_at", "occurred_at"),
        Index("ix_a2a_audit_workspace", "workspace_id"),
    )

    task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("a2a_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[A2ADirection] = mapped_column(
        SAEnum(A2ADirection, name="a2a_direction"),
        nullable=False,
    )
    principal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    action: Mapped[str] = mapped_column(String(length=64), nullable=False)
    result: Mapped[str] = mapped_column(String(length=32), nullable=False)
    policy_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
