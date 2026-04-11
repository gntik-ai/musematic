# Data Model: Accounts Bounded Context

**Feature**: 016-accounts-bounded-context  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## Enums

### `UserStatus` (SQLAlchemy Enum / Pydantic Literal)

```python
class UserStatus(str, Enum):
    pending_verification = "pending_verification"
    pending_approval     = "pending_approval"
    active               = "active"
    suspended            = "suspended"
    blocked              = "blocked"
    archived             = "archived"
```

### `SignupSource` (SQLAlchemy Enum)

```python
class SignupSource(str, Enum):
    self_registration = "self_registration"
    invitation        = "invitation"
```

### `InvitationStatus` (SQLAlchemy Enum)

```python
class InvitationStatus(str, Enum):
    pending  = "pending"
    consumed = "consumed"
    expired  = "expired"
    revoked  = "revoked"
```

### `ApprovalDecision` (SQLAlchemy Enum)

```python
class ApprovalDecision(str, Enum):
    approved = "approved"
    rejected = "rejected"
```

### `SignupMode` (Python Literal — config only, not DB)

```python
SignupMode = Literal["open", "invite_only", "admin_approval"]
```

---

## SQLAlchemy Models (`accounts/models.py`)

### `User`

Inherits: `Base`, `UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, non-null | from UUIDMixin |
| `email` | `String(255)` | UNIQUE, non-null, indexed | Lowercase-normalized on insert |
| `display_name` | `String(100)` | non-null | 2–100 chars (validated in schema) |
| `status` | `Enum(UserStatus)` | non-null, default=`pending_verification` | Lifecycle state |
| `signup_source` | `Enum(SignupSource)` | non-null, default=`self_registration` | How the user arrived |
| `invitation_id` | `UUID` | FK → `invitations.id`, nullable | Set when source=invitation |
| `email_verified_at` | `DateTime(tz=True)` | nullable | Set when email verified |
| `activated_at` | `DateTime(tz=True)` | nullable | Set on first transition to active |
| `suspended_at` | `DateTime(tz=True)` | nullable | Set on suspension |
| `suspended_by` | `UUID` | nullable | Admin user ID |
| `suspend_reason` | `Text` | nullable | |
| `blocked_at` | `DateTime(tz=True)` | nullable | |
| `blocked_by` | `UUID` | nullable | Admin user ID |
| `block_reason` | `Text` | nullable | |
| `archived_at` | `DateTime(tz=True)` | nullable | |
| `archived_by` | `UUID` | nullable | Admin user ID |
| `created_at` | `DateTime(tz=True)` | non-null, default=now | from TimestampMixin |
| `updated_at` | `DateTime(tz=True)` | non-null, default=now | from TimestampMixin |
| `deleted_at` | `DateTime(tz=True)` | nullable | from SoftDeleteMixin (used for archived) |

**Indexes**:
- `email` (unique index)
- `status` (for admin queue queries)
- `created_at` (for sorting approval queue)

**Table name**: `accounts_users`

---

### `EmailVerification`

Inherits: `Base`, `UUIDMixin`, `TimestampMixin`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | from UUIDMixin |
| `user_id` | `UUID` | FK → `accounts_users.id`, non-null, indexed | |
| `token_hash` | `String(64)` | non-null, indexed | SHA-256 hex of plaintext token |
| `expires_at` | `DateTime(tz=True)` | non-null | `created_at + TTL_HOURS` |
| `consumed` | `Boolean` | non-null, default=False | Single-use |
| `created_at` | `DateTime(tz=True)` | non-null | from TimestampMixin |

**Table name**: `accounts_email_verifications`

**Constraint**: `UniqueConstraint("user_id", name="uq_email_verify_user")` — only one active (unconsumed, unexpired) token per user (enforced by service layer; DB allows multiple historical records).

---

### `Invitation`

Inherits: `Base`, `UUIDMixin`, `TimestampMixin`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | from UUIDMixin |
| `token_hash` | `String(64)` | UNIQUE, non-null, indexed | SHA-256 hex of plaintext token |
| `inviter_id` | `UUID` | non-null, indexed | FK → `accounts_users.id` (inviting admin/workspace owner) |
| `invitee_email` | `String(255)` | non-null, indexed | Lowercase-normalized |
| `invitee_message` | `Text` | nullable | Optional personal message |
| `roles_json` | `Text` | non-null | JSON array of `RoleType` strings |
| `workspace_ids_json` | `Text` | nullable | JSON array of workspace UUID strings for pre-assignment |
| `status` | `Enum(InvitationStatus)` | non-null, default=`pending` | |
| `expires_at` | `DateTime(tz=True)` | non-null | `created_at + TTL_DAYS` |
| `consumed_by_user_id` | `UUID` | nullable | Set on acceptance |
| `consumed_at` | `DateTime(tz=True)` | nullable | |
| `revoked_by` | `UUID` | nullable | Admin who revoked |
| `revoked_at` | `DateTime(tz=True)` | nullable | |
| `created_at` | `DateTime(tz=True)` | non-null | from TimestampMixin |

**Table name**: `accounts_invitations`

---

### `ApprovalRequest`

Inherits: `Base`, `UUIDMixin`, `TimestampMixin`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | from UUIDMixin |
| `user_id` | `UUID` | UNIQUE, non-null, indexed | FK → `accounts_users.id` — one request per user |
| `requested_at` | `DateTime(tz=True)` | non-null | When email verification completed |
| `reviewer_id` | `UUID` | nullable | Admin who acted |
| `decision` | `Enum(ApprovalDecision)` | nullable | Set when reviewed |
| `decision_at` | `DateTime(tz=True)` | nullable | |
| `reason` | `Text` | nullable | Optional rejection reason |
| `created_at` | `DateTime(tz=True)` | non-null | from TimestampMixin |

**Table name**: `accounts_approval_requests`

---

## Pydantic Schemas (`accounts/schemas.py`)

### Request Schemas

```python
class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # Must have: uppercase, lowercase, digit, special char
        ...

