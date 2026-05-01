"""Tenant table and default tenant seed.

Revision ID: 096_tenant_table_and_seed
Revises: 095_status_page_and_scenarios
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "096_tenant_table_and_seed"
down_revision: str | None = "095_status_page_and_scenarios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "docs",
        "grafana",
        "help",
        "platform",
        "public",
        "status",
        "webhooks",
        "www",
    }
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(length=32), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subdomain", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column(
            "data_isolation_mode",
            sa.String(length=8),
            nullable=False,
            server_default="pool",
        ),
        sa.Column(
            "branding_config_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("subscription_id", PG_UUID, nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("scheduled_deletion_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "created_by_super_admin_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dpa_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dpa_version", sa.String(length=32), nullable=True),
        sa.Column("dpa_artifact_uri", sa.String(length=512), nullable=True),
        sa.Column("dpa_artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "contract_metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "feature_flags_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z][a-z0-9-]{0,30}[a-z0-9]$'",
            name="ck_tenants_slug_format",
        ),
        sa.CheckConstraint("kind IN ('default','enterprise')", name="ck_tenants_kind"),
        sa.CheckConstraint(
            "data_isolation_mode IN ('pool','silo')",
            name="ck_tenants_data_isolation_mode",
        ),
        sa.CheckConstraint(
            "status IN ('active','suspended','pending_deletion')",
            name="ck_tenants_status",
        ),
    )
    op.create_index(
        "tenants_one_default",
        "tenants",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'default'"),
    )
    op.create_index("tenants_kind_status_idx", "tenants", ["kind", "status"])
    op.create_index(
        "tenants_scheduled_deletion_at_idx",
        "tenants",
        ["scheduled_deletion_at"],
        postgresql_where=sa.text("status = 'pending_deletion'"),
    )
    _create_triggers()
    _seed_default_tenant()
    _create_tenant_enforcement_violations_table()


def downgrade() -> None:
    op.drop_table("tenant_enforcement_violations")
    op.execute("DROP TRIGGER IF EXISTS tenants_default_immutable ON tenants")
    op.execute("DROP FUNCTION IF EXISTS tenants_default_immutable()")
    op.execute("DROP TRIGGER IF EXISTS tenants_reserved_slug_check ON tenants")
    op.execute("DROP FUNCTION IF EXISTS tenants_reserved_slug_check()")
    op.drop_index("tenants_scheduled_deletion_at_idx", table_name="tenants")
    op.drop_index("tenants_kind_status_idx", table_name="tenants")
    op.drop_index("tenants_one_default", table_name="tenants")
    op.drop_table("tenants")


def _create_triggers() -> None:
    reserved_array = ", ".join(f"'{slug}'" for slug in sorted(RESERVED_SLUGS))
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION tenants_reserved_slug_check()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.kind != 'default' AND NEW.slug = ANY (ARRAY[{reserved_array}]) THEN
                RAISE EXCEPTION 'tenant slug "%" is reserved', NEW.slug
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_reserved_slug_check
        BEFORE INSERT OR UPDATE OF slug, kind ON tenants
        FOR EACH ROW EXECUTE FUNCTION tenants_reserved_slug_check();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenants_default_immutable()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND OLD.kind = 'default' THEN
                RAISE EXCEPTION 'default tenant cannot be deleted'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'UPDATE' AND OLD.kind = 'default' AND (
                NEW.slug IS DISTINCT FROM OLD.slug OR
                NEW.subdomain IS DISTINCT FROM OLD.subdomain OR
                NEW.kind IS DISTINCT FROM OLD.kind OR
                NEW.status IS DISTINCT FROM OLD.status
            ) THEN
                RAISE EXCEPTION 'default tenant identity cannot be changed'
                    USING ERRCODE = '23514';
            END IF;

            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_default_immutable
        BEFORE UPDATE OR DELETE ON tenants
        FOR EACH ROW EXECUTE FUNCTION tenants_default_immutable();
        """
    )


def _seed_default_tenant() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO tenants (
                id,
                slug,
                kind,
                subdomain,
                display_name,
                region,
                data_isolation_mode,
                branding_config_json,
                status,
                contract_metadata_json,
                feature_flags_json
            )
            VALUES (
                CAST(:id AS UUID),
                'default',
                'default',
                'app',
                'Musematic',
                'global',
                'pool',
                '{}'::jsonb,
                'active',
                '{}'::jsonb,
                '{}'::jsonb
            )
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(id=DEFAULT_TENANT_ID)
    )


def _create_tenant_enforcement_violations_table() -> None:
    op.create_table(
        "tenant_enforcement_violations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("expected_tenant_id", PG_UUID, nullable=True),
        sa.Column("observed_violation", sa.Text(), nullable=False),
    )
