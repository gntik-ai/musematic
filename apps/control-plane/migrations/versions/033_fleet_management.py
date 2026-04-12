"""Fleet management and learning schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "033_fleet_management"
down_revision = "032_trust_certifications"
branch_labels = None
depends_on = None


fleet_status = postgresql.ENUM(
    "active",
    "degraded",
    "paused",
    "archived",
    name="fleet_status",
    create_type=False,
)
fleet_topology_type = postgresql.ENUM(
    "hierarchical",
    "peer_to_peer",
    "hybrid",
    name="fleet_topology_type",
    create_type=False,
)
fleet_member_role = postgresql.ENUM(
    "lead",
    "worker",
    "observer",
    name="fleet_member_role",
    create_type=False,
)
fleet_member_availability = postgresql.ENUM(
    "available",
    "unavailable",
    name="fleet_member_availability",
    create_type=False,
)
fleet_transfer_request_status = postgresql.ENUM(
    "proposed",
    "approved",
    "applied",
    "rejected",
    name="fleet_transfer_request_status",
    create_type=False,
)
fleet_communication_style = postgresql.ENUM(
    "verbose",
    "concise",
    "structured",
    name="fleet_communication_style",
    create_type=False,
)
fleet_decision_speed = postgresql.ENUM(
    "fast",
    "deliberate",
    "consensus_seeking",
    name="fleet_decision_speed",
    create_type=False,
)
fleet_risk_tolerance = postgresql.ENUM(
    "conservative",
    "moderate",
    "aggressive",
    name="fleet_risk_tolerance",
    create_type=False,
)
fleet_autonomy_level = postgresql.ENUM(
    "supervised",
    "semi_autonomous",
    "fully_autonomous",
    name="fleet_autonomy_level",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    fleet_status.create(bind, checkfirst=True)
    fleet_topology_type.create(bind, checkfirst=True)
    fleet_member_role.create(bind, checkfirst=True)
    fleet_member_availability.create(bind, checkfirst=True)
    fleet_transfer_request_status.create(bind, checkfirst=True)
    fleet_communication_style.create(bind, checkfirst=True)
    fleet_decision_speed.create(bind, checkfirst=True)
    fleet_risk_tolerance.create(bind, checkfirst=True)
    fleet_autonomy_level.create(bind, checkfirst=True)

    op.create_table(
        "fleets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            fleet_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("topology_type", fleet_topology_type, nullable=False),
        sa.Column("quorum_min", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
    )
    op.create_index("ix_fleets_workspace_id", "fleets", ["workspace_id"], unique=False)
    op.create_index(
        "ix_fleets_workspace_status", "fleets", ["workspace_id", "status"], unique=False
    )
    op.create_index(
        "uq_fleets_workspace_name",
        "fleets",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "fleet_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("role", fleet_member_role, nullable=False, server_default=sa.text("'worker'")),
        sa.Column(
            "availability",
            fleet_member_availability,
            nullable=False,
            server_default=sa.text("'available'"),
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
        sa.ForeignKeyConstraint(
            ["fleet_id"],
            ["fleets.id"],
            name="fk_fleet_members_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_fleet_members_fleet_id", "fleet_members", ["fleet_id"], unique=False)
    op.create_index("ix_fleet_members_agent_fqn", "fleet_members", ["agent_fqn"], unique=False)
    op.create_index(
        "uq_fleet_members_fleet_agent_fqn",
        "fleet_members",
        ["fleet_id", "agent_fqn"],
        unique=True,
    )

    op.create_table(
        "fleet_topology_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topology_type", fleet_topology_type, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            ["fleet_id"],
            ["fleets.id"],
            name="fk_fleet_topology_versions_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fleet_topology_versions_fleet_id",
        "fleet_topology_versions",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "uq_fleet_topology_versions_fleet_version",
        "fleet_topology_versions",
        ["fleet_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_fleet_topology_versions_current",
        "fleet_topology_versions",
        ["fleet_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "fleet_policy_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bound_by", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["fleet_id"],
            ["fleets.id"],
            name="fk_fleet_policy_bindings_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fleet_policy_bindings_fleet_id",
        "fleet_policy_bindings",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "uq_fleet_policy_bindings_fleet_policy",
        "fleet_policy_bindings",
        ["fleet_id", "policy_id"],
        unique=True,
    )

    op.create_table(
        "observer_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observer_fqn", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            ["fleet_id"],
            ["fleets.id"],
            name="fk_observer_assignments_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_observer_assignments_fleet_id", "observer_assignments", ["fleet_id"], unique=False
    )
    op.create_index(
        "uq_observer_assignments_active",
        "observer_assignments",
        ["fleet_id", "observer_fqn"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "fleet_governance_chains",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["fleet_id"],
            ["fleets.id"],
            name="fk_fleet_governance_chains_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fleet_governance_chains_fleet_id", "fleet_governance_chains", ["fleet_id"], unique=False
    )
    op.create_index(
        "uq_fleet_governance_chains_fleet_version",
        "fleet_governance_chains",
        ["fleet_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_fleet_governance_chains_current",
        "fleet_governance_chains",
        ["fleet_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "fleet_orchestration_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "delegation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "aggregation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "escalation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "conflict_resolution",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "retry",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("max_parallelism", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            ["fleet_id"],
            ["fleets.id"],
            name="fk_fleet_orchestration_rules_fleet_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fleet_orchestration_rules_fleet_id",
        "fleet_orchestration_rules",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "uq_fleet_orchestration_rules_fleet_version",
        "fleet_orchestration_rules",
        ["fleet_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_fleet_orchestration_rules_current",
        "fleet_orchestration_rules",
        ["fleet_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "fleet_performance_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "avg_completion_time_ms", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_per_task", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_quality_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("throughput_per_hour", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "member_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "flagged_member_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
    op.create_index(
        "ix_fleet_performance_profiles_fleet_id",
        "fleet_performance_profiles",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_fleet_performance_profiles_fleet_period",
        "fleet_performance_profiles",
        ["fleet_id", "period_start", "period_end"],
        unique=False,
    )

    op.create_table(
        "fleet_adaptation_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "condition",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
    op.create_index(
        "ix_fleet_adaptation_rules_fleet_id", "fleet_adaptation_rules", ["fleet_id"], unique=False
    )
    op.create_index(
        "ix_fleet_adaptation_rules_fleet_priority",
        "fleet_adaptation_rules",
        ["fleet_id", "priority"],
        unique=False,
    )

    op.create_table(
        "fleet_adaptation_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adaptation_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("before_rules_version", sa.Integer(), nullable=False),
        sa.Column("after_rules_version", sa.Integer(), nullable=False),
        sa.Column(
            "performance_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_reverted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
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
            ["adaptation_rule_id"],
            ["fleet_adaptation_rules.id"],
            name="fk_fleet_adaptation_log_adaptation_rule_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fleet_adaptation_log_fleet_id", "fleet_adaptation_log", ["fleet_id"], unique=False
    )
    op.create_index(
        "ix_fleet_adaptation_log_rule_id",
        "fleet_adaptation_log",
        ["adaptation_rule_id"],
        unique=False,
    )

    op.create_table(
        "cross_fleet_transfer_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            fleet_transfer_request_status,
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column(
            "pattern_definition",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("pattern_minio_key", sa.String(length=1024), nullable=True),
        sa.Column("proposed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_cross_fleet_transfer_requests_source_fleet_id",
        "cross_fleet_transfer_requests",
        ["source_fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_cross_fleet_transfer_requests_target_fleet_id",
        "cross_fleet_transfer_requests",
        ["target_fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_cross_fleet_transfer_requests_status",
        "cross_fleet_transfer_requests",
        ["status"],
        unique=False,
    )

    op.create_table(
        "fleet_personality_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("communication_style", fleet_communication_style, nullable=False),
        sa.Column("decision_speed", fleet_decision_speed, nullable=False),
        sa.Column("risk_tolerance", fleet_risk_tolerance, nullable=False),
        sa.Column("autonomy_level", fleet_autonomy_level, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
    op.create_index(
        "ix_fleet_personality_profiles_fleet_id",
        "fleet_personality_profiles",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "uq_fleet_personality_profiles_fleet_version",
        "fleet_personality_profiles",
        ["fleet_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_fleet_personality_profiles_current",
        "fleet_personality_profiles",
        ["fleet_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_fleet_personality_profiles_current", table_name="fleet_personality_profiles")
    op.drop_index(
        "uq_fleet_personality_profiles_fleet_version", table_name="fleet_personality_profiles"
    )
    op.drop_index("ix_fleet_personality_profiles_fleet_id", table_name="fleet_personality_profiles")
    op.drop_table("fleet_personality_profiles")

    op.drop_index(
        "ix_cross_fleet_transfer_requests_status", table_name="cross_fleet_transfer_requests"
    )
    op.drop_index(
        "ix_cross_fleet_transfer_requests_target_fleet_id",
        table_name="cross_fleet_transfer_requests",
    )
    op.drop_index(
        "ix_cross_fleet_transfer_requests_source_fleet_id",
        table_name="cross_fleet_transfer_requests",
    )
    op.drop_table("cross_fleet_transfer_requests")

    op.drop_index("ix_fleet_adaptation_log_rule_id", table_name="fleet_adaptation_log")
    op.drop_index("ix_fleet_adaptation_log_fleet_id", table_name="fleet_adaptation_log")
    op.drop_table("fleet_adaptation_log")

    op.drop_index("ix_fleet_adaptation_rules_fleet_priority", table_name="fleet_adaptation_rules")
    op.drop_index("ix_fleet_adaptation_rules_fleet_id", table_name="fleet_adaptation_rules")
    op.drop_table("fleet_adaptation_rules")

    op.drop_index(
        "ix_fleet_performance_profiles_fleet_period", table_name="fleet_performance_profiles"
    )
    op.drop_index("ix_fleet_performance_profiles_fleet_id", table_name="fleet_performance_profiles")
    op.drop_table("fleet_performance_profiles")

    op.drop_index("uq_fleet_orchestration_rules_current", table_name="fleet_orchestration_rules")
    op.drop_index(
        "uq_fleet_orchestration_rules_fleet_version", table_name="fleet_orchestration_rules"
    )
    op.drop_index("ix_fleet_orchestration_rules_fleet_id", table_name="fleet_orchestration_rules")
    op.drop_table("fleet_orchestration_rules")

    op.drop_index("uq_fleet_governance_chains_current", table_name="fleet_governance_chains")
    op.drop_index("uq_fleet_governance_chains_fleet_version", table_name="fleet_governance_chains")
    op.drop_index("ix_fleet_governance_chains_fleet_id", table_name="fleet_governance_chains")
    op.drop_table("fleet_governance_chains")

    op.drop_index("uq_observer_assignments_active", table_name="observer_assignments")
    op.drop_index("ix_observer_assignments_fleet_id", table_name="observer_assignments")
    op.drop_table("observer_assignments")

    op.drop_index("uq_fleet_policy_bindings_fleet_policy", table_name="fleet_policy_bindings")
    op.drop_index("ix_fleet_policy_bindings_fleet_id", table_name="fleet_policy_bindings")
    op.drop_table("fleet_policy_bindings")

    op.drop_index("uq_fleet_topology_versions_current", table_name="fleet_topology_versions")
    op.drop_index("uq_fleet_topology_versions_fleet_version", table_name="fleet_topology_versions")
    op.drop_index("ix_fleet_topology_versions_fleet_id", table_name="fleet_topology_versions")
    op.drop_table("fleet_topology_versions")

    op.drop_index("uq_fleet_members_fleet_agent_fqn", table_name="fleet_members")
    op.drop_index("ix_fleet_members_agent_fqn", table_name="fleet_members")
    op.drop_index("ix_fleet_members_fleet_id", table_name="fleet_members")
    op.drop_table("fleet_members")

    op.drop_index("uq_fleets_workspace_name", table_name="fleets")
    op.drop_index("ix_fleets_workspace_status", table_name="fleets")
    op.drop_index("ix_fleets_workspace_id", table_name="fleets")
    op.drop_table("fleets")

    fleet_autonomy_level.drop(op.get_bind(), checkfirst=True)
    fleet_risk_tolerance.drop(op.get_bind(), checkfirst=True)
    fleet_decision_speed.drop(op.get_bind(), checkfirst=True)
    fleet_communication_style.drop(op.get_bind(), checkfirst=True)
    fleet_transfer_request_status.drop(op.get_bind(), checkfirst=True)
    fleet_member_availability.drop(op.get_bind(), checkfirst=True)
    fleet_member_role.drop(op.get_bind(), checkfirst=True)
    fleet_topology_type.drop(op.get_bind(), checkfirst=True)
    fleet_status.drop(op.get_bind(), checkfirst=True)
