from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=50),
        nullable=False,
        server_default="pending_verification",
    )

