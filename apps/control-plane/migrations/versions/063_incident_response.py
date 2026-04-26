"""Incident response and runbooks.

Revision ID: 063_incident_response
Revises: 062_cost_governance
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence
from platform.incident_response.seeds.runbooks_v1 import RUNBOOK_SCENARIOS, seed_initial_runbooks

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "063_incident_response"
down_revision: str | None = "062_cost_governance"
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
        "incident_integrations",
        _uuid_pk(),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("integration_key_ref", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _jsonb("alert_severity_mapping", "'{}'::jsonb"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint(
            "provider",
            "integration_key_ref",
            name="uq_incident_integrations_provider_key_ref",
        ),
        sa.CheckConstraint(
            "provider IN ('pagerduty','opsgenie','victorops')",
            name="ck_incident_integrations_provider",
        ),
    )

    op.create_table(
        "incidents",
        _uuid_pk(),
        sa.Column("condition_fingerprint", sa.String(length=512), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        _ts("triggered_at"),
        _ts("resolved_at", nullable=True),
        sa.Column(
            "related_executions",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column(
            "related_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column("runbook_scenario", sa.String(length=256), nullable=True),
        sa.Column("alert_rule_class", sa.String(length=128), nullable=False),
        sa.Column("post_mortem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('critical','high','warning','info')",
            name="ck_incidents_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved','auto_resolved')",
            name="ck_incidents_status",
        ),
    )
    op.create_index(
        "ix_incidents_condition_fingerprint",
        "incidents",
        ["condition_fingerprint"],
    )
    op.create_index(
        "ix_incidents_open_fingerprint",
        "incidents",
        ["condition_fingerprint"],
        postgresql_where=sa.text("status IN ('open','acknowledged')"),
    )
    op.create_index(
        "ix_incidents_triggered_at_desc",
        "incidents",
        [sa.text("triggered_at DESC")],
    )
    op.create_index(
        "ix_incidents_related_executions_gin",
        "incidents",
        ["related_executions"],
        postgresql_using="gin",
    )

    op.create_table(
        "incident_external_alerts",
        _uuid_pk(),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incident_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_reference", sa.String(length=512), nullable=True),
        sa.Column(
            "delivery_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        _ts("last_attempt_at", nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("next_retry_at", nullable=True),
        sa.UniqueConstraint(
            "incident_id",
            "integration_id",
            name="uq_incident_external_alert_incident_integration",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('pending','delivered','failed','resolved')",
            name="ck_incident_external_alerts_status",
        ),
    )
    op.create_index(
        "ix_incident_external_alerts_next_retry_pending",
        "incident_external_alerts",
        ["next_retry_at"],
        postgresql_where=sa.text("delivery_status = 'pending'"),
    )

    op.create_table(
        "runbooks",
        _uuid_pk(),
        sa.Column("scenario", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        _jsonb("diagnostic_commands", "'[]'::jsonb"),
        sa.Column("remediation_steps", sa.Text(), nullable=False),
        sa.Column("escalation_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("scenario", name="uq_runbooks_scenario"),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_runbooks_status"),
        sa.CheckConstraint("length(symptoms) > 0", name="ck_runbooks_symptoms_nonempty"),
        sa.CheckConstraint(
            "length(remediation_steps) > 0",
            name="ck_runbooks_remediation_nonempty",
        ),
        sa.CheckConstraint(
            "length(escalation_path) > 0",
            name="ck_runbooks_escalation_nonempty",
        ),
    )

    op.create_table(
        "post_mortems",
        _uuid_pk(),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timeline_blob_ref", sa.String(length=1024), nullable=True),
        _jsonb("timeline_source_coverage", "'{}'::jsonb"),
        sa.Column("impact_assessment", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("action_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("distribution_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "linked_certification_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column("blameless", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("published_at", nullable=True),
        _ts("distributed_at", nullable=True),
        sa.UniqueConstraint("incident_id", name="uq_post_mortems_incident_id"),
        sa.CheckConstraint(
            "status IN ('draft','published','distributed')",
            name="ck_post_mortems_status",
        ),
    )
    op.create_index(
        "ix_post_mortems_linked_certifications_gin",
        "post_mortems",
        ["linked_certification_ids"],
        postgresql_using="gin",
    )
    op.create_foreign_key(
        "fk_incidents_post_mortem_id",
        "incidents",
        "post_mortems",
        ["post_mortem_id"],
        ["id"],
        ondelete="SET NULL",
    )

    seed_initial_runbooks(op.get_bind())


def downgrade() -> None:
    connection = op.get_bind()
    runbooks = sa.table("runbooks", sa.column("scenario"))
    connection.execute(runbooks.delete().where(runbooks.c.scenario.in_(RUNBOOK_SCENARIOS)))
    op.drop_constraint("fk_incidents_post_mortem_id", "incidents", type_="foreignkey")
    op.drop_index("ix_post_mortems_linked_certifications_gin", table_name="post_mortems")
    op.drop_table("post_mortems")
    op.drop_table("runbooks")
    op.drop_index(
        "ix_incident_external_alerts_next_retry_pending",
        table_name="incident_external_alerts",
    )
    op.drop_table("incident_external_alerts")
    op.drop_index("ix_incidents_related_executions_gin", table_name="incidents")
    op.drop_index("ix_incidents_triggered_at_desc", table_name="incidents")
    op.drop_index("ix_incidents_open_fingerprint", table_name="incidents")
    op.drop_index("ix_incidents_condition_fingerprint", table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("incident_integrations")
