from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MCPServerStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    deregistered = "deregistered"


class MCPInvocationDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class MCPInvocationOutcome(StrEnum):
    allowed = "allowed"
    denied = "denied"
    error_transient = "error_transient"
    error_permanent = "error_permanent"


class MCPServerRegistration(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mcp_server_registrations"
    __table_args__ = (
        Index("ix_mcp_server_registrations_workspace", "workspace_id"),
        Index(
            "uq_mcp_server_registrations_workspace_url",
            "workspace_id",
            "endpoint_url",
            unique=True,
        ),
        Index("ix_mcp_server_registrations_status", "status"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(length=2048), nullable=False)
    auth_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[MCPServerStatus] = mapped_column(
        SAEnum(MCPServerStatus, name="mcp_server_status"),
        nullable=False,
        default=MCPServerStatus.active,
        server_default=text("'active'"),
    )
    catalog_ttl_seconds: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=3600,
        server_default=text("3600"),
    )
    last_catalog_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    catalog_version_snapshot: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class MCPExposedTool(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mcp_exposed_tools"
    __table_args__ = (
        Index("ix_mcp_exposed_tools_exposed", "is_exposed"),
        Index(
            "uq_mcp_exposed_tools_workspace_tool",
            "workspace_id",
            "tool_fqn",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    tool_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    mcp_tool_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    mcp_description: Mapped[str] = mapped_column(Text(), nullable=False)
    mcp_input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_exposed: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class MCPCatalogCache(Base, UUIDMixin):
    __tablename__ = "mcp_catalog_cache"
    __table_args__ = (
        Index("uq_mcp_catalog_cache_server", "server_id", unique=True),
        Index("ix_mcp_catalog_cache_next_refresh_at", "next_refresh_at"),
    )

    server_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("mcp_server_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    tools_catalog: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    resources_catalog: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    prompts_catalog: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    version_snapshot: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    is_stale: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    next_refresh_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MCPInvocationAuditRecord(Base, UUIDMixin):
    __tablename__ = "mcp_invocation_audit_records"
    __table_args__ = (
        Index("ix_mcp_invocation_audit_workspace_time", "workspace_id", "timestamp"),
        Index("ix_mcp_invocation_audit_agent_time", "agent_id", "timestamp"),
        Index("ix_mcp_invocation_audit_server_time", "server_id", "timestamp"),
        Index("ix_mcp_invocation_audit_outcome", "outcome"),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    principal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    server_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("mcp_server_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_identifier: Mapped[str] = mapped_column(String(length=512), nullable=False)
    direction: Mapped[MCPInvocationDirection] = mapped_column(
        SAEnum(MCPInvocationDirection, name="mcp_invocation_direction"),
        nullable=False,
    )
    outcome: Mapped[MCPInvocationOutcome] = mapped_column(
        SAEnum(MCPInvocationOutcome, name="mcp_invocation_outcome"),
        nullable=False,
    )
    policy_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    payload_size_bytes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    error_classification: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
