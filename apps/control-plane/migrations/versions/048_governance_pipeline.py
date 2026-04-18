"""Add governance verdicts, enforcement actions, and workspace governance chains."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "048_governance_pipeline"
down_revision = "047_notifications_alerts"
branch_labels = None
depends_on = None

verdicttype = postgresql.ENUM(
    "COMPLIANT",
    "WARNING",
    "VIOLATION",
    "ESCALATE_TO_HUMAN",
    name="verdicttype",
    create_type=False,
)
enforcementactiontype = postgresql.ENUM(
    "block",
    "quarantine",
    "notify",
    "revoke_cert",
    "log_and_continue",
    name="enforcementactiontype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    verdicttype.create(bind, checkfirst=True)
    enforcementactiontype.create(bind, checkfirst=True)

    op.create_table(
        "governance_verdicts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("judge_agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("verdict_type", verdicttype, nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(length=64), nullable=True),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["policy_id"], ["policy_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fleet_id"], ["fleets.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_governance_verdicts_workspace_id",
        "governance_verdicts",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_verdicts_fleet_id",
        "governance_verdicts",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_verdicts_verdict_type",
        "governance_verdicts",
        ["verdict_type"],
        unique=False,
    )
    op.create_index(
        "ix_governance_verdicts_created_at",
        "governance_verdicts",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "enforcement_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("enforcer_agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("verdict_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", enforcementactiontype, nullable=False),
        sa.Column("target_agent_fqn", sa.String(length=512), nullable=True),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["verdict_id"],
            ["governance_verdicts.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_enforcement_actions_verdict_id",
        "enforcement_actions",
        ["verdict_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_actions_action_type",
        "enforcement_actions",
        ["action_type"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_actions_workspace_id",
        "enforcement_actions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_actions_created_at",
        "enforcement_actions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "workspace_governance_chains",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "observer_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "judge_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enforcer_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "policy_binding_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "verdict_to_action_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_workspace_governance_chains_version",
        "workspace_governance_chains",
        ["workspace_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_workspace_governance_chains_current",
        "workspace_governance_chains",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )
    op.create_index(
        "ix_workspace_governance_chains_workspace_id",
        "workspace_governance_chains",
        ["workspace_id"],
        unique=False,
    )

    op.add_column(
        "fleet_governance_chains",
        sa.Column(
            "verdict_to_action_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("fleet_governance_chains", "verdict_to_action_mapping")

    op.drop_index(
        "ix_workspace_governance_chains_workspace_id",
        table_name="workspace_governance_chains",
    )
    op.drop_index(
        "uq_workspace_governance_chains_current",
        table_name="workspace_governance_chains",
    )
    op.drop_index(
        "uq_workspace_governance_chains_version",
        table_name="workspace_governance_chains",
    )
    op.drop_table("workspace_governance_chains")

    op.drop_index("ix_enforcement_actions_created_at", table_name="enforcement_actions")
    op.drop_index("ix_enforcement_actions_workspace_id", table_name="enforcement_actions")
    op.drop_index("ix_enforcement_actions_action_type", table_name="enforcement_actions")
    op.drop_index("ix_enforcement_actions_verdict_id", table_name="enforcement_actions")
    op.drop_table("enforcement_actions")

    op.drop_index("ix_governance_verdicts_created_at", table_name="governance_verdicts")
    op.drop_index("ix_governance_verdicts_verdict_type", table_name="governance_verdicts")
    op.drop_index("ix_governance_verdicts_fleet_id", table_name="governance_verdicts")
    op.drop_index("ix_governance_verdicts_workspace_id", table_name="governance_verdicts")
    op.drop_table("governance_verdicts")

    bind = op.get_bind()
    enforcementactiontype.drop(bind, checkfirst=True)
    verdicttype.drop(bind, checkfirst=True)
