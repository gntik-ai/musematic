"""Tags, labels, and saved views.

Revision ID: 065_tags_labels_saved_views
Revises: 064_multi_region_ops
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "065_tags_labels_saved_views"
down_revision: str | None = "064_multi_region_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_TYPES = (
    "workspace",
    "agent",
    "fleet",
    "workflow",
    "policy",
    "certification",
    "evaluation_run",
)


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


def _entity_type_check(column: str = "entity_type") -> str:
    values = ",".join(f"'{value}'" for value in ENTITY_TYPES)
    return f"{column} IN ({values})"


def upgrade() -> None:
    op.create_table(
        "entity_tags",
        _uuid_pk(),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        sa.CheckConstraint(_entity_type_check(), name="ck_entity_tags_entity_type"),
        sa.CheckConstraint("tag ~ '^[a-zA-Z0-9._-]+$'", name="ck_entity_tags_tag_pattern"),
        sa.UniqueConstraint("entity_type", "entity_id", "tag", name="uq_entity_tags_type_id_tag"),
    )
    op.create_index("idx_entity_tags_type_id", "entity_tags", ["entity_type", "entity_id"])
    op.create_index("idx_entity_tags_tag", "entity_tags", ["tag"])

    op.create_table(
        "entity_labels",
        _uuid_pk(),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_key", sa.String(length=128), nullable=False),
        sa.Column("label_value", sa.String(length=512), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(_entity_type_check(), name="ck_entity_labels_entity_type"),
        sa.CheckConstraint(
            "label_key ~ '^[a-zA-Z][a-zA-Z0-9._-]*$'",
            name="ck_entity_labels_key_pattern",
        ),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "label_key",
            name="uq_entity_labels_type_id_key",
        ),
    )
    op.create_index("idx_entity_labels_type_id", "entity_labels", ["entity_type", "entity_id"])
    op.create_index("idx_entity_labels_kv", "entity_labels", ["label_key", "label_value"])
    op.create_index("idx_entity_labels_key", "entity_labels", ["label_key"])

    op.create_table(
        "saved_views",
        _uuid_pk(),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_orphan_transferred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_orphan",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(_entity_type_check(), name="ck_saved_views_entity_type"),
        sa.UniqueConstraint(
            "owner_id",
            "workspace_id",
            "name",
            name="uq_saved_views_owner_ws_name",
        ),
    )
    op.create_index("idx_saved_views_owner_entity", "saved_views", ["owner_id", "entity_type"])
    op.create_index(
        "idx_saved_views_shared_workspace_entity",
        "saved_views",
        ["workspace_id", "entity_type"],
        postgresql_where=sa.text("shared = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_saved_views_shared_workspace_entity", table_name="saved_views")
    op.drop_index("idx_saved_views_owner_entity", table_name="saved_views")
    op.drop_table("saved_views")
    op.drop_index("idx_entity_labels_key", table_name="entity_labels")
    op.drop_index("idx_entity_labels_kv", table_name="entity_labels")
    op.drop_index("idx_entity_labels_type_id", table_name="entity_labels")
    op.drop_table("entity_labels")
    op.drop_index("idx_entity_tags_tag", table_name="entity_tags")
    op.drop_index("idx_entity_tags_type_id", table_name="entity_tags")
    op.drop_table("entity_tags")
