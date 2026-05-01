"""Create platform-staff BYPASSRLS role.

Revision ID: 101_platform_staff_role
Revises: 100_tenant_rls_policies
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "101_platform_staff_role"
down_revision: str | None = "100_tenant_rls_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musematic_platform_staff') THEN
                CREATE ROLE musematic_platform_staff LOGIN BYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER ROLE musematic_platform_staff SET search_path = public")
    op.execute("GRANT USAGE ON SCHEMA public TO musematic_platform_staff")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO musematic_platform_staff"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO musematic_platform_staff"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM musematic_platform_staff"
    )
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "FROM musematic_platform_staff"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM musematic_platform_staff")
    op.execute("DROP ROLE IF EXISTS musematic_platform_staff")
