"""Create runtime_warm_pool_targets table."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "043_runtime_warm_pool_targets"
down_revision = "042_prescreener_guardrail_layer"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("runtime_warm_pool_targets"):
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
    if not _index_exists("runtime_warm_pool_targets", "ix_runtime_warm_pool_targets_lookup"):
        op.create_index(
            "ix_runtime_warm_pool_targets_lookup",
            "runtime_warm_pool_targets",
            ["workspace_id", "agent_type"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("runtime_warm_pool_targets") and _index_exists(
        "runtime_warm_pool_targets", "ix_runtime_warm_pool_targets_lookup"
    ):
        op.drop_index("ix_runtime_warm_pool_targets_lookup", table_name="runtime_warm_pool_targets")
    if _table_exists("runtime_warm_pool_targets"):
        op.drop_table("runtime_warm_pool_targets")
