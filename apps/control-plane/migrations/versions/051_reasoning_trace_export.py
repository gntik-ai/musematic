"""Create reasoning trace export records."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "051_reasoning_trace_export"
down_revision = "050_reprioritization_ckpts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_reasoning_trace_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("technique", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'complete'"),
        ),
        sa.Column("compute_budget_used", sa.Float(), nullable=True),
        sa.Column("consensus_reached", sa.Boolean(), nullable=True),
        sa.Column("stabilized", sa.Boolean(), nullable=True),
        sa.Column("degradation_detected", sa.Boolean(), nullable=True),
        sa.Column(
            "compute_budget_exhausted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("effective_budget_scope", sa.String(length=16), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_reasoning_trace_records_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_reasoning_trace_records_execution_id",
        "execution_reasoning_trace_records",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "uq_execution_reasoning_trace_records_execution_step",
        "execution_reasoning_trace_records",
        ["execution_id", "step_id"],
        unique=True,
        postgresql_where=sa.text("step_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_execution_reasoning_trace_records_execution_step",
        table_name="execution_reasoning_trace_records",
    )
    op.drop_index(
        "ix_execution_reasoning_trace_records_execution_id",
        table_name="execution_reasoning_trace_records",
    )
    op.drop_table("execution_reasoning_trace_records")
