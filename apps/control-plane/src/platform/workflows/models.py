from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    AuditMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class WorkflowStatus(StrEnum):
    """Represent the workflow status."""

    active = "active"
    archived = "archived"
    draft = "draft"


class TriggerType(StrEnum):
    """Represent the trigger type."""

    webhook = "webhook"
    cron = "cron"
    orchestrator = "orchestrator"
    manual = "manual"
    api = "api"
    event_bus = "event_bus"
    workspace_goal = "workspace_goal"


class WorkflowDefinition(
    Base, TenantScopedMixin, UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin
):
    """Represent the workflow definition."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("ix_workflow_definitions_name", "name"),
        Index("ix_workflow_definitions_status", "status"),
        Index(
            "uq_workflow_definitions_workspace_name",
            "workspace_id",
            "name",
            unique=True,
        ),
    )

    name: Mapped[str] = mapped_column(String(length=200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        SAEnum(WorkflowStatus, name="workflow_status"),
        nullable=False,
        default=WorkflowStatus.active,
    )
    current_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)

    versions: Mapped[list[WorkflowVersion]] = relationship(
        "platform.workflows.models.WorkflowVersion",
        foreign_keys="platform.workflows.models.WorkflowVersion.definition_id",
        back_populates="definition",
        order_by="platform.workflows.models.WorkflowVersion.version_number.asc()",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[WorkflowVersion | None] = relationship(
        "platform.workflows.models.WorkflowVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    trigger_definitions: Mapped[list[WorkflowTriggerDefinition]] = relationship(
        "platform.workflows.models.WorkflowTriggerDefinition",
        back_populates="definition",
        cascade="all, delete-orphan",
    )


class WorkflowVersion(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    """Represent the workflow version."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        Index("ix_workflow_versions_definition_id", "definition_id"),
        Index(
            "uq_workflow_versions_definition_version",
            "definition_id",
            "version_number",
            unique=True,
        ),
    )

    definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    yaml_source: Mapped[str] = mapped_column(Text(), nullable=False)
    compiled_ir: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    schema_version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    change_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    checkpoint_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    definition: Mapped[WorkflowDefinition] = relationship(
        "platform.workflows.models.WorkflowDefinition",
        foreign_keys=[definition_id],
        back_populates="versions",
    )


class WorkflowTriggerDefinition(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    """Represent the workflow trigger definition."""

    __tablename__ = "workflow_trigger_definitions"
    __table_args__ = (
        Index("ix_workflow_trigger_definitions_definition_id", "definition_id"),
        Index("ix_workflow_trigger_definitions_type", "trigger_type"),
        Index("ix_workflow_trigger_definitions_is_active", "is_active"),
    )

    definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        SAEnum(TriggerType, name="workflow_trigger_type"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    max_concurrent_executions: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(nullable=True)

    definition: Mapped[WorkflowDefinition] = relationship(
        "platform.workflows.models.WorkflowDefinition",
        back_populates="trigger_definitions",
    )
