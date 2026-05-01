from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    SoftDeleteMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ConnectorTypeSlug(StrEnum):
    slack = "slack"
    telegram = "telegram"
    webhook = "webhook"
    email = "email"


class ConnectorInstanceStatus(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


class ConnectorHealthStatus(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    unreachable = "unreachable"
    unknown = "unknown"


class DeliveryStatus(StrEnum):
    pending = "pending"
    in_flight = "in_flight"
    delivered = "delivered"
    failed = "failed"
    dead_lettered = "dead_lettered"


class DeadLetterResolution(StrEnum):
    pending = "pending"
    redelivered = "redelivered"
    discarded = "discarded"


class ConnectorType(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "connector_types"

    slug: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecation_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    instances: Mapped[list[ConnectorInstance]] = relationship(
        "platform.connectors.models.ConnectorInstance",
        back_populates="connector_type",
    )


class ConnectorInstance(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "connector_instances"
    __table_args__ = (
        Index("ix_connector_instances_workspace_type", "workspace_id", "connector_type_id"),
        Index(
            "uq_connector_instances_workspace_name_active",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(
        "config",
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[ConnectorInstanceStatus] = mapped_column(
        SAEnum(ConnectorInstanceStatus, name="connectors_instance_status"),
        nullable=False,
        default=ConnectorInstanceStatus.enabled,
        index=True,
    )
    health_status: Mapped[ConnectorHealthStatus] = mapped_column(
        SAEnum(ConnectorHealthStatus, name="connectors_health_status"),
        nullable=False,
        default=ConnectorHealthStatus.unknown,
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    health_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_retried: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_dead_lettered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    connector_type: Mapped[ConnectorType] = relationship(
        "platform.connectors.models.ConnectorType",
        back_populates="instances",
    )
    credential_refs: Mapped[list[ConnectorCredentialRef]] = relationship(
        "platform.connectors.models.ConnectorCredentialRef",
        back_populates="connector_instance",
        cascade="all, delete-orphan",
    )
    routes: Mapped[list[ConnectorRoute]] = relationship(
        "platform.connectors.models.ConnectorRoute",
        back_populates="connector_instance",
        cascade="all, delete-orphan",
    )
    deliveries: Mapped[list[OutboundDelivery]] = relationship(
        "platform.connectors.models.OutboundDelivery",
        back_populates="connector_instance",
        cascade="all, delete-orphan",
    )


class ConnectorCredentialRef(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "connector_credential_refs"
    __table_args__ = (
        Index(
            "uq_connector_credential_refs_instance_key",
            "connector_instance_id",
            "credential_key",
            unique=True,
        ),
    )

    connector_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_key: Mapped[str] = mapped_column(String(length=255), nullable=False)
    vault_path: Mapped[str] = mapped_column(String(length=1024), nullable=False)

    connector_instance: Mapped[ConnectorInstance] = relationship(
        "platform.connectors.models.ConnectorInstance",
        back_populates="credential_refs",
    )


class ConnectorRoute(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "connector_routes"
    __table_args__ = (
        Index("ix_connector_routes_instance_priority", "connector_instance_id", "priority"),
        CheckConstraint(
            "(target_agent_fqn IS NOT NULL) OR (target_workflow_id IS NOT NULL)",
            name="ck_connector_routes_has_target",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    channel_pattern: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    sender_pattern: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        "conditions",
        JSONB,
        nullable=False,
        default=dict,
    )
    target_agent_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    target_workflow_id: Mapped[UUID | None] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    connector_instance: Mapped[ConnectorInstance] = relationship(
        "platform.connectors.models.ConnectorInstance",
        back_populates="routes",
    )


class OutboundDelivery(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "outbound_deliveries"
    __table_args__ = (
        Index("ix_outbound_deliveries_status_retry", "status", "next_retry_at"),
        Index("ix_outbound_deliveries_connector_status", "connector_instance_id", "status"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        "content",
        JSONB,
        nullable=False,
        default=dict,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, name="connectors_delivery_status"),
        nullable=False,
        default=DeliveryStatus.pending,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    source_interaction_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_execution_id: Mapped[UUID | None] = mapped_column(nullable=True)

    connector_instance: Mapped[ConnectorInstance] = relationship(
        "platform.connectors.models.ConnectorInstance",
        back_populates="deliveries",
    )
    dead_letter_entry: Mapped[DeadLetterEntry | None] = relationship(
        "platform.connectors.models.DeadLetterEntry",
        back_populates="outbound_delivery",
        uselist=False,
    )


class DeadLetterEntry(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "dead_letter_entries"
    __table_args__ = (
        Index(
            "ix_dead_letter_entries_connector_resolution",
            "connector_instance_id",
            "resolution_status",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outbound_delivery_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbound_deliveries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    connector_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolution_status: Mapped[DeadLetterResolution] = mapped_column(
        SAEnum(DeadLetterResolution, name="connectors_dead_letter_resolution"),
        nullable=False,
        default=DeadLetterResolution.pending,
    )
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_path: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)

    outbound_delivery: Mapped[OutboundDelivery] = relationship(
        "platform.connectors.models.OutboundDelivery",
        back_populates="dead_letter_entry",
    )
    connector_instance: Mapped[ConnectorInstance] = relationship(
        "platform.connectors.models.ConnectorInstance",
    )
