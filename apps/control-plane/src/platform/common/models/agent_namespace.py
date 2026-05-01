from __future__ import annotations

from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class AgentNamespace(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_namespaces"

    name: Mapped[str] = mapped_column(String(length=255), unique=True, nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
