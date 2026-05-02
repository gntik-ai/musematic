from __future__ import annotations

from datetime import UTC, datetime
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
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserStatus(StrEnum):
    pending_verification = "pending_verification"
    pending_approval = "pending_approval"
    pending_profile_completion = "pending_profile_completion"
    active = "active"
    suspended = "suspended"
    blocked = "blocked"
    archived = "archived"


class SignupSource(StrEnum):
    self_registration = "self_registration"
    invitation = "invitation"


class InvitationStatus(StrEnum):
    pending = "pending"
    consumed = "consumed"
    expired = "expired"
    revoked = "revoked"


class ApprovalDecision(StrEnum):
    approved = "approved"
    rejected = "rejected"


class User(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "accounts_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_accounts_users_tenant_email"),
    )

    email: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="accounts_user_status"),
        nullable=False,
        default=UserStatus.pending_verification,
    )
    signup_source: Mapped[SignupSource] = mapped_column(
        SAEnum(SignupSource, name="accounts_signup_source"),
        nullable=False,
        default=SignupSource.self_registration,
    )
    invitation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts_invitations.id"),
        nullable=True,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    suspend_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    max_workspaces: Mapped[int] = mapped_column(nullable=False, default=0)


class EmailVerification(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "accounts_email_verifications"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_accounts_email_verifications_token_hash"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts_users.id"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(length=64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Invitation(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "accounts_invitations"

    token_hash: Mapped[str] = mapped_column(
        String(length=64), nullable=False, unique=True, index=True
    )
    inviter_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    invitee_email: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    invitee_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InvitationStatus] = mapped_column(
        SAEnum(InvitationStatus, name="accounts_invitation_status"),
        nullable=False,
        default=InvitationStatus.pending,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "accounts_approval_requests"
    __table_args__ = (UniqueConstraint("user_id", name="uq_accounts_approval_requests_user_id"),)

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts_users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    decision: Mapped[ApprovalDecision | None] = mapped_column(
        SAEnum(ApprovalDecision, name="accounts_approval_decision"),
        nullable=True,
    )
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserOnboardingState(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "user_onboarding_states"
    __table_args__ = (
        UniqueConstraint("user_id", name="user_onboarding_states_user_unique"),
        Index("user_onboarding_states_tenant_idx", "tenant_id"),
        CheckConstraint(
            "last_step_attempted IN "
            "('workspace_named','invitations','first_agent','tour','done')",
            name="ck_user_onboarding_states_last_step",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts_users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    step_workspace_named: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    step_invitations_sent_or_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    step_first_agent_created_or_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    step_tour_started_or_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    last_step_attempted: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="workspace_named",
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantFirstAdminInvitation(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "tenant_first_admin_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="tenant_first_admin_invitations_token_unique"),
        Index(
            "tenant_first_admin_invitations_tenant_active_idx",
            "tenant_id",
            "expires_at",
            postgresql_where=text(
                "consumed_at IS NULL AND prior_token_invalidated_at IS NULL"
            ),
        ),
        Index(
            "tenant_first_admin_invitations_target_email_idx",
            "target_email",
            "expires_at",
        ),
    )

    token_hash: Mapped[str] = mapped_column(String(length=128), nullable=False, unique=True)
    target_email: Mapped[str] = mapped_column(String(length=320), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prior_token_invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    setup_step_state: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    mfa_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_super_admin_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    consumed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
