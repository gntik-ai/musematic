from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RoleType(StrEnum):
    SUPERADMIN = "superadmin"
    PLATFORM_ADMIN = "platform_admin"
    WORKSPACE_OWNER = "workspace_owner"
    WORKSPACE_ADMIN = "workspace_admin"
    CREATOR = "creator"
    OPERATOR = "operator"
    VIEWER = "viewer"
    AUDITOR = "auditor"
    AGENT = "agent"
    SERVICE_ACCOUNT = "service_account"


class AuthOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE_PASSWORD = "failure_password"
    FAILURE_LOCKED = "failure_locked"
    FAILURE_MFA = "failure_mfa"


class MfaStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MfaChallengeResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    totp_code: str = Field(min_length=6, max_length=64)


class MfaConfirmRequest(BaseModel):
    totp_code: str = Field(min_length=6, max_length=64)


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


class MfaConfirmResponse(BaseModel):
    status: str = "active"
    message: str = "MFA enrollment confirmed"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PermissionCheckRequest(BaseModel):
    resource_type: str
    action: str
    workspace_id: UUID | None = None


class PermissionCheckResponse(BaseModel):
    allowed: bool
    role: str
    resource_type: str
    action: str
    scope: str
    reason: str | None = None


class ServiceAccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: RoleType = RoleType.SERVICE_ACCOUNT
    workspace_id: UUID | None = None


class ServiceAccountCreateResponse(BaseModel):
    service_account_id: UUID
    name: str
    api_key: str
    role: str


class MessageResponse(BaseModel):
    message: str


class LogoutAllResponse(MessageResponse):
    sessions_revoked: int

