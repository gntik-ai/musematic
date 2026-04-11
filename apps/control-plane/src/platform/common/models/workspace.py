from __future__ import annotations

from platform.common.models.base import Base
from platform.common.models.mixins import (
    EventSourcedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)
from uuid import UUID

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Workspace(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, EventSourcedMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