class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ApproveUserRequest(BaseModel):
    reason: str | None = None

class RejectUserRequest(BaseModel):
    reason: str

class SuspendUserRequest(BaseModel):
    reason: str

class BlockUserRequest(BaseModel):
    reason: str

class ArchiveUserRequest(BaseModel):
    reason: str | None = None

class ReactivateUserRequest(BaseModel):
    reason: str | None = None

class UnblockUserRequest(BaseModel):
    reason: str | None = None

class ResetPasswordRequest(BaseModel):
    """Admin-initiated password reset. Optional: force_change_on_login."""
    force_change_on_login: bool = True

class CreateInvitationRequest(BaseModel):
    email: EmailStr
    roles: list[RoleType] = Field(min_length=1)
    workspace_ids: list[UUID] | None = None
    message: str | None = Field(default=None, max_length=500)

class AcceptInvitationRequest(BaseModel):
    token: str
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str: ...
```

### Response Schemas

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    status: UserStatus
    signup_source: SignupSource
    email_verified_at: datetime | None
    activated_at: datetime | None
    created_at: datetime

class RegisterResponse(BaseModel):
    """Anti-enumeration: same shape regardless of whether email was new or duplicate."""
    message: str = "If this email is not already registered, a verification email has been sent"

class VerifyEmailResponse(BaseModel):
    user_id: UUID
    status: UserStatus    # active or pending_approval

class PendingApprovalItem(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    registered_at: datetime
    email_verified_at: datetime

class PendingApprovalsResponse(BaseModel):
    items: list[PendingApprovalItem]
    total: int

class InvitationResponse(BaseModel):
    id: UUID
    invitee_email: str
    roles: list[RoleType]
    workspace_ids: list[UUID] | None
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime

class InvitationDetailsResponse(BaseModel):
    """Public view for invitee — no internal IDs."""
    invitee_email: str
    inviter_display_name: str
    roles: list[RoleType]
    message: str | None
    expires_at: datetime
```

---

## Lifecycle State Machine (`accounts/state_machine.py`)

```python
VALID_TRANSITIONS: dict[UserStatus, set[UserStatus]] = {
    UserStatus.pending_verification: {
        UserStatus.pending_approval,
        UserStatus.active,
    },
    UserStatus.pending_approval: {
        UserStatus.active,
        UserStatus.archived,
    },
    UserStatus.active: {
        UserStatus.suspended,
        UserStatus.blocked,
        UserStatus.archived,
    },
    UserStatus.suspended: {
        UserStatus.active,
        UserStatus.blocked,
        UserStatus.archived,
    },
    UserStatus.blocked: {
        UserStatus.active,
        UserStatus.archived,
    },
    UserStatus.archived: set(),  # Terminal state
}
```

---

## Kafka Events (`accounts/events.py`)

All events use `EventEnvelope` from `common/events/envelope.py`.

| Event Type | Payload Key Fields | Consumers |
|---|---|---|
| `accounts.user.registered` | `user_id`, `email`, `signup_source` | audit |
| `accounts.user.email_verified` | `user_id`, `email` | audit |
| `accounts.user.approved` | `user_id`, `reviewer_id`, `reason` | notifications, audit |
| `accounts.user.rejected` | `user_id`, `reviewer_id`, `reason` | notifications, audit |
| `accounts.user.activated` | `user_id`, `email`, `display_name`, `signup_source` | **workspaces** (provisioning), notifications, audit |
| `accounts.user.suspended` | `user_id`, `suspended_by`, `reason` | auth (session invalidation alt), audit |
| `accounts.user.reactivated` | `user_id`, `reactivated_by` | notifications, audit |
| `accounts.user.blocked` | `user_id`, `blocked_by`, `reason` | audit |
| `accounts.user.unblocked` | `user_id`, `unblocked_by` | audit |
| `accounts.user.archived` | `user_id`, `archived_by` | audit |
| `accounts.user.mfa_reset` | `user_id`, `reset_by` | notifications, audit |
| `accounts.user.password_reset_initiated` | `user_id`, `initiated_by` | audit |
| `accounts.invitation.created` | `invitation_id`, `invitee_email`, `inviter_id` | audit |
| `accounts.invitation.accepted` | `invitation_id`, `user_id`, `invitee_email` | audit |
| `accounts.invitation.revoked` | `invitation_id`, `revoked_by` | audit |

**Topic**: `accounts.events`  
**Key**: `user_id` (or `invitation_id` for invitation events)

---

## Redis Keys

| Key Pattern | Type | Value | TTL | Purpose |
|---|---|---|---|---|
| `resend_verify:{user_id}` | String (int) | Resend count | 3600s | Rate-limit verification email resends (max 3/hour) |

---

## Additional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCOUNTS_SIGNUP_MODE` | `open` | `open \| invite_only \| admin_approval` |
| `ACCOUNTS_EMAIL_VERIFY_TTL_HOURS` | `24` | Email verification token expiry in hours |
| `ACCOUNTS_INVITE_TTL_DAYS` | `7` | Invitation token expiry in days |
| `ACCOUNTS_RESEND_RATE_LIMIT` | `3` | Max verification email resends per hour |
