"""Status page snapshots, subscriptions, and simulation scenarios.

Revision ID: 095_status_page_and_scenarios
Revises: 072_creator_context_contracts
Create Date: 2026-04-28
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "095_status_page_and_scenarios"
down_revision: str | None = "072_creator_context_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
SYSTEM_STATUS_WORKSPACE_ID = UUID("00000000-0000-0000-0000-0000005757a7")
SYSTEM_STATUS_USER_EMAIL = "system_status@musematic.ai"

OVERALL_STATES = ("operational", "degraded", "partial_outage", "full_outage", "maintenance")
SOURCE_KINDS = ("kafka", "poll", "fallback", "manual")
SUBSCRIPTION_CHANNELS = ("email", "rss", "atom", "webhook", "slack")
SUBSCRIPTION_HEALTH = ("pending", "healthy", "unhealthy", "unsubscribed")
DISPATCH_EVENT_KINDS = (
    "incident.created",
    "incident.updated",
    "incident.resolved",
    "maintenance.scheduled",
    "maintenance.started",
    "maintenance.ended",
    "component.degraded",
    "component.recovered",
)
DISPATCH_OUTCOMES = ("sent", "retrying", "dead_lettered", "dropped")


def _uuid_pk() -> sa.Column[UUID]:
    return sa.Column(
        "id",
        PG_UUID,
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def _jsonb(name: str, default: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, JSONB, nullable=nullable, server_default=sa.text(default))


def _check(column: str, values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "platform_status_snapshots",
        _uuid_pk(),
        _ts("generated_at"),
        sa.Column("overall_state", sa.String(length=32), nullable=False),
        _jsonb("payload", "'{}'::jsonb"),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            _check("overall_state", OVERALL_STATES),
            name="CK_platform_status_snapshots_overall_state",
        ),
        sa.CheckConstraint(
            _check("source_kind", SOURCE_KINDS),
            name="CK_platform_status_snapshots_source_kind",
        ),
    )
    op.create_index(
        "IX_platform_status_snapshots_generated_at_desc",
        "platform_status_snapshots",
        [sa.text("generated_at DESC")],
        unique=False,
    )
    op.create_index(
        "IX_platform_status_snapshots_non_operational",
        "platform_status_snapshots",
        ["overall_state"],
        unique=False,
        postgresql_where=sa.text("overall_state != 'operational'"),
    )

    op.create_table(
        "status_subscriptions",
        _uuid_pk(),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column(
            "scope_components",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("confirmation_token_hash", sa.LargeBinary(), nullable=True),
        _ts("confirmed_at", nullable=True),
        sa.Column("health", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "workspace_id",
            PG_UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "webhook_id",
            PG_UUID,
            sa.ForeignKey("outbound_webhooks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            _check("channel", SUBSCRIPTION_CHANNELS),
            name="CK_status_subscriptions_channel",
        ),
        sa.CheckConstraint(
            _check("health", SUBSCRIPTION_HEALTH),
            name="CK_status_subscriptions_health",
        ),
    )
    op.create_index(
        "IX_status_subscriptions_user_id",
        "status_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "IX_status_subscriptions_workspace_id",
        "status_subscriptions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "UQ_status_subscriptions_channel_target_confirmed",
        "status_subscriptions",
        ["channel", "target"],
        unique=True,
        postgresql_where=sa.text("confirmed_at IS NOT NULL"),
    )

    op.create_table(
        "subscription_dispatches",
        _uuid_pk(),
        sa.Column(
            "subscription_id",
            PG_UUID,
            sa.ForeignKey("status_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_kind", sa.String(length=48), nullable=False),
        sa.Column("event_id", PG_UUID, nullable=False),
        _ts("dispatched_at"),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("webhook_signature_kid", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _check("event_kind", DISPATCH_EVENT_KINDS),
            name="CK_subscription_dispatches_event_kind",
        ),
        sa.CheckConstraint(
            _check("outcome", DISPATCH_OUTCOMES),
            name="CK_subscription_dispatches_outcome",
        ),
    )
    op.create_index(
        "IX_subscription_dispatches_subscription_id_dispatched_at",
        "subscription_dispatches",
        ["subscription_id", sa.text("dispatched_at DESC")],
        unique=False,
    )
    op.create_index(
        "IX_subscription_dispatches_event_kind_dispatched_at",
        "subscription_dispatches",
        ["event_kind", sa.text("dispatched_at DESC")],
        unique=False,
    )

    op.create_table(
        "simulation_scenarios",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            PG_UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        _jsonb("agents_config", "'{}'::jsonb"),
        sa.Column(
            "workflow_template_id",
            PG_UUID,
            sa.ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        _jsonb("mock_set_config", "'{}'::jsonb"),
        _jsonb("input_distribution", "'{}'::jsonb"),
        _jsonb("twin_fidelity", "'{}'::jsonb"),
        _jsonb("success_criteria", "'[]'::jsonb"),
        _jsonb("run_schedule", "'{}'::jsonb", nullable=True),
        _ts("archived_at", nullable=True),
        sa.Column(
            "created_by",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index(
        "IX_simulation_scenarios_workspace_id_archived_at",
        "simulation_scenarios",
        ["workspace_id", "archived_at"],
        unique=False,
    )
    op.create_index(
        "UQ_simulation_scenarios_workspace_name_active",
        "simulation_scenarios",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.add_column(
        "simulation_runs",
        sa.Column("scenario_id", PG_UUID, nullable=True),
    )
    op.create_foreign_key(
        "FK_simulation_runs_scenario_id",
        "simulation_runs",
        "simulation_scenarios",
        ["scenario_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "IX_simulation_runs_scenario_id",
        "simulation_runs",
        ["scenario_id"],
        unique=False,
    )

    _seed_system_status_workspace()


def downgrade() -> None:
    op.drop_index("IX_simulation_runs_scenario_id", table_name="simulation_runs")
    op.drop_constraint("FK_simulation_runs_scenario_id", "simulation_runs", type_="foreignkey")
    op.drop_column("simulation_runs", "scenario_id")

    op.drop_index(
        "UQ_simulation_scenarios_workspace_name_active",
        table_name="simulation_scenarios",
    )
    op.drop_index(
        "IX_simulation_scenarios_workspace_id_archived_at",
        table_name="simulation_scenarios",
    )
    op.drop_table("simulation_scenarios")

    op.drop_index(
        "IX_subscription_dispatches_event_kind_dispatched_at",
        table_name="subscription_dispatches",
    )
    op.drop_index(
        "IX_subscription_dispatches_subscription_id_dispatched_at",
        table_name="subscription_dispatches",
    )
    op.drop_table("subscription_dispatches")

    op.drop_index(
        "UQ_status_subscriptions_channel_target_confirmed",
        table_name="status_subscriptions",
    )
    op.drop_index("IX_status_subscriptions_workspace_id", table_name="status_subscriptions")
    op.drop_index("IX_status_subscriptions_user_id", table_name="status_subscriptions")
    op.drop_table("status_subscriptions")

    op.drop_index(
        "IX_platform_status_snapshots_non_operational",
        table_name="platform_status_snapshots",
    )
    op.drop_index(
        "IX_platform_status_snapshots_generated_at_desc",
        table_name="platform_status_snapshots",
    )
    op.drop_table("platform_status_snapshots")

    # The synthetic workspace/user are intentionally retained so a later re-upgrade
    # does not conflict with existing status webhook ownership references.


def _seed_system_status_workspace() -> None:
    op.execute(
        sa.text(
            """
            WITH status_owner_user AS (
                INSERT INTO users (email, display_name, status)
                VALUES (:email, 'System Status', 'active')
                ON CONFLICT (email) DO UPDATE
                    SET display_name = EXCLUDED.display_name
                RETURNING id
            ),
            owner AS (
                SELECT id FROM status_owner_user
                UNION
                SELECT id FROM users WHERE email = :email
                LIMIT 1
            )
            INSERT INTO workspaces (id, name, owner_id, settings, created_at, updated_at)
            SELECT
                :workspace_id,
                'Status',
                owner.id,
                '{"system_slug": "system_status", "system_owned": true}'::jsonb,
                now(),
                now()
            FROM owner
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(
            sa.bindparam("email", SYSTEM_STATUS_USER_EMAIL),
            sa.bindparam("workspace_id", SYSTEM_STATUS_WORKSPACE_ID, type_=PG_UUID),
        )
    )
