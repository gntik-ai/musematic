from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    SoftDeleteMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class IBORSourceType(StrEnum):
    ldap = "ldap"
    oidc = "oidc"
    scim = "scim"


class IBORSyncMode(StrEnum):
    pull = "pull"
    push = "push"


class IBORSyncRunStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    partial_success = "partial_success"
    failed = "failed"


class OAuthProviderSource(StrEnum):
    env_var = "env_var"
    manual = "manual"
    imported = "imported"


class UserCredential(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
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


class MfaEnrollment(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class AuthAttempt(Base, TenantScopedMixin, UUIDMixin):
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


class PasswordResetToken(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class ServiceAccountCredential(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
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
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class UserRole(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role", "workspace_id", name="uq_user_role_workspace"),
        Index("ix_user_roles_source_connector", "source_connector_id"),
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
    source_connector_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
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


class IBORConnector(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "ibor_connectors"

    name: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True, index=True)
    source_type: Mapped[IBORSourceType] = mapped_column(
        SAEnum(IBORSourceType, name="auth_ibor_source_type"),
        nullable=False,
    )
    sync_mode: Mapped[IBORSyncMode] = mapped_column(
        SAEnum(IBORSyncMode, name="auth_ibor_sync_mode"),
        nullable=False,
    )
    cadence_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    credential_ref: Mapped[str] = mapped_column(String(length=255), nullable=False)
    role_mapping_policy: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(length=32), nullable=True)


class IBORSyncRun(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "ibor_sync_runs"
    __table_args__ = (Index("ix_ibor_sync_runs_connector_started", "connector_id", "started_at"),)

    connector_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ibor_connectors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[IBORSyncMode] = mapped_column(
        SAEnum(IBORSyncMode, name="auth_ibor_sync_mode"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[IBORSyncRunStatus] = mapped_column(
        SAEnum(IBORSyncRunStatus, name="auth_ibor_sync_run_status"),
        nullable=False,
        default=IBORSyncRunStatus.running,
    )
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    error_details: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    triggered_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class OAuthProvider(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "oauth_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_type", name="uq_oauth_providers_tenant_type"),
    )

    provider_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    client_id: Mapped[str] = mapped_column(String(length=256), nullable=False)
    client_secret_ref: Mapped[str] = mapped_column(String(length=256), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(length=512), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    domain_restrictions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    org_restrictions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    group_role_mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    default_role: Mapped[str] = mapped_column(String(length=64), nullable=False, default="member")
    require_mfa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[OAuthProviderSource] = mapped_column(
        SAEnum(
            OAuthProviderSource,
            name="oauth_provider_source",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=OAuthProviderSource.manual,
    )
    last_edited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_successful_auth_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    links: Mapped[list[OAuthLink]] = relationship(
        "OAuthLink",
        back_populates="provider",
        lazy="selectin",
    )
    rate_limits: Mapped[OAuthProviderRateLimit | None] = relationship(
        "OAuthProviderRateLimit",
        back_populates="provider",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class OAuthProviderRateLimit(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "oauth_provider_rate_limits"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_oauth_provider_rate_limits_provider"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("oauth_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    per_ip_max: Mapped[int] = mapped_column(Integer, nullable=False)
    per_ip_window: Mapped[int] = mapped_column(Integer, nullable=False)
    per_user_max: Mapped[int] = mapped_column(Integer, nullable=False)
    per_user_window: Mapped[int] = mapped_column(Integer, nullable=False)
    global_max: Mapped[int] = mapped_column(Integer, nullable=False)
    global_window: Mapped[int] = mapped_column(Integer, nullable=False)

    provider: Mapped[OAuthProvider] = relationship(
        "OAuthProvider",
        back_populates="rate_limits",
        lazy="selectin",
    )


class OAuthLink(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "oauth_links"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_oauth_links_provider_ext"),
        UniqueConstraint("user_id", "provider_id", name="uq_oauth_links_user_provider"),
        Index("idx_oauth_links_user", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("oauth_providers.id"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(length=256), nullable=False)
    external_email: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    external_name: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    external_avatar_url: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    external_groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[OAuthProvider] = relationship(
        "OAuthProvider",
        back_populates="links",
        lazy="selectin",
    )


class OAuthAuditEntry(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "oauth_audit_entries"
    __table_args__ = (
        Index("idx_oauth_audit_user", "user_id", "created_at"),
        Index("idx_oauth_audit_provider", "provider_id", "created_at"),
    )

    provider_type: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("oauth_providers.id"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    action: Mapped[str] = mapped_column(String(length=64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(length=32), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    changed_fields: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
