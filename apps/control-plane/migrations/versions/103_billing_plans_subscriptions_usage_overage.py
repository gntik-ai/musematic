"""Billing plans, subscriptions, usage, and overage.

Revision ID: 103_billing_plans_subscriptions_usage_overage
Revises: 102_oauth_provider_tenant_scope
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "103_billing_plans_subscriptions_usage_overage"
down_revision: str | None = "102_oauth_provider_tenant_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        PG_UUID,
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def upgrade() -> None:
    _create_plan_tables()
    _create_plan_version_triggers()
    _create_subscription_tables()
    _create_subscription_scope_trigger()
    _seed_default_plans()
    _backfill_default_workspace_subscriptions()
    _enable_rls("subscriptions")
    _enable_rls("usage_records")
    _enable_rls("overage_authorizations")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS subscriptions_scope_check ON subscriptions")
    op.execute("DROP FUNCTION IF EXISTS subscriptions_scope_check()")
    op.execute("DROP TRIGGER IF EXISTS plan_versions_no_delete_published ON plan_versions")
    op.execute("DROP FUNCTION IF EXISTS plan_versions_no_delete_published()")
    op.execute("DROP TRIGGER IF EXISTS plan_versions_immutable_after_publish ON plan_versions")
    op.execute("DROP FUNCTION IF EXISTS plan_versions_immutable_after_publish()")

    op.drop_index("processed_event_ids_consumer_idx", table_name="processed_event_ids")
    op.drop_table("processed_event_ids")
    op.drop_index(
        "overage_authorizations_subscription_period_idx",
        table_name="overage_authorizations",
    )
    op.drop_table("overage_authorizations")
    op.drop_index("usage_records_subscription_period_idx", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("subscriptions_plan_version_idx", table_name="subscriptions")
    op.drop_index("subscriptions_status_period_end_idx", table_name="subscriptions")
    op.drop_index("subscriptions_tenant_idx", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("plan_versions_plan_published_idx", table_name="plan_versions")
    op.drop_table("plan_versions")
    op.drop_index("plans_tier_active_idx", table_name="plans")
    op.drop_table("plans")


def _create_plan_tables() -> None:
    op.create_table(
        "plans",
        _uuid_pk(),
        sa.Column("slug", sa.String(length=32), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "allowed_model_tier",
            sa.String(length=32),
            nullable=False,
            server_default="all",
        ),
        _ts("created_at"),
        sa.CheckConstraint("tier IN ('free','pro','enterprise')", name="ck_plans_tier"),
        sa.CheckConstraint(
            "allowed_model_tier IN ('cheap_only','standard','all')",
            name="ck_plans_allowed_model_tier",
        ),
    )
    op.create_index("plans_tier_active_idx", "plans", ["tier", "is_active"])

    op.create_table(
        "plan_versions",
        _uuid_pk(),
        sa.Column(
            "plan_id",
            PG_UUID,
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "price_monthly",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("executions_per_day", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executions_per_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutes_per_day", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutes_per_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_workspaces", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_agents_per_workspace", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_users_per_workspace", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "overage_price_per_minute",
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "quota_period_anchor",
            sa.String(length=32),
            nullable=False,
            server_default="calendar_month",
        ),
        sa.Column("extras_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _ts("published_at", nullable=True),
        _ts("deprecated_at", nullable=True),
        _ts("created_at"),
        sa.Column(
            "created_by",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("plan_id", "version", name="plan_versions_plan_version_key"),
        sa.CheckConstraint("price_monthly >= 0", name="ck_plan_versions_price_nonnegative"),
        sa.CheckConstraint(
            "executions_per_day >= 0 AND executions_per_month >= 0 "
            "AND minutes_per_day >= 0 AND minutes_per_month >= 0 "
            "AND max_workspaces >= 0 AND max_agents_per_workspace >= 0 "
            "AND max_users_per_workspace >= 0 AND trial_days >= 0",
            name="ck_plan_versions_quotas_nonnegative",
        ),
        sa.CheckConstraint(
            "overage_price_per_minute >= 0",
            name="ck_plan_versions_overage_price_nonnegative",
        ),
        sa.CheckConstraint(
            "quota_period_anchor IN ('calendar_month','subscription_anniversary')",
            name="ck_plan_versions_quota_period_anchor",
        ),
    )
    op.create_index(
        "plan_versions_plan_published_idx",
        "plan_versions",
        ["plan_id", "published_at"],
        postgresql_where=sa.text("deprecated_at IS NULL"),
    )


def _create_plan_version_triggers() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION plan_versions_immutable_after_publish()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL AND (
                NEW.plan_id IS DISTINCT FROM OLD.plan_id OR
                NEW.version IS DISTINCT FROM OLD.version OR
                NEW.price_monthly IS DISTINCT FROM OLD.price_monthly OR
                NEW.executions_per_day IS DISTINCT FROM OLD.executions_per_day OR
                NEW.executions_per_month IS DISTINCT FROM OLD.executions_per_month OR
                NEW.minutes_per_day IS DISTINCT FROM OLD.minutes_per_day OR
                NEW.minutes_per_month IS DISTINCT FROM OLD.minutes_per_month OR
                NEW.max_workspaces IS DISTINCT FROM OLD.max_workspaces OR
                NEW.max_agents_per_workspace IS DISTINCT FROM OLD.max_agents_per_workspace OR
                NEW.max_users_per_workspace IS DISTINCT FROM OLD.max_users_per_workspace OR
                NEW.overage_price_per_minute IS DISTINCT FROM OLD.overage_price_per_minute OR
                NEW.trial_days IS DISTINCT FROM OLD.trial_days OR
                NEW.quota_period_anchor IS DISTINCT FROM OLD.quota_period_anchor OR
                NEW.published_at IS DISTINCT FROM OLD.published_at OR
                NEW.created_at IS DISTINCT FROM OLD.created_at OR
                NEW.created_by IS DISTINCT FROM OLD.created_by
            ) THEN
                RAISE EXCEPTION 'published plan versions are immutable'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER plan_versions_immutable_after_publish
        BEFORE UPDATE ON plan_versions
        FOR EACH ROW EXECUTE FUNCTION plan_versions_immutable_after_publish();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION plan_versions_no_delete_published()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'published plan versions cannot be deleted'
                    USING ERRCODE = '23514';
            END IF;

            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER plan_versions_no_delete_published
        BEFORE DELETE ON plan_versions
        FOR EACH ROW EXECUTE FUNCTION plan_versions_no_delete_published();
        """
    )


