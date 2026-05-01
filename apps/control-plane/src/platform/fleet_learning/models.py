from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransferRequestStatus(StrEnum):
    proposed = "proposed"
    approved = "approved"
    applied = "applied"
    rejected = "rejected"


class CommunicationStyle(StrEnum):
    verbose = "verbose"
    concise = "concise"
    structured = "structured"


class DecisionSpeed(StrEnum):
    fast = "fast"
    deliberate = "deliberate"
    consensus_seeking = "consensus_seeking"


class RiskTolerance(StrEnum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class AutonomyLevel(StrEnum):
    supervised = "supervised"
    semi_autonomous = "semi_autonomous"
    fully_autonomous = "fully_autonomous"


class FleetPerformanceProfile(
    Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin
):
    __tablename__ = "fleet_performance_profiles"
    __table_args__ = (
        Index("ix_fleet_performance_profiles_fleet_id", "fleet_id"),
        Index(
            "ix_fleet_performance_profiles_fleet_period",
            "fleet_id",
            "period_start",
            "period_end",
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    avg_completion_time_ms: Mapped[float] = mapped_column(nullable=False, default=0.0)
    success_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    cost_per_task: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_quality_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    throughput_per_hour: Mapped[float] = mapped_column(nullable=False, default=0.0)
    member_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    flagged_member_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )


class FleetAdaptationRule(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_adaptation_rules"
    __table_args__ = (
        Index("ix_fleet_adaptation_rules_fleet_id", "fleet_id"),
        Index("ix_fleet_adaptation_rules_fleet_priority", "fleet_id", "priority"),
    )

    fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    condition: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    action: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FleetAdaptationLog(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "fleet_adaptation_log"
    __table_args__ = (
        Index("ix_fleet_adaptation_log_fleet_id", "fleet_id"),
        Index("ix_fleet_adaptation_log_rule_id", "adaptation_rule_id"),
    )

    fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    adaptation_rule_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleet_adaptation_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    before_rules_version: Mapped[int] = mapped_column(Integer, nullable=False)
    after_rules_version: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_reverted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrossFleetTransferRequest(
    Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin
):
    __tablename__ = "cross_fleet_transfer_requests"
    __table_args__ = (
        Index("ix_cross_fleet_transfer_requests_source_fleet_id", "source_fleet_id"),
        Index("ix_cross_fleet_transfer_requests_target_fleet_id", "target_fleet_id"),
        Index("ix_cross_fleet_transfer_requests_status", "status"),
    )

    source_fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    target_fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[TransferRequestStatus] = mapped_column(
        SAEnum(TransferRequestStatus, name="fleet_transfer_request_status"),
        nullable=False,
        default=TransferRequestStatus.proposed,
    )
    pattern_definition: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    pattern_minio_key: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)
    proposed_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    approved_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FleetPersonalityProfile(
    Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin
):
    __tablename__ = "fleet_personality_profiles"
    __table_args__ = (
        Index("ix_fleet_personality_profiles_fleet_id", "fleet_id"),
        Index("uq_fleet_personality_profiles_fleet_version", "fleet_id", "version", unique=True),
        Index(
            "uq_fleet_personality_profiles_current",
            "fleet_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    communication_style: Mapped[CommunicationStyle] = mapped_column(
        SAEnum(CommunicationStyle, name="fleet_communication_style"),
        nullable=False,
    )
    decision_speed: Mapped[DecisionSpeed] = mapped_column(
        SAEnum(DecisionSpeed, name="fleet_decision_speed"),
        nullable=False,
    )
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(
        SAEnum(RiskTolerance, name="fleet_risk_tolerance"),
        nullable=False,
    )
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        SAEnum(AutonomyLevel, name="fleet_autonomy_level"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
