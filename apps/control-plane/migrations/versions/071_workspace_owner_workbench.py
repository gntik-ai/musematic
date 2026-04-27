"""Add workspace owner workbench settings.

Revision ID: 071_workspace_owner_workbench
Revises: 070_user_self_service_extensions
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "071_workspace_owner_workbench"
down_revision: str | None = "070_user_self_service_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb_settings_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def upgrade() -> None:
    op.add_column("workspaces_settings", _jsonb_settings_column("quota_config"))
    op.add_column("workspaces_settings", _jsonb_settings_column("dlp_rules"))
    op.add_column("workspaces_settings", _jsonb_settings_column("residency_config"))


def downgrade() -> None:
    op.drop_column("workspaces_settings", "residency_config")
    op.drop_column("workspaces_settings", "dlp_rules")
    op.drop_column("workspaces_settings", "quota_config")
