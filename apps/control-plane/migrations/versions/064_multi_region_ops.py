"""Multi-region operations.

Revision ID: 064_multi_region_ops
Revises: 063_incident_response
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "064_multi_region_ops"
down_revision: str | None = "063_incident_response"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGION_ROLES = ("primary", "secondary")
REPLICATION_COMPONENTS = (
    "postgres",
    "kafka",
    "s3",
    "clickhouse",
    "qdrant",
    "neo4j",
    "opensearch",
)
REPLICATION_HEALTH = ("healthy", "degraded", "unhealthy", "paused")
MAINTENANCE_STATUSES = ("scheduled", "active", "completed", "cancelled")
FAILOVER_PLAN_RUN_KINDS = ("rehearsal", "production")
FAILOVER_PLAN_RUN_OUTCOMES = ("succeeded", "failed", "aborted", "in_progress")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def _jsonb(name: str, default: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=nullable,
        server_default=sa.text(default),
    )


def _check(column: str, values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "region_configs",
        _uuid_pk(),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("region_role", sa.String(length=16), nullable=False),
        _jsonb("endpoint_urls", "'{}'::jsonb"),
        sa.Column("rpo_target_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("rto_target_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("region_code", name="uq_region_configs_region_code"),
        sa.CheckConstraint(_check("region_role", REGION_ROLES), name="ck_region_configs_role"),
    )
    op.create_index(
        "uq_region_configs_single_enabled_primary",
        "region_configs",
        ["region_role"],
        unique=True,
        postgresql_where=sa.text("region_role = 'primary' AND enabled = true"),
    )

    op.create_table(
        "replication_statuses",
        _uuid_pk(),
        sa.Column("source_region", sa.String(length=32), nullable=False),
        sa.Column("target_region", sa.String(length=32), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("lag_seconds", sa.Integer(), nullable=True),
        sa.Column("health", sa.String(length=16), nullable=False),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        _ts("measured_at"),
        sa.CheckConstraint(
            _check("component", REPLICATION_COMPONENTS),
            name="ck_replication_statuses_component",
        ),
        sa.CheckConstraint(
            _check("health", REPLICATION_HEALTH),
            name="ck_replication_statuses_health",
        ),
    )
    op.create_index(
        "ix_replication_status_tuple_measured",
        "replication_statuses",
        [
            "source_region",
            "target_region",
            "component",
            sa.text("measured_at DESC"),
        ],
    )

    op.create_table(
        "failover_plans",
        _uuid_pk(),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("from_region", sa.String(length=32), nullable=False),
        sa.Column("to_region", sa.String(length=32), nullable=False),
        _jsonb("steps", "'[]'::jsonb"),
        sa.Column("runbook_url", sa.Text(), nullable=True),
        _ts("tested_at", nullable=True),
        _ts("last_executed_at", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("name", name="uq_failover_plans_name"),
    )
    op.create_index(
        "ix_failover_plans_region_pair",
        "failover_plans",
        ["from_region", "to_region"],
    )

    op.create_table(
        "failover_plan_runs",
        _uuid_pk(),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("failover_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_kind", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="in_progress"),
        _ts("started_at"),
        _ts("ended_at", nullable=True),
        _jsonb("step_outcomes", "'[]'::jsonb"),
        sa.Column(
            "initiated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("lock_token", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            _check("run_kind", FAILOVER_PLAN_RUN_KINDS),
            name="ck_failover_plan_runs_kind",
        ),
        sa.CheckConstraint(
            _check("outcome", FAILOVER_PLAN_RUN_OUTCOMES),
            name="ck_failover_plan_runs_outcome",
        ),
    )
    op.create_index(
        "ix_failover_plan_runs_plan_started",
        "failover_plan_runs",
        ["plan_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_failover_plan_runs_in_progress",
        "failover_plan_runs",
        ["outcome"],
        postgresql_where=sa.text("outcome = 'in_progress'"),
    )

    op.create_table(
        "maintenance_windows",
        _uuid_pk(),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("blocks_writes", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("announcement_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column(
            "scheduled_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("enabled_at", nullable=True),
        _ts("disabled_at", nullable=True),
        sa.Column("disable_failure_reason", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_maintenance_windows_end_after_start",
        ),
        sa.CheckConstraint(
            _check("status", MAINTENANCE_STATUSES),
            name="ck_maintenance_windows_status",
        ),
    )
    op.create_index(
        "uq_maintenance_windows_single_active",
        "maintenance_windows",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_maintenance_windows_time_range",
        "maintenance_windows",
        ["starts_at", "ends_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_windows_time_range", table_name="maintenance_windows")
    op.drop_index("uq_maintenance_windows_single_active", table_name="maintenance_windows")
    op.drop_table("maintenance_windows")
    op.drop_index("ix_failover_plan_runs_in_progress", table_name="failover_plan_runs")
    op.drop_index("ix_failover_plan_runs_plan_started", table_name="failover_plan_runs")
    op.drop_table("failover_plan_runs")
    op.drop_index("ix_failover_plans_region_pair", table_name="failover_plans")
    op.drop_table("failover_plans")
    op.drop_index("ix_replication_status_tuple_measured", table_name="replication_statuses")
    op.drop_table("replication_statuses")
    op.drop_index("uq_region_configs_single_enabled_primary", table_name="region_configs")
    op.drop_table("region_configs")
