"""Add workspace proximity graph settings and hypothesis embedding status."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "056_proximity_graph_workspace"
down_revision = "055_adaptation_context_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_hypotheses",
        sa.Column(
            "embedding_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "discovery_hypotheses",
        sa.Column("rationale_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE discovery_hypotheses
        SET embedding_status = CASE
            WHEN qdrant_point_id IS NOT NULL THEN 'indexed'
            ELSE 'pending'
        END
        """
    )
    op.create_index(
        "ix_discovery_hypotheses_embedding_pending",
        "discovery_hypotheses",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("embedding_status = 'pending'"),
    )

    op.drop_constraint(
        "uq_cluster_session_label",
        "discovery_hypothesis_clusters",
        type_="unique",
    )
    op.alter_column(
        "discovery_hypothesis_clusters",
        "session_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_index(
        "uq_cluster_session_label",
        "discovery_hypothesis_clusters",
        ["session_id", "cluster_label"],
        unique=True,
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )

    op.create_table(
        "discovery_workspace_settings",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "bias_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "recompute_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("15"),
        ),
        sa.Column("last_recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_transition_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
    )


def downgrade() -> None:
    op.drop_table("discovery_workspace_settings")

    op.drop_index("uq_cluster_session_label", table_name="discovery_hypothesis_clusters")
    op.alter_column(
        "discovery_hypothesis_clusters",
        "session_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_cluster_session_label",
        "discovery_hypothesis_clusters",
        ["session_id", "cluster_label"],
    )

    op.drop_index(
        "ix_discovery_hypotheses_embedding_pending",
        table_name="discovery_hypotheses",
    )
    op.drop_column("discovery_hypotheses", "rationale_metadata")
    op.drop_column("discovery_hypotheses", "embedding_status")
