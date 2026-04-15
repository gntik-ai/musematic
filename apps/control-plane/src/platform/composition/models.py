from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin, WorkspaceScopedMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CompositionRequestType(StrEnum):
    """Supported composition request types."""

    agent = "agent"
    fleet = "fleet"


class CompositionRequestStatus(StrEnum):
    """Supported composition request statuses."""

    pending = "pending"
    completed = "completed"
    failed = "failed"


class MaturityEstimate(StrEnum):
    """Supported agent blueprint maturity estimates."""

    experimental = "experimental"
    developing = "developing"
    production_ready = "production_ready"


class TopologyType(StrEnum):
    """Supported fleet topology types."""

    sequential = "sequential"
    hierarchical = "hierarchical"
    peer = "peer"
    hybrid = "hybrid"


class CompositionAuditEventType(StrEnum):
    """Append-only composition audit event types."""

    blueprint_generated = "blueprint_generated"
    blueprint_validated = "blueprint_validated"
    blueprint_overridden = "blueprint_overridden"
    blueprint_finalized = "blueprint_finalized"
    generation_failed = "generation_failed"


class CompositionRequest(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Root record for a composition request."""

    __tablename__ = "composition_requests"
    __table_args__ = (
        Index("ix_composition_requests_workspace_status", "workspace_id", "status"),
        Index("ix_composition_requests_workspace_type", "workspace_id", "request_type"),
        CheckConstraint("request_type IN ('agent', 'fleet')", name="ck_composition_request_type"),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_composition_request_status",
        ),
    )

    request_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    llm_model_used: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    generation_time_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    agent_blueprints: Mapped[list[AgentBlueprint]] = relationship(
        "platform.composition.models.AgentBlueprint",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="platform.composition.models.AgentBlueprint.version.asc()",
    )
    fleet_blueprints: Mapped[list[FleetBlueprint]] = relationship(
        "platform.composition.models.FleetBlueprint",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="platform.composition.models.FleetBlueprint.version.asc()",
    )
    audit_entries: Mapped[list[CompositionAuditEntry]] = relationship(
        "platform.composition.models.CompositionAuditEntry",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="platform.composition.models.CompositionAuditEntry.created_at.asc()",
    )


class AgentBlueprint(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """AI-generated agent configuration proposal."""

    __tablename__ = "composition_agent_blueprints"
    __table_args__ = (
        Index("ix_agent_blueprints_workspace", "workspace_id"),
        Index(
            "uq_agent_blueprints_request_version",
            "request_id",
            "version",
            unique=True,
        ),
        CheckConstraint(
            "maturity_estimate IN ('experimental', 'developing', 'production_ready')",
            name="ck_agent_blueprints_maturity_estimate",
        ),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_agent_blueprints_confidence_range",
        ),
    )

    request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("composition_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    model_config: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    tool_selections: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    connector_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    policy_recommendations: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    context_profile: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    maturity_estimate: Mapped[str] = mapped_column(String(length=32), nullable=False)
    maturity_reasoning: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    confidence_score: Mapped[float] = mapped_column(Float(), nullable=False)
    low_confidence: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    follow_up_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    llm_reasoning_summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    alternatives_considered: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )

    request: Mapped[CompositionRequest] = relationship(
        "platform.composition.models.CompositionRequest",
        back_populates="agent_blueprints",
    )
    validations: Mapped[list[CompositionValidation]] = relationship(
        "platform.composition.models.CompositionValidation",
        back_populates="agent_blueprint",
        cascade="all, delete-orphan",
    )


class FleetBlueprint(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """AI-generated fleet configuration proposal."""

    __tablename__ = "composition_fleet_blueprints"
    __table_args__ = (
        Index("ix_fleet_blueprints_workspace", "workspace_id"),
        Index(
            "uq_fleet_blueprints_request_version",
            "request_id",
            "version",
            unique=True,
        ),
        CheckConstraint(
            "topology_type IN ('sequential', 'hierarchical', 'peer', 'hybrid')",
            name="ck_fleet_blueprints_topology_type",
        ),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_fleet_blueprints_confidence_range",
        ),
    )

    request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("composition_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    topology_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    member_roles: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    orchestration_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    delegation_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    escalation_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    confidence_score: Mapped[float] = mapped_column(Float(), nullable=False)
    low_confidence: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    follow_up_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    llm_reasoning_summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    alternatives_considered: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    single_agent_suggestion: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    request: Mapped[CompositionRequest] = relationship(
        "platform.composition.models.CompositionRequest",
        back_populates="fleet_blueprints",
    )
    validations: Mapped[list[CompositionValidation]] = relationship(
        "platform.composition.models.CompositionValidation",
        back_populates="fleet_blueprint",
        cascade="all, delete-orphan",
    )


class CompositionValidation(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Validation results for an agent or fleet blueprint."""

    __tablename__ = "composition_validations"
    __table_args__ = (
        CheckConstraint(
            "(agent_blueprint_id IS NOT NULL) != (fleet_blueprint_id IS NOT NULL)",
            name="ck_composition_validations_one_blueprint_ref",
        ),
        Index("ix_validations_agent_blueprint", "agent_blueprint_id"),
        Index("ix_validations_fleet_blueprint", "fleet_blueprint_id"),
    )

    agent_blueprint_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("composition_agent_blueprints.id", ondelete="CASCADE"),
        nullable=True,
    )
    fleet_blueprint_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("composition_fleet_blueprints.id", ondelete="CASCADE"),
        nullable=True,
    )
    overall_valid: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    tools_check_passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    tools_check_details: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    model_check_passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    model_check_details: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    connectors_check_passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    connectors_check_details: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    policy_check_passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    policy_check_details: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    cycle_check_passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    cycle_check_details: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
    )

    agent_blueprint: Mapped[AgentBlueprint | None] = relationship(
        "platform.composition.models.AgentBlueprint",
        back_populates="validations",
    )
    fleet_blueprint: Mapped[FleetBlueprint | None] = relationship(
        "platform.composition.models.FleetBlueprint",
        back_populates="validations",
    )


class CompositionAuditEntry(Base, UUIDMixin, WorkspaceScopedMixin):
    """Append-only audit entry for a composition request."""

    __tablename__ = "composition_audit_entries"
    __table_args__ = (
        Index("ix_audit_entries_request_id", "request_id"),
        Index("ix_audit_entries_workspace_created", "workspace_id", "created_at"),
        CheckConstraint(
            "event_type IN ('blueprint_generated', 'blueprint_validated', "
            "'blueprint_overridden', 'blueprint_finalized', 'generation_failed')",
            name="ck_composition_audit_event_type",
        ),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("composition_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)

    request: Mapped[CompositionRequest] = relationship(
        "platform.composition.models.CompositionRequest",
        back_populates="audit_entries",
    )
