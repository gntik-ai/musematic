from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FleetStatus(StrEnum):
    active = "active"
    degraded = "degraded"
    paused = "paused"
    archived = "archived"


class FleetTopologyType(StrEnum):
    hierarchical = "hierarchical"
    peer_to_peer = "peer_to_peer"
    hybrid = "hybrid"


class FleetMemberRole(StrEnum):
    lead = "lead"
    worker = "worker"
    observer = "observer"


class FleetMemberAvailability(StrEnum):
    available = "available"
    unavailable = "unavailable"


class Fleet(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    __tablename__ = "fleets"
    __table_args__ = (
        Index("ix_fleets_workspace_status", "workspace_id", "status"),
        Index(
            "uq_fleets_workspace_name",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(length=200), nullable=False)
    status: Mapped[FleetStatus] = mapped_column(
        SAEnum(FleetStatus, name="fleet_status"),
        nullable=False,
        default=FleetStatus.active,
    )
    topology_type: Mapped[FleetTopologyType] = mapped_column(
        SAEnum(FleetTopologyType, name="fleet_topology_type"),
        nullable=False,
    )
    quorum_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FleetMember(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_members"
    __table_args__ = (
        Index("ix_fleet_members_fleet_id", "fleet_id"),
        Index("ix_fleet_members_agent_fqn", "agent_fqn"),
        Index("uq_fleet_members_fleet_agent_fqn", "fleet_id", "agent_fqn", unique=True),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    role: Mapped[FleetMemberRole] = mapped_column(
        SAEnum(FleetMemberRole, name="fleet_member_role"),
        nullable=False,
        default=FleetMemberRole.worker,
    )
    availability: Mapped[FleetMemberAvailability] = mapped_column(
        SAEnum(FleetMemberAvailability, name="fleet_member_availability"),
        nullable=False,
        default=FleetMemberAvailability.available,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


class FleetTopologyVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fleet_topology_versions"
    __table_args__ = (
        Index("ix_fleet_topology_versions_fleet_id", "fleet_id"),
        Index("uq_fleet_topology_versions_fleet_version", "fleet_id", "version", unique=True),
        Index(
            "uq_fleet_topology_versions_current",
            "fleet_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    topology_type: Mapped[FleetTopologyType] = mapped_column(
        SAEnum(FleetTopologyType, name="fleet_topology_type", create_type=False),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FleetPolicyBinding(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_policy_bindings"
    __table_args__ = (
        Index("ix_fleet_policy_bindings_fleet_id", "fleet_id"),
        Index("uq_fleet_policy_bindings_fleet_policy", "fleet_id", "policy_id", unique=True),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    bound_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class ObserverAssignment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "observer_assignments"
    __table_args__ = (
        Index("ix_observer_assignments_fleet_id", "fleet_id"),
        Index(
            "uq_observer_assignments_active",
            "fleet_id",
            "observer_fqn",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    observer_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FleetGovernanceChain(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_governance_chains"
    __table_args__ = (
        Index("ix_fleet_governance_chains_fleet_id", "fleet_id"),
        Index("uq_fleet_governance_chains_fleet_version", "fleet_id", "version", unique=True),
        Index(
            "uq_fleet_governance_chains_current",
            "fleet_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    observer_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    judge_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    enforcer_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    policy_binding_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verdict_to_action_mapping: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class FleetOrchestrationRules(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_orchestration_rules"
    __table_args__ = (
        Index("ix_fleet_orchestration_rules_fleet_id", "fleet_id"),
        Index("uq_fleet_orchestration_rules_fleet_version", "fleet_id", "version", unique=True),
        Index(
            "uq_fleet_orchestration_rules_current",
            "fleet_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    delegation: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    aggregation: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    escalation: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    conflict_resolution: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    retry: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    max_parallelism: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
