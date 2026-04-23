"""Create trajectory evaluation and rubric calibration schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "054_trajectory_evaluation_schema"
down_revision = "053_mcp_integration"
branch_labels = None
depends_on = None

rubric_status = postgresql.ENUM(
    "active",
    "archived",
    name="rubric_status",
    create_type=False,
    _create_events=False,
)
calibration_run_status = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="calibration_run_status",
    create_type=False,
    _create_events=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    rubric_status.create(bind, checkfirst=True)
    calibration_run_status.create(bind, checkfirst=True)

    op.create_table(
        "evaluation_rubrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", rubric_status, nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces_workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_evaluation_rubrics_workspace_id", "evaluation_rubrics", ["workspace_id"], unique=False
    )
    op.create_index("ix_evaluation_rubrics_status", "evaluation_rubrics", ["status"], unique=False)
    op.create_index(
        "ix_evaluation_rubrics_is_builtin", "evaluation_rubrics", ["is_builtin"], unique=False
    )
    op.create_index(
        "uq_evaluation_rubrics_builtin_name",
        "evaluation_rubrics",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_builtin = true"),
    )

    op.create_table(
        "evaluation_calibration_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("rubric_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("judge_model", sa.Text(), nullable=False),
        sa.Column("reference_set_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            calibration_run_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agreement_rate", sa.Float(), nullable=True),
        sa.Column("calibrated", sa.Boolean(), nullable=True),
        sa.Column(
            "error_grade_finding",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["rubric_id"], ["evaluation_rubrics.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_evaluation_calibration_runs_rubric_id",
        "evaluation_calibration_runs",
        ["rubric_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_calibration_runs_status",
        "evaluation_calibration_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_calibration_runs_status", table_name="evaluation_calibration_runs")
    op.drop_index(
        "ix_evaluation_calibration_runs_rubric_id", table_name="evaluation_calibration_runs"
    )
    op.drop_table("evaluation_calibration_runs")

    op.drop_index("uq_evaluation_rubrics_builtin_name", table_name="evaluation_rubrics")
    op.drop_index("ix_evaluation_rubrics_is_builtin", table_name="evaluation_rubrics")
    op.drop_index("ix_evaluation_rubrics_status", table_name="evaluation_rubrics")
    op.drop_index("ix_evaluation_rubrics_workspace_id", table_name="evaluation_rubrics")
    op.drop_table("evaluation_rubrics")

    bind = op.get_bind()
    calibration_run_status.drop(bind, checkfirst=True)
    rubric_status.drop(bind, checkfirst=True)
