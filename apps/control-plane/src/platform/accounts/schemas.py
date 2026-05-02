from __future__ import annotations

import re
from datetime import datetime
from platform.accounts.models import InvitationStatus, UserStatus
from platform.auth.schemas import RoleType
from platform.localization.constants import LOCALES
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

PASSWORD_PATTERNS = (
    re.compile(r"[A-Z]"),
    re.compile(r"[a-z]"),
    re.compile(r"\d"),
    re.compile(r"[^A-Za-z0-9]"),
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("value is not a valid email address")
    return normalized


def _validate_password_strength(value: str) -> str:
    if len(value) < 12 or any(pattern.search(value) is None for pattern in PASSWORD_PATTERNS):
        raise ValueError(
            "Password must be at least 12 characters and include uppercase, lowercase, "
            "digit, and special character",
        )
    return value


class RegisterRequest(BaseModel):
    email: str
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class ProfileUpdateRequest(BaseModel):
    locale: str | None = Field(default=None, max_length=16)
    timezone: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized not in LOCALES:
            raise ValueError(f"locale must be one of: {', '.join(LOCALES)}")
        return normalized

    @field_validator("timezone", "display_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> ProfileUpdateRequest:
        if self.locale is None and self.timezone is None and self.display_name is None:
            raise ValueError("At least one profile field must be provided")
        return self


class ApproveUserRequest(BaseModel):
    reason: str | None = None


class RejectUserRequest(BaseModel):
    reason: str = Field(min_length=1)


class SuspendUserRequest(BaseModel):
    reason: str = Field(min_length=1)


class BlockUserRequest(BaseModel):
    reason: str = Field(min_length=1)


class ArchiveUserRequest(BaseModel):
    reason: str | None = None


class ReactivateUserRequest(BaseModel):
    reason: str | None = None


class UnblockUserRequest(BaseModel):
    reason: str | None = None


class ResetPasswordRequest(BaseModel):
    force_change_on_login: bool = True


class CreateInvitationRequest(BaseModel):
    email: str
    roles: list[RoleType] = Field(min_length=1)
    workspace_ids: list[UUID] | None = None
    message: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1)
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class RegisterResponse(BaseModel):
    message: str = "If this email is not already registered, a verification email has been sent"


class ResendVerificationResponse(BaseModel):
    message: str = (
        "If a pending verification account exists for this email, "
        "a new verification email has been sent"
    )


class VerifyEmailResponse(BaseModel):
    user_id: UUID
    status: UserStatus


class ProfileUpdateResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    status: UserStatus
    locale: str | None = None
    timezone: str | None = None


class PendingApprovalItem(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    registered_at: datetime
    email_verified_at: datetime


class PendingApprovalsResponse(BaseModel):
    items: list[PendingApprovalItem]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class UserLifecycleResponse(BaseModel):
    user_id: UUID
    status: UserStatus


class InvitationResponse(BaseModel):
    id: UUID
    invitee_email: str
    roles: list[str]
    workspace_ids: list[UUID] | None
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime


class RevokeInvitationResponse(BaseModel):
    invitation_id: UUID
    status: InvitationStatus


class PaginatedInvitationsResponse(BaseModel):
    items: list[InvitationResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class InvitationDetailsResponse(BaseModel):
    invitee_email: str
    inviter_display_name: str
    roles: list[str]
    message: str | None
    expires_at: datetime


class AcceptInvitationResponse(BaseModel):
    user_id: UUID
    email: str
    status: UserStatus
    display_name: str


class ResetMfaResponse(BaseModel):
    user_id: UUID
    mfa_cleared: bool


class ResetPasswordResponse(BaseModel):
    user_id: UUID
    password_reset_initiated: bool


class UnlockResponse(BaseModel):
    user_id: UUID
    unlocked: bool


class OnboardingStateView(BaseModel):
    user_id: UUID
    tenant_id: UUID
    step_workspace_named: bool = False
    step_invitations_sent_or_skipped: bool = False
    step_first_agent_created_or_skipped: bool = False
    step_tour_started_or_skipped: bool = False
    last_step_attempted: Literal[
        "workspace_named",
        "invitations",
        "first_agent",
        "tour",
        "done",
    ] = "workspace_named"
    dismissed_at: datetime | None = None
    first_agent_step_available: bool = True
    default_workspace_id: UUID | None = None
    default_workspace_name: str | None = None


class OnboardingStepWorkspaceName(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=100)


class OnboardingInvitationEntry(BaseModel):
    email: str
    role: str = Field(default="workspace_member", max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class OnboardingStepInvitations(BaseModel):
    invitations: list[OnboardingInvitationEntry] = Field(default_factory=list)


class OnboardingStepFirstAgent(BaseModel):
    skipped: bool = True
    agent_fqn: str | None = Field(default=None, max_length=255)


class OnboardingStepTour(BaseModel):
    started: bool = False


class TenantFirstAdminInviteCreate(BaseModel):
    tenant_id: UUID
    target_email: str
    super_admin_id: UUID

    @field_validator("target_email")
    @classmethod
    def normalize_target_email(cls, value: str) -> str:
        return _normalize_email(value)


class TenantFirstAdminInviteValidationResponse(BaseModel):
    valid: bool = True
    tenant_id: UUID
    tenant_slug: str
    tenant_display_name: str
    target_email: str
    expires_at: datetime
    current_step: str = "tos"
    completed_steps: list[str] = Field(default_factory=list)


class SetupStepTos(BaseModel):
    tos_version: str = Field(min_length=1, max_length=64)
    accepted_at_ts: datetime


class SetupStepCredentials(BaseModel):
    method: Literal["password", "oauth"]
    password: str | None = Field(default=None, min_length=12)
    provider: str | None = Field(default=None, max_length=32)
    oauth_token: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_method_payload(self) -> SetupStepCredentials:
        if self.method == "password":
            if self.password is None:
                raise ValueError("password is required for password setup")
            self.password = _validate_password_strength(self.password)
        if self.method == "oauth" and (not self.provider or not self.oauth_token):
            raise ValueError("provider and oauth_token are required for OAuth setup")
        return self


class SetupStepWorkspace(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SetupStepInvitations(BaseModel):
    invitations: list[OnboardingInvitationEntry] = Field(default_factory=list)


class SetupStepMfaVerify(BaseModel):
    totp_code: str = Field(min_length=6, max_length=12)


class MembershipEntry(BaseModel):
    tenant_id: UUID
    tenant_slug: str
    tenant_kind: str
    tenant_display_name: str
    user_id_within_tenant: UUID
    role: str | None = None
    is_current_tenant: bool
    login_url: str


class MembershipsListResponse(BaseModel):
    memberships: list[MembershipEntry]
    count: int
