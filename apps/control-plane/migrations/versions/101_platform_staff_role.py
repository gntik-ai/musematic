"""Create platform-staff BYPASSRLS role.

Revision ID: 101_platform_staff_role
Revises: 100_tenant_rls_policies
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "101_platform_staff_role"
down_revision: str | None = "100_tenant_rls_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_NAME = "musematic_platform_staff"


def upgrade() -> None:
    connection = op.get_bind()
    if _can_manage_bypassrls(connection):
        _create_or_update_role()
    else:
        _assert_preprovisioned_role(connection)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE_NAME}")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {ROLE_NAME}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE_NAME}"
    )


def downgrade() -> None:
    connection = op.get_bind()
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE_NAME}"
    )
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"FROM {ROLE_NAME}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE_NAME}")
    if _can_manage_bypassrls(connection):
        op.execute(f"DROP ROLE IF EXISTS {ROLE_NAME}")


def _create_or_update_role() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE_NAME}') THEN
                CREATE ROLE {ROLE_NAME} LOGIN BYPASSRLS;
            ELSE
                ALTER ROLE {ROLE_NAME} LOGIN BYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"ALTER ROLE {ROLE_NAME} SET search_path = public")


def _can_manage_bypassrls(connection: sa.Connection) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    )


def _assert_preprovisioned_role(connection: sa.Connection) -> None:
    role = connection.execute(
        sa.text(
            """
            SELECT rolcanlogin, rolbypassrls
            FROM pg_roles
            WHERE rolname = :role_name
            """
        ),
        {"role_name": ROLE_NAME},
    ).one_or_none()
    if role is None:
        raise RuntimeError(
            f"{ROLE_NAME} must be pre-provisioned with LOGIN BYPASSRLS, "
            "or this migration must run as a PostgreSQL superuser."
        )
    if not role.rolcanlogin or not role.rolbypassrls:
        raise RuntimeError(f"{ROLE_NAME} must have LOGIN and BYPASSRLS attributes.")
