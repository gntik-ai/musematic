"""Content moderation and fairness evaluation tables.

Revision ID: 061_content_safety_fairness
Revises: 058_multi_channel_notifications
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "061_content_safety_fairness"
down_revision: str | None = "058_multi_channel_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def upgrade() -> None:
    op.create_table(
        "content_moderation_policies",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _jsonb("categories", "'[]'::jsonb"),
        _jsonb("thresholds", "'{}'::jsonb"),
        _jsonb("action_map", "'{}'::jsonb"),
        sa.Column("default_action", sa.String(length=32), nullable=False, server_default="flag"),
        sa.Column("primary_provider", sa.String(length=64), nullable=False),
        sa.Column("fallback_provider", sa.String(length=64), nullable=True),
        sa.Column(
            "tie_break_rule",
            sa.String(length=32),
            nullable=False,
            server_default="max_score",
        ),
        sa.Column(
            "provider_failure_action",
            sa.String(length=32),
            nullable=False,
            server_default="fail_closed",
        ),
        _jsonb("language_pins", "'{}'::jsonb"),
        _jsonb("agent_allowlist", "'[]'::jsonb"),
        sa.Column(
            "monthly_cost_cap_eur",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="50.0",
        ),
        sa.Column(
            "per_call_timeout_ms",
            sa.Integer(),
            nullable=False,
            server_default="2000",
        ),
        sa.Column(
            "per_execution_budget_ms",
            sa.Integer(),
            nullable=False,
            server_default="5000",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "default_action IN ('block','redact','flag')",
            name="ck_content_moderation_policy_default_action",
        ),
        sa.CheckConstraint(
            "provider_failure_action IN ('fail_closed','fail_open')",
            name="ck_content_moderation_policy_failure_action",
        ),
        sa.CheckConstraint(
            "tie_break_rule IN ('max_score','min_score','primary_only')",
            name="ck_content_moderation_policy_tie_break_rule",
        ),
        sa.CheckConstraint(
            "per_call_timeout_ms > 0 AND per_execution_budget_ms > 0",
            name="ck_content_moderation_policy_timeouts_positive",
        ),
    )
    op.create_index(
        "uq_content_moderation_policy_workspace_active",
        "content_moderation_policies",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("active = TRUE"),
    )
    op.create_index(
        "idx_content_moderation_policy_workspace_version",
        "content_moderation_policies",
        ["workspace_id", "version"],
    )

    op.create_table(
        "content_moderation_events",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_moderation_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        _jsonb("triggered_categories", "'[]'::jsonb"),
        _jsonb("scores", "'{}'::jsonb"),
        sa.Column("action_taken", sa.String(length=32), nullable=False),
        sa.Column("language_detected", sa.String(length=32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("audit_chain_ref", sa.String(length=255), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "action_taken IN ('block','redact','flag','none',"
            "'fail_closed_blocked','fail_open_delivered')",
            name="ck_content_moderation_event_action",
        ),
    )
    op.create_index(
        "idx_moderation_events_workspace_created",
        "content_moderation_events",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "idx_moderation_events_workspace_agent_created",
        "content_moderation_events",
        ["workspace_id", "agent_id", "created_at"],
    )
    op.create_index(
        "idx_moderation_events_workspace_action",
        "content_moderation_events",
        ["workspace_id", "action_taken"],
        postgresql_where=sa.text("action_taken IN ('block','redact','flag')"),
    )

    op.create_table(
        "fairness_evaluations",
        _uuid_pk(),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_agent_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_revision_id", sa.String(length=255), nullable=False),
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("group_attribute", sa.String(length=128), nullable=False),
        _jsonb("per_group_scores", "'{}'::jsonb"),
        sa.Column("spread", sa.Float(), nullable=False),
        sa.Column("fairness_band", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        _jsonb("coverage", "'{}'::jsonb"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "evaluated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("computed_at"),
        sa.CheckConstraint(
            "metric_name IN ('demographic_parity','equal_opportunity','calibration')",
            name="ck_fairness_eval_metric_name",
        ),
        sa.CheckConstraint(
            "fairness_band >= 0 AND fairness_band <= 1",
            name="ck_fairness_eval_band_range",
        ),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "metric_name",
            "group_attribute",
            name="uq_fairness_eval_run_metric_attribute",
        ),
    )
    op.create_index(
        "idx_fairness_eval_agent_revision",
        "fairness_evaluations",
        ["agent_id", "agent_revision_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_fairness_eval_agent_revision", table_name="fairness_evaluations")
    op.drop_table("fairness_evaluations")
    op.drop_index("idx_moderation_events_workspace_action", table_name="content_moderation_events")
    op.drop_index(
        "idx_moderation_events_workspace_agent_created",
        table_name="content_moderation_events",
    )
    op.drop_index(
        "idx_moderation_events_workspace_created",
        table_name="content_moderation_events",
    )
    op.drop_table("content_moderation_events")
    op.drop_index(
        "idx_content_moderation_policy_workspace_version",
        table_name="content_moderation_policies",
    )
    op.drop_index(
        "uq_content_moderation_policy_workspace_active",
        table_name="content_moderation_policies",
    )
    op.drop_table("content_moderation_policies")

