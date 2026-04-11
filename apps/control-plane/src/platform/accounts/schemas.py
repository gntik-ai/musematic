from __future__ import annotations

import re
from datetime import datetime
from platform.accounts.models import InvitationStatus, UserStatus
from platform.auth.schemas import RoleType
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_PATTERNS = (
    re.compile(r"[A-Z]"),
    re.compile(r"[a-z]"),
    re.compile(r"\d"),
    re.compile(r"[^A-Za-z0-9]"),
)


def _validate_password_strength(value: str) -> str:
    if len(value) < 12 or any(pattern.search(value) is None for pattern in PASSWORD_PATTERNS):
        raise ValueError(
            "Password must be at least 12 characters and include uppercase, lowercase, "
            "digit, and special character",
        )
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


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
    email: EmailStr
    roles: list[RoleType] = Field(min_length=1)
    workspace_ids: list[UUID] | None = None
    message: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


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
