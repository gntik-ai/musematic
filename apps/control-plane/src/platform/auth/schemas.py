from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.auth.models import IBORSourceType, IBORSyncMode, IBORSyncRunStatus
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.networks import EmailStr


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


class IBORRoleMappingRule(BaseModel):
    directory_group: str = Field(min_length=1, max_length=512)
    platform_role: str = Field(min_length=1, max_length=50)
    workspace_scope: UUID | None = None


class IBORConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: IBORSourceType
    sync_mode: IBORSyncMode
    cadence_seconds: int = Field(default=3600, ge=60, le=86400)
    credential_ref: str = Field(min_length=1, max_length=255)
    role_mapping_policy: list[IBORRoleMappingRule] = Field(default_factory=list)
    enabled: bool = True


class IBORConnectorUpdate(IBORConnectorCreate):
    pass


class IBORConnectorResponse(BaseModel):
    id: UUID
    name: str
    source_type: IBORSourceType
    sync_mode: IBORSyncMode
    cadence_seconds: int
    credential_ref: str
    role_mapping_policy: list[IBORRoleMappingRule]
    enabled: bool
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class IBORConnectorListResponse(BaseModel):
    items: list[IBORConnectorResponse]


class IBORSyncRunResponse(BaseModel):
    id: UUID
    connector_id: UUID
    mode: IBORSyncMode
    started_at: datetime
    finished_at: datetime | None = None
    status: IBORSyncRunStatus
    counts: dict[str, int] = Field(default_factory=dict)
    error_details: list[dict[str, object]] = Field(default_factory=list)
    triggered_by: UUID | None = None


class IBORSyncRunListResponse(BaseModel):
    items: list[IBORSyncRunResponse]
    next_cursor: str | None = None


class IBORSyncTriggerResponse(BaseModel):
    run_id: UUID
    connector_id: UUID
    status: IBORSyncRunStatus
    started_at: datetime