def _create_subscription_tables() -> None:
    op.create_table(
        "subscriptions",
        _uuid_pk(),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", PG_UUID, nullable=False),
        sa.Column("plan_id", PG_UUID, nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        _ts("started_at"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("payment_method_id", PG_UUID, nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("scope_type", "scope_id", name="subscriptions_scope_unique"),
        sa.ForeignKeyConstraint(
            ["plan_id", "plan_version"],
            ["plan_versions.plan_id", "plan_versions.version"],
            name="subscriptions_plan_version_fk",
        ),
        sa.CheckConstraint("scope_type IN ('workspace','tenant')", name="ck_subscriptions_scope"),
        sa.CheckConstraint(
            "status IN ('trial','active','past_due','cancellation_pending','canceled','suspended')",
            name="ck_subscriptions_status",
        ),
    )
    op.create_index("subscriptions_tenant_idx", "subscriptions", ["tenant_id"])
    op.create_index(
        "subscriptions_status_period_end_idx",
        "subscriptions",
        ["status", "current_period_end"],
    )
    op.create_index(
        "subscriptions_plan_version_idx",
        "subscriptions",
        ["plan_id", "plan_version"],
    )

    op.create_table(
        "usage_records",
        _uuid_pk(),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "workspace_id",
            PG_UUID,
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            PG_UUID,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "quantity",
            sa.Numeric(precision=20, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("is_overage", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "subscription_id",
            "metric",
            "period_start",
            "is_overage",
            name="usage_records_unique_aggregate",
        ),
        sa.CheckConstraint("metric IN ('executions','minutes')", name="ck_usage_records_metric"),
    )
    op.create_index(
        "usage_records_subscription_period_idx",
        "usage_records",
        ["subscription_id", "period_start", "metric"],
    )

    op.create_table(
        "overage_authorizations",
        _uuid_pk(),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "workspace_id",
            PG_UUID,
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            PG_UUID,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=False),
        _ts("authorized_at"),
        sa.Column(
            "authorized_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        sa.Column("max_overage_eur", sa.Numeric(precision=10, scale=2), nullable=True),
        _ts("revoked_at", nullable=True),
        sa.Column(
            "revoked_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "billing_period_start",
            name="overage_authorizations_workspace_period_unique",
        ),
    )
    op.create_index(
        "overage_authorizations_subscription_period_idx",
        "overage_authorizations",
        ["subscription_id", "billing_period_start"],
    )

    op.create_table(
        "processed_event_ids",
        sa.Column("event_id", PG_UUID, primary_key=True, nullable=False),
        sa.Column("consumer_name", sa.String(length=64), nullable=False),
        _ts("processed_at"),
    )
    op.create_index(
        "processed_event_ids_consumer_idx",
        "processed_event_ids",
        ["consumer_name", "processed_at"],
    )


def _create_subscription_scope_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION subscriptions_scope_check()
        RETURNS trigger AS $$
        DECLARE
            tenant_kind text;
            workspace_tenant_id uuid;
        BEGIN
            SELECT kind INTO tenant_kind FROM tenants WHERE id = NEW.tenant_id;
            IF tenant_kind IS NULL THEN
                RAISE EXCEPTION 'subscription tenant does not exist'
                    USING ERRCODE = '23503';
            END IF;

            IF NEW.scope_type = 'tenant' THEN
                IF NEW.scope_id IS DISTINCT FROM NEW.tenant_id THEN
                    RAISE EXCEPTION 'tenant-scoped subscription scope_id must equal tenant_id'
                        USING ERRCODE = '23514';
                END IF;
                IF tenant_kind = 'default' THEN
                    RAISE EXCEPTION 'default tenants cannot have tenant-scoped subscriptions'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.scope_type = 'workspace' THEN
                SELECT tenant_id INTO workspace_tenant_id
                  FROM workspaces_workspaces
                 WHERE id = NEW.scope_id;
                IF workspace_tenant_id IS NULL THEN
                    RAISE EXCEPTION 'workspace-scoped subscription workspace does not exist'
                        USING ERRCODE = '23503';
                END IF;
                IF workspace_tenant_id IS DISTINCT FROM NEW.tenant_id THEN
                    RAISE EXCEPTION 'workspace subscription tenant mismatch'
                        USING ERRCODE = '23514';
                END IF;
                IF tenant_kind = 'enterprise' THEN
                    RAISE EXCEPTION 'enterprise tenants cannot have workspace-scoped subscriptions'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'invalid subscription scope type' USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER subscriptions_scope_check
        BEFORE INSERT OR UPDATE OF tenant_id, scope_type, scope_id ON subscriptions
        FOR EACH ROW EXECUTE FUNCTION subscriptions_scope_check();
        """
    )


def _enable_rls(table_name: str) -> None:
    quoted = '"' + table_name.replace('"', '""') + '"'
    op.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {quoted} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {quoted}")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {quoted}
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def _seed_default_plans() -> None:
    op.execute(
        """
        WITH plan_seed(slug, display_name, description, tier, is_public, allowed_model_tier) AS (
            VALUES
              (
                'free',
                'Free',
                'Free plan with hard cost-protection quotas.',
                'free',
                true,
                'cheap_only'
              ),
              ('pro', 'Pro', 'Professional plan with opt-in overage.', 'pro', true, 'all'),
              (
                'enterprise',
                'Enterprise',
                'Enterprise plan with tenant-scoped unlimited usage.',
                'enterprise',
                false,
                'all'
              )
        ),
        inserted_plans AS (
            INSERT INTO plans (
                slug,
                display_name,
                description,
                tier,
                is_public,
                is_active,
                allowed_model_tier
            )
            SELECT slug, display_name, description, tier, is_public, true, allowed_model_tier
              FROM plan_seed
            ON CONFLICT (slug) DO NOTHING
            RETURNING id, slug
        ),
        all_plans AS (
            SELECT id, slug FROM inserted_plans
            UNION ALL
            SELECT p.id, p.slug
              FROM plans p
              JOIN plan_seed s ON s.slug = p.slug
        ),
        version_seed(
            slug,
            price_monthly,
            executions_per_day,
            executions_per_month,
            minutes_per_day,
            minutes_per_month,
            max_workspaces,
            max_agents_per_workspace,
            max_users_per_workspace,
            overage_price_per_minute,
            trial_days,
            quota_period_anchor
        ) AS (
            VALUES
              ('free', 0.00, 50, 100, 30, 100, 1, 5, 3, 0.0000, 0, 'calendar_month'),
              (
                'pro',
                49.00,
                500,
                5000,
                240,
                2400,
                5,
                50,
                25,
                0.1000,
                14,
                'subscription_anniversary'
              ),
              (
                'enterprise',
                0.00,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0.0000,
                0,
                'subscription_anniversary'
              )
        )
        INSERT INTO plan_versions (
            plan_id,
            version,
            price_monthly,
            executions_per_day,
            executions_per_month,
            minutes_per_day,
            minutes_per_month,
            max_workspaces,
            max_agents_per_workspace,
            max_users_per_workspace,
            overage_price_per_minute,
            trial_days,
            quota_period_anchor,
            published_at
        )
        SELECT DISTINCT ON (p.id)
            p.id,
            1,
            v.price_monthly,
            v.executions_per_day,
            v.executions_per_month,
            v.minutes_per_day,
            v.minutes_per_month,
            v.max_workspaces,
            v.max_agents_per_workspace,
            v.max_users_per_workspace,
            v.overage_price_per_minute,
            v.trial_days,
            v.quota_period_anchor,
            now()
          FROM all_plans p
          JOIN version_seed v ON v.slug = p.slug
        ON CONFLICT (plan_id, version) DO NOTHING
        """
    )


def _backfill_default_workspace_subscriptions() -> None:
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            WITH free_plan AS (
                SELECT p.id AS plan_id
                  FROM plans p
                 WHERE p.slug = 'free'
            ),
            inserted AS (
                INSERT INTO subscriptions (
                    tenant_id,
                    scope_type,
                    scope_id,
                    plan_id,
                    plan_version,
                    status,
                    current_period_start,
                    current_period_end
                )
                SELECT
                    w.tenant_id,
                    'workspace',
                    w.id,
                    fp.plan_id,
                    1,
                    'active',
                    date_trunc('month', now()),
                    date_trunc('month', now()) + interval '1 month'
                  FROM workspaces_workspaces w
                  JOIN tenants t ON t.id = w.tenant_id AND t.kind = 'default'
                  CROSS JOIN free_plan fp
                ON CONFLICT (scope_type, scope_id) DO NOTHING
                RETURNING tenant_id
            )
            SELECT count(*) AS inserted_count FROM inserted
            """
        )
    )
    inserted_count = int(result.scalar() or 0)
    op.execute(
        f"""
        DO $$
        BEGIN
            RAISE NOTICE
                '{{"event":"billing.default_workspace_subscription_backfill","inserted_count":{inserted_count}}}';
        END;
        $$;
        """
    )
