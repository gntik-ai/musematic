# Data Model: Auth Bounded Context

**Feature**: 014-auth-bounded-context  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## SQLAlchemy Models

### UserCredential

```python
# src/platform/auth/models.py
class UserCredential(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)  # PHC format: $argon2id$v=19$...
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

### MfaEnrollment

```python
class MfaEnrollment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mfa_enrollments"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user_credentials.user_id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="totp")  # "totp" only for now
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted TOTP secret
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | active | disabled
    recovery_codes_hash: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # list of Argon2id hashes
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # set when status → active
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # pending enrollment expiry
```

### AuthAttempt

```python
class AuthAttempt(Base, UUIDMixin):
    __tablename__ = "auth_attempts"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)  # null for unknown emails
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv4 or IPv6
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)  # success | failure_password | failure_locked | failure_mfa
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

### PasswordResetToken

```python
class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user_credentials.user_id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)  # SHA-256 hex digest
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### ServiceAccountCredential

```python
class ServiceAccountCredential(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "service_account_credentials"

    service_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(512), nullable=False)  # Argon2id hash of full key (msk_...)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="service_account")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active | rotated | revoked
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)  # scope
```

### UserRole

```python
class UserRole(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", "workspace_id", name="uq_user_role_workspace"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # RoleType enum value
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)  # null = global
```

### RolePermission

```python
class RolePermission(Base, UUIDMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "resource_type", "action", name="uq_role_resource_action"),)

    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "agent", "workflow", "workspace"
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "read", "write", "delete", "admin"
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="workspace")  # global | workspace | own
```

---

## Enums

```python
# src/platform/auth/schemas.py (or a shared types module)
from enum import StrEnum

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
```

---

## Pydantic Schemas

```python
# src/platform/auth/schemas.py

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires

class MfaChallengeResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str  # temporary token to submit with TOTP code

class MfaVerifyRequest(BaseModel):
    mfa_token: str
    totp_code: str = Field(min_length=6, max_length=6)

class MfaEnrollResponse(BaseModel):
    secret: str  # base32-encoded TOTP secret (shown once)
    provisioning_uri: str  # otpauth:// URI for QR code
    recovery_codes: list[str]  # shown once, 10 codes

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
    api_key: str  # shown once — raw key with msk_ prefix
    role: str
```

---

## Redis Session Structure

```
# Session hash
session:{user_id}:{session_id}
  user_id: UUID string
  email: string
  roles_json: JSON string of [{role, workspace_id}, ...]
  device_info: string
  ip_address: string
  created_at: ISO timestamp
  last_activity: ISO timestamp
  refresh_jti: UUID string (JWT ID of the refresh token)
  TTL: 604800 seconds (7 days)

# User sessions set
user_sessions:{user_id}
  members: set of session_id strings
  TTL: 604800 seconds (7 days)

# Lockout counter
auth:lockout:{user_id}
  value: integer (failed attempt count)
  TTL: 900 seconds (15 minutes)

# Locked flag
auth:locked:{user_id}
  value: "1"
  TTL: 900 seconds (15 minutes)
```

---

## Kafka Event Schemas

```python
# src/platform/auth/events.py

class UserAuthenticatedPayload(BaseModel):
    user_id: UUID
    session_id: UUID
    ip_address: str
    device_info: str

class UserLockedPayload(BaseModel):
    user_id: UUID
    attempt_count: int
    locked_until: datetime

class SessionRevokedPayload(BaseModel):
    user_id: UUID
    session_id: UUID
    reason: str  # "logout" | "logout_all" | "revoked"

class MfaEnrolledPayload(BaseModel):
    user_id: UUID
    method: str  # "totp"

class PermissionDeniedPayload(BaseModel):
    user_id: UUID
    resource_type: str
    action: str
    reason: str  # "rbac_denied" | "purpose_violation"

class ApiKeyRotatedPayload(BaseModel):
    service_account_id: UUID
```

---

## Permission Matrix (Seed Data)

| Role | Resources | Actions | Scope |
|------|-----------|---------|-------|
| superadmin | * | * | global |
| platform_admin | workspace, user, agent, connector | read, write, delete, admin | global |
| workspace_owner | workspace, agent, workflow, connector | read, write, delete, admin | workspace |
| workspace_admin | agent, workflow, connector, interaction | read, write, delete | workspace |
| creator | agent, workflow, prompt, evaluation | read, write | workspace |
| operator | agent, workflow, execution, fleet | read, write | workspace |
| viewer | agent, workflow, execution, analytics | read | workspace |
| auditor | audit, analytics, trust, execution | read | workspace |
| agent | execution, memory, tool | read, write | own |
| service_account | (configurable per account) | (configurable) | workspace |

---

## Configuration (Additional Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_JWT_PRIVATE_KEY` | required | RS256 private key (PEM) for signing |
| `AUTH_JWT_PUBLIC_KEY` | required | RS256 public key (PEM) for verification |
| `AUTH_JWT_ALGORITHM` | `RS256` | JWT signing algorithm |
| `AUTH_ACCESS_TOKEN_TTL` | `900` | Access token expiry in seconds (15 min) |
| `AUTH_REFRESH_TOKEN_TTL` | `604800` | Refresh token expiry in seconds (7 days) |
| `AUTH_LOCKOUT_THRESHOLD` | `5` | Failed attempts before lockout |
| `AUTH_LOCKOUT_DURATION` | `900` | Lockout duration in seconds (15 min) |
| `AUTH_MFA_ENCRYPTION_KEY` | required | Fernet key for TOTP secret encryption |
| `AUTH_MFA_ENROLLMENT_TTL` | `600` | Pending MFA enrollment expiry in seconds |
| `AUTH_SESSION_TTL` | `604800` | Session TTL in seconds (7 days) |
| `AUTH_PASSWORD_RESET_TTL` | `3600` | Password reset token TTL in seconds |
