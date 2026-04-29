from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

_ENTITY_TYPE_CHECK = (
    "entity_type IN ('workspace','agent','fleet','workflow','policy','certification',"
    "'evaluation_run')"
)


class EntityTag(Base, UUIDMixin):
    __tablename__ = "entity_tags"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "tag", name="uq_entity_tags_type_id_tag"),
        CheckConstraint(_ENTITY_TYPE_CHECK, name="ck_entity_tags_entity_type"),
        CheckConstraint("tag ~ '^[a-zA-Z0-9._-]+$'", name="ck_entity_tags_tag_pattern"),
        Index("idx_entity_tags_type_id", "entity_type", "entity_id"),
        Index("idx_entity_tags_tag", "tag"),
    )

    entity_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tag: Mapped[str] = mapped_column(String(length=128), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class EntityLabel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entity_labels"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "label_key",
            name="uq_entity_labels_type_id_key",
        ),
        CheckConstraint(_ENTITY_TYPE_CHECK, name="ck_entity_labels_entity_type"),
        CheckConstraint(
            "label_key ~ '^[a-zA-Z][a-zA-Z0-9._-]*$'",
            name="ck_entity_labels_key_pattern",
        ),
        Index("idx_entity_labels_type_id", "entity_type", "entity_id"),
        Index("idx_entity_labels_kv", "label_key", "label_value"),
        Index("idx_entity_labels_key", "label_key"),
    )

    entity_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    label_key: Mapped[str] = mapped_column(String(length=128), nullable=False)
    label_value: Mapped[str] = mapped_column(String(length=512), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class SavedView(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "saved_views"
    __table_args__ = (
        UniqueConstraint("owner_id", "workspace_id", "name", name="uq_saved_views_owner_ws_name"),
        CheckConstraint(_ENTITY_TYPE_CHECK, name="ck_saved_views_entity_type"),
        Index("idx_saved_views_owner_entity", "owner_id", "entity_type"),
        Index(
            "idx_saved_views_shared_workspace_entity",
            "workspace_id",
            "entity_type",
            postgresql_where=text("shared = true"),
        ),
    )

    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    shared: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_orphan_transferred: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_orphan: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    owner: Mapped[Any] = relationship("platform.common.models.user.User")
    workspace: Mapped[Any | None] = relationship("platform.workspaces.models.Workspace")
