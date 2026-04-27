from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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

from .constants import DATA_EXPORT_FORMATS, DEFAULT_LOCALE, DEFAULT_THEME, LOCALES, THEMES


def _check_values(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(value) for value in values)})"


class UserPreferences(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
        CheckConstraint(_check_values("theme", THEMES), name="ck_user_preferences_theme"),
        CheckConstraint(_check_values("language", LOCALES), name="ck_user_preferences_language"),
        CheckConstraint(
            _check_values("data_export_format", DATA_EXPORT_FORMATS),
            name="ck_user_preferences_data_export_format",
        ),
        Index("ix_user_preferences_default_workspace", "default_workspace_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    default_workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    theme: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=DEFAULT_THEME,
        server_default=DEFAULT_THEME,
    )
    language: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=DEFAULT_LOCALE,
        server_default=DEFAULT_LOCALE,
    )
    timezone: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        default="UTC",
        server_default="UTC",
    )
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    data_export_format: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="json",
        server_default="json",
    )

    user: Mapped[Any] = relationship("platform.common.models.user.User")
    default_workspace: Mapped[Any | None] = relationship("platform.workspaces.models.Workspace")


class LocaleFile(Base, UUIDMixin):
    __tablename__ = "locale_files"
    __table_args__ = (
        UniqueConstraint("locale_code", "version", name="uq_locale_files_locale_version"),
        CheckConstraint(_check_values("locale_code", LOCALES), name="ck_locale_files_locale_code"),
        Index("ix_locale_files_locale_version_desc", "locale_code", text("version DESC")),
        Index("ix_locale_files_published_at", "published_at"),
    )

    locale_code: Mapped[str] = mapped_column(String(length=16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    translations: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    vendor_source_ref: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    publisher: Mapped[Any | None] = relationship("platform.common.models.user.User")
