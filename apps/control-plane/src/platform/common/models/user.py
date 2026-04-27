from __future__ import annotations

from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDMixin

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "users"

    username: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    email: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=50),
        nullable=False,
        server_default="pending_verification",
    )
    mfa_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_required_before_login: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    force_password_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_install_checklist_state: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
