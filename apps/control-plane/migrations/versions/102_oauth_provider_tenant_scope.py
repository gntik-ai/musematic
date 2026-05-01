"""Scope OAuth providers by tenant.

Revision ID: 102_oauth_provider_tenant_scope
Revises: 101_platform_staff_role
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "102_oauth_provider_tenant_scope"
down_revision: str | None = "101_platform_staff_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE oauth_providers
               SET tenant_id = :default_tenant_id
             WHERE tenant_id IS NULL
            """
        ),
        {"default_tenant_id": DEFAULT_TENANT_ID},
    )
    op.execute("DROP INDEX IF EXISTS ix_oauth_providers_provider_type")
    op.execute("DROP INDEX IF EXISTS idx_oauth_providers_enabled")
    op.execute("ALTER TABLE oauth_providers DROP CONSTRAINT IF EXISTS uq_oauth_providers_type")
    op.create_unique_constraint(
        "uq_oauth_providers_tenant_type",
        "oauth_providers",
        ["tenant_id", "provider_type"],
    )
    op.create_index(
        "idx_oauth_providers_enabled",
        "oauth_providers",
        ["tenant_id", "enabled", "provider_type"],
        unique=False,
    )
    op.execute(
        "ALTER TYPE two_person_approval_action_type "
        "ADD VALUE IF NOT EXISTS 'tenant_schedule_deletion'"
    )
    op.execute(
        "ALTER TYPE two_person_approval_action_type "
        "ADD VALUE IF NOT EXISTS 'tenant_force_cascade_deletion'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_oauth_providers_enabled")
    op.drop_constraint(
        "uq_oauth_providers_tenant_type",
        "oauth_providers",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_oauth_providers_type",
        "oauth_providers",
        ["provider_type"],
    )
    op.create_index(
        "idx_oauth_providers_enabled",
        "oauth_providers",
        ["enabled", "provider_type"],
        unique=False,
    )
