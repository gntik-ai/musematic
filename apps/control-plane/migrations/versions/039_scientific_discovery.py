"""Scientific discovery orchestration schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "039_scientific_discovery"
down_revision = "038_ai_agent_composition"
branch_labels = None
depends_on = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def _workspace() -> sa.Column[object]:
    return sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "discovery_sessions",
        _uuid_pk(),
        _workspace(),
        sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column(
            "corpus_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_cycle", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("convergence_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('active', 'converged', 'halted', 'iteration_limit_reached')",
            name="ck_discovery_sessions_status",
        ),
    )
    op.create_index(
        "ix_discovery_sessions_workspace_status",
        "discovery_sessions",
        ["workspace_id", "status"],
    )
    op.create_index("ix_discovery_sessions_workspace_id", "discovery_sessions", ["workspace_id"])

    op.create_table(
        "discovery_gde_cycles",
        _uuid_pk(),
        _workspace(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("generation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "debate_record",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("refinement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("convergence_metric", sa.Float(), nullable=True),
        sa.Column("converged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "cycle_number", name="uq_cycle_session_number"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="ck_gde_cycles_status"
        ),
    )
    op.create_index("ix_gde_cycles_session_id", "discovery_gde_cycles", ["session_id"])
    op.create_index(
        "ix_discovery_gde_cycles_workspace_id", "discovery_gde_cycles", ["workspace_id"]
    )

    op.create_table(
        "discovery_hypotheses",
        _uuid_pk(),
        _workspace(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("generating_agent_fqn", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("qdrant_point_id", sa.String(length=128), nullable=True),
        sa.Column("cluster_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["discovery_gde_cycles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["discovery_hypotheses.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'merged', 'retired')", name="ck_hypotheses_status"
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_hypotheses_confidence"
        ),
    )
    op.create_index("ix_hypotheses_session_id", "discovery_hypotheses", ["session_id"])
    op.create_index(
        "ix_hypotheses_workspace_status",
        "discovery_hypotheses",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_discovery_hypotheses_workspace_id", "discovery_hypotheses", ["workspace_id"]
    )

    op.create_table(
        "discovery_critiques",
        _uuid_pk(),
        _workspace(),
        sa.Column("hypothesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_agent_fqn", sa.String(length=255), nullable=False),
        sa.Column("scores", postgresql.JSONB(), nullable=False),
        sa.Column("composite_summary", postgresql.JSONB(), nullable=True),
        sa.Column("is_aggregated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["discovery_hypotheses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_critiques_hypothesis_id", "discovery_critiques", ["hypothesis_id"])
    op.create_index("ix_critiques_session_id", "discovery_critiques", ["session_id"])
    op.create_index("ix_discovery_critiques_workspace_id", "discovery_critiques", ["workspace_id"])

    op.create_table(
        "discovery_tournament_rounds",
        _uuid_pk(),
        _workspace(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column(
            "pairwise_results",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "elo_changes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("bye_hypothesis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["discovery_gde_cycles.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('completed', 'in_progress', 'failed')",
            name="ck_tournament_rounds_status",
        ),
    )
    op.create_index(
        "ix_tournament_rounds_session_id",
        "discovery_tournament_rounds",
        ["session_id"],
    )
    op.create_index(
        "ix_discovery_tournament_rounds_workspace_id",
        "discovery_tournament_rounds",
        ["workspace_id"],
    )

    op.create_table(
        "discovery_elo_scores",
        _uuid_pk(),
        _workspace(),
        sa.Column("hypothesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_score", sa.Float(), nullable=False, server_default="1000"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draws", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "score_history",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["discovery_hypotheses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hypothesis_id", "session_id", name="uq_elo_hypothesis_session"),
    )
    op.create_index("ix_elo_scores_session_id", "discovery_elo_scores", ["session_id"])
    op.create_index(
        "ix_discovery_elo_scores_workspace_id", "discovery_elo_scores", ["workspace_id"]
    )

    op.create_table(
        "discovery_experiments",
        _uuid_pk(),
        _workspace(),
        sa.Column("hypothesis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("governance_status", sa.String(length=16), nullable=False),
        sa.Column(
            "governance_violations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("execution_status", sa.String(length=16), nullable=False),
        sa.Column("sandbox_execution_id", sa.String(length=128), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("designed_by_agent_fqn", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["discovery_hypotheses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "governance_status IN ('pending', 'approved', 'rejected')",
            name="ck_experiments_governance_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('not_started', 'running', 'completed', 'failed', 'timeout')",
            name="ck_experiments_execution_status",
        ),
    )
    op.create_index("ix_experiments_hypothesis_id", "discovery_experiments", ["hypothesis_id"])
    op.create_index("ix_experiments_session_id", "discovery_experiments", ["session_id"])
    op.create_index(
        "ix_discovery_experiments_workspace_id", "discovery_experiments", ["workspace_id"]
    )

    op.create_table(
        "discovery_hypothesis_clusters",
        _uuid_pk(),
        _workspace(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_label", sa.String(length=128), nullable=False),
        sa.Column("centroid_description", sa.Text(), nullable=False),
        sa.Column("hypothesis_count", sa.Integer(), nullable=False),
        sa.Column("density_metric", sa.Float(), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column(
            "hypothesis_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["session_id"], ["discovery_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "cluster_label", name="uq_cluster_session_label"),
        sa.CheckConstraint(
            "classification IN ('normal', 'over_explored', 'gap')",
            name="ck_clusters_classification",
        ),
    )
    op.create_index("ix_clusters_session_id", "discovery_hypothesis_clusters", ["session_id"])
    op.create_index(
        "ix_discovery_hypothesis_clusters_workspace_id",
        "discovery_hypothesis_clusters",
        ["workspace_id"],
    )


def downgrade() -> None:
    for table in (
        "discovery_hypothesis_clusters",
        "discovery_experiments",
        "discovery_elo_scores",
        "discovery_tournament_rounds",
        "discovery_critiques",
        "discovery_hypotheses",
        "discovery_gde_cycles",
        "discovery_sessions",
    ):
        op.drop_table(table)
