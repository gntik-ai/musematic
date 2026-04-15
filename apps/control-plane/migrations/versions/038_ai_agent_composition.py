"""AI-assisted agent composition schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "038_ai_agent_composition"
down_revision = "037_agentops_lifecycle"
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


def upgrade() -> None:
    op.create_table(
        "composition_requests",
        _uuid_pk(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("llm_model_used", sa.String(length=255), nullable=True),
        sa.Column("generation_time_ms", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "request_type IN ('agent', 'fleet')",
            name="ck_composition_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_composition_request_status",
        ),
    )
    op.create_index(
        "ix_composition_requests_workspace_status",
        "composition_requests",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_composition_requests_workspace_type",
        "composition_requests",
        ["workspace_id", "request_type"],
    )

    op.create_table(
        "composition_agent_blueprints",
        _uuid_pk(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("model_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_selections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("connector_suggestions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "policy_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("context_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("maturity_estimate", sa.String(length=32), nullable=False),
        sa.Column("maturity_reasoning", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("follow_up_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_reasoning_summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "alternatives_considered",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "maturity_estimate IN ('experimental', 'developing', 'production_ready')",
            name="ck_agent_blueprints_maturity_estimate",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_agent_blueprints_confidence_range",
        ),
    )
    op.create_index(
        "ix_agent_blueprints_workspace",
        "composition_agent_blueprints",
        ["workspace_id"],
    )
    op.create_index(
        "uq_agent_blueprints_request_version",
        "composition_agent_blueprints",
        ["request_id", "version"],
        unique=True,
    )

    op.create_table(
        "composition_fleet_blueprints",
        _uuid_pk(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("topology_type", sa.String(length=32), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("member_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("orchestration_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delegation_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("escalation_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("follow_up_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_reasoning_summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "alternatives_considered",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "single_agent_suggestion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "topology_type IN ('sequential', 'hierarchical', 'peer', 'hybrid')",
            name="ck_fleet_blueprints_topology_type",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_fleet_blueprints_confidence_range",
        ),
    )
    op.create_index(
        "ix_fleet_blueprints_workspace",
        "composition_fleet_blueprints",
        ["workspace_id"],
    )
    op.create_index(
        "uq_fleet_blueprints_request_version",
        "composition_fleet_blueprints",
        ["request_id", "version"],
        unique=True,
    )

    op.create_table(
        "composition_validations",
        _uuid_pk(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "agent_blueprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_agent_blueprints.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "fleet_blueprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_fleet_blueprints.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("overall_valid", sa.Boolean(), nullable=False),
        sa.Column("tools_check_passed", sa.Boolean(), nullable=True),
        sa.Column("tools_check_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_check_passed", sa.Boolean(), nullable=True),
        sa.Column("model_check_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("connectors_check_passed", sa.Boolean(), nullable=True),
        sa.Column(
            "connectors_check_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("policy_check_passed", sa.Boolean(), nullable=True),
        sa.Column("policy_check_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cycle_check_passed", sa.Boolean(), nullable=True),
        sa.Column("cycle_check_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(agent_blueprint_id IS NOT NULL) != (fleet_blueprint_id IS NOT NULL)",
            name="ck_composition_validations_one_blueprint_ref",
        ),
    )
    op.create_index(
        "ix_validations_agent_blueprint",
        "composition_validations",
        ["agent_blueprint_id"],
    )
    op.create_index(
        "ix_validations_fleet_blueprint",
        "composition_validations",
        ["fleet_blueprint_id"],
    )

    op.create_table(
        "composition_audit_entries",
        _uuid_pk(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('blueprint_generated', 'blueprint_validated', "
            "'blueprint_overridden', 'blueprint_finalized', 'generation_failed')",
            name="ck_composition_audit_event_type",
        ),
    )
    op.create_index(
        "ix_audit_entries_request_id",
        "composition_audit_entries",
        ["request_id"],
    )
    op.create_index(
        "ix_audit_entries_workspace_created",
        "composition_audit_entries",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_entries_workspace_created", table_name="composition_audit_entries")
    op.drop_index("ix_audit_entries_request_id", table_name="composition_audit_entries")
    op.drop_table("composition_audit_entries")
    op.drop_index("ix_validations_fleet_blueprint", table_name="composition_validations")
    op.drop_index("ix_validations_agent_blueprint", table_name="composition_validations")
    op.drop_table("composition_validations")
    op.drop_index("uq_fleet_blueprints_request_version", table_name="composition_fleet_blueprints")
    op.drop_index("ix_fleet_blueprints_workspace", table_name="composition_fleet_blueprints")
    op.drop_table("composition_fleet_blueprints")
    op.drop_index("uq_agent_blueprints_request_version", table_name="composition_agent_blueprints")
    op.drop_index("ix_agent_blueprints_workspace", table_name="composition_agent_blueprints")
    op.drop_table("composition_agent_blueprints")
    op.drop_index("ix_composition_requests_workspace_type", table_name="composition_requests")
    op.drop_index("ix_composition_requests_workspace_status", table_name="composition_requests")
    op.drop_table("composition_requests")
