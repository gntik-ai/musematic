"""Create runtime_warm_pool_targets table."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "043_runtime_warm_pool_targets"
down_revision = "042_prescreener_guardrail_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_warm_pool_targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(length=255), nullable=False),
        sa.Column(
            "target_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "agent_type",
            name="uq_warm_pool_target_key",
        ),
    )
    op.create_index(
        "ix_runtime_warm_pool_targets_lookup",
        "runtime_warm_pool_targets",
        ["workspace_id", "agent_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_warm_pool_targets_lookup", table_name="runtime_warm_pool_targets")
    op.drop_table("runtime_warm_pool_targets")
