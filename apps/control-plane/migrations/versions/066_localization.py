"""Localization preferences and locale files.

Revision ID: 066_localization
Revises: 065_tags_labels_saved_views
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "066_localization"
down_revision: str | None = "065_tags_labels_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

THEMES = ("light", "dark", "system", "high_contrast")
LOCALES = ("en", "es", "fr", "de", "ja", "zh-CN")
DATA_EXPORT_FORMATS = ("json", "csv", "ndjson")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def _check_values(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        _uuid_pk(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "default_workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("theme", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column(
            "notification_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "data_export_format",
            sa.String(length=32),
            nullable=False,
            server_default="json",
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
        sa.CheckConstraint(_check_values("theme", THEMES), name="ck_user_preferences_theme"),
        sa.CheckConstraint(
            _check_values("language", LOCALES),
            name="ck_user_preferences_language",
        ),
        sa.CheckConstraint(
            _check_values("data_export_format", DATA_EXPORT_FORMATS),
            name="ck_user_preferences_data_export_format",
        ),
    )
    op.create_index(
        "ix_user_preferences_default_workspace",
        "user_preferences",
        ["default_workspace_id"],
    )

    op.create_table(
        "locale_files",
        _uuid_pk(),
        sa.Column("locale_code", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        _ts("published_at", nullable=True),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("vendor_source_ref", sa.String(length=256), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint(
            "locale_code",
            "version",
            name="uq_locale_files_locale_version",
        ),
        sa.CheckConstraint(
            _check_values("locale_code", LOCALES),
            name="ck_locale_files_locale_code",
        ),
    )
    op.create_index(
        "ix_locale_files_locale_version_desc",
        "locale_files",
        ["locale_code", sa.text("version DESC")],
    )
    op.create_index("ix_locale_files_published_at", "locale_files", ["published_at"])

    op.execute(
        sa.text(
            """
            INSERT INTO locale_files (
                id,
                locale_code,
                version,
                translations,
                published_at,
                created_at
            )
            VALUES (
                gen_random_uuid(),
                'en',
                1,
                '{}'::jsonb,
                now(),
                now()
            )
            ON CONFLICT (locale_code, version) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_locale_files_published_at", table_name="locale_files")
    op.drop_index("ix_locale_files_locale_version_desc", table_name="locale_files")
    op.drop_table("locale_files")
    op.drop_index("ix_user_preferences_default_workspace", table_name="user_preferences")
    op.drop_table("user_preferences")

