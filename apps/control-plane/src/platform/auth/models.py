from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class UserCredential(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_credentials"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(length=255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(length=512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MfaEnrollment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mfa_enrollments"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_credentials.user_id"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(length=20), nullable=False, default="totp")
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(length=20), nullable=False, default="pending")
    recovery_codes_hash: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthAttempt(Base, UUIDMixin):
    __tablename__ = "auth_attempts"

    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(length=255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(length=45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(length=512), nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(length=30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_credentials.user_id"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(length=128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceAccountCredential(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "service_account_credentials"

    service_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(length=512), nullable=False)
    role: Mapped[str] = mapped_column(String(length=50), nullable=False, default="service_account")
    status: Mapped[str] = mapped_column(String(length=20), nullable=False, default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )


class UserRole(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role", "workspace_id", name="uq_user_role_workspace"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(length=50), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )


class RolePermission(Base, UUIDMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role", "resource_type", "action", name="uq_role_resource_action"),
    )

    role: Mapped[str] = mapped_column(String(length=50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(length=100), nullable=False)
    action: Mapped[str] = mapped_column(String(length=50), nullable=False)
    scope: Mapped[str] = mapped_column(String(length=20), nullable=False, default="workspace")
