from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from platform.multi_region_ops.constants import (
    FAILOVER_PLAN_RUN_KINDS,
    FAILOVER_PLAN_RUN_OUTCOMES,
    MAINTENANCE_STATUSES,
    REGION_ROLES,
    REPLICATION_COMPONENTS,
    REPLICATION_HEALTH,
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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _check_values(column: str, values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class RegionConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "region_configs"
    __table_args__ = (
        UniqueConstraint("region_code", name="uq_region_configs_region_code"),
        CheckConstraint(_check_values("region_role", REGION_ROLES), name="ck_region_configs_role"),
        Index(
            "uq_region_configs_single_enabled_primary",
            "region_role",
            unique=True,
            postgresql_where=text("region_role = 'primary' AND enabled = true"),
        ),
    )

    region_code: Mapped[str] = mapped_column(String(length=32), nullable=False)
    region_role: Mapped[str] = mapped_column(String(length=16), nullable=False)
    endpoint_urls: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    rpo_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    rto_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReplicationStatus(Base, UUIDMixin):
    __tablename__ = "replication_statuses"
    __table_args__ = (
        CheckConstraint(
            _check_values("component", REPLICATION_COMPONENTS),
            name="ck_replication_statuses_component",
        ),
        CheckConstraint(
            _check_values("health", REPLICATION_HEALTH),
            name="ck_replication_statuses_health",
        ),
        Index(
            "ix_replication_status_tuple_measured",
            "source_region",
            "target_region",
            "component",
            text("measured_at DESC"),
        ),
    )

    source_region: Mapped[str] = mapped_column(String(length=32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(length=32), nullable=False)
    component: Mapped[str] = mapped_column(String(length=64), nullable=False)
    lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health: Mapped[str] = mapped_column(String(length=16), nullable=False)
    pause_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FailoverPlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "failover_plans"
    __table_args__ = (
        UniqueConstraint("name", name="uq_failover_plans_name"),
        Index("ix_failover_plans_region_pair", "from_region", "to_region"),
    )

    name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    from_region: Mapped[str] = mapped_column(String(length=32), nullable=False)
    to_region: Mapped[str] = mapped_column(String(length=32), nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    runbook_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FailoverPlanRun(Base, UUIDMixin):
    __tablename__ = "failover_plan_runs"
    __table_args__ = (
        CheckConstraint(
            _check_values("run_kind", FAILOVER_PLAN_RUN_KINDS),
            name="ck_failover_plan_runs_kind",
        ),
        CheckConstraint(
            _check_values("outcome", FAILOVER_PLAN_RUN_OUTCOMES),
            name="ck_failover_plan_runs_outcome",
        ),
        Index("ix_failover_plan_runs_plan_started", "plan_id", text("started_at DESC")),
        Index(
            "ix_failover_plan_runs_in_progress",
            "outcome",
            postgresql_where=text("outcome = 'in_progress'"),
        ),
    )

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("failover_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_kind: Mapped[str] = mapped_column(String(length=16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(length=16), nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    initiated_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    lock_token: Mapped[str] = mapped_column(String(length=128), nullable=False)


class MaintenanceWindow(Base, UUIDMixin):
    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_maintenance_windows_end_after_start"),
        CheckConstraint(
            _check_values("status", MAINTENANCE_STATUSES),
            name="ck_maintenance_windows_status",
        ),
        Index(
            "uq_maintenance_windows_single_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_maintenance_windows_time_range", "starts_at", "ends_at"),
    )

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    blocks_writes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    announcement_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="scheduled")
    scheduled_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disable_failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
