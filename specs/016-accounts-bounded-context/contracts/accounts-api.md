# API Contracts: Accounts Bounded Context

**Feature**: 016-accounts-bounded-context  
**Date**: 2026-04-11  
**Base path**: `/api/v1/accounts`

All error responses follow the platform standard:
```json
{"error": {"code": "ERROR_CODE", "message": "Human-readable message", "details": [...]}}
```

---

## Public Endpoints (No Authentication Required)

### POST /api/v1/accounts/register

**Purpose**: Self-register a new user account.  
**Auth**: None  
**Signup mode guard**: Returns `403 SELF_REGISTRATION_DISABLED` when mode is `invite_only`.

**Request**:
```json
{
  "email": "user@example.com",
  "display_name": "Jane Smith",
  "password": "SecureP@ssw0rd!"
}
```

**Response** `202 Accepted` (always — anti-enumeration):
```json
{
  "message": "If this email is not already registered, a verification email has been sent"
}
```

**Errors**:
- `403 SELF_REGISTRATION_DISABLED` — signup mode is `invite_only`
- `422 VALIDATION_ERROR` — email format invalid, display_name length, password strength

---

### POST /api/v1/accounts/verify-email

**Purpose**: Verify email address using the token from the verification email.  
**Auth**: None

**Request**:
```json
{"token": "<plaintext_token>"}
```

**Response** `200 OK`:
```json
{
  "user_id": "uuid",
  "status": "active"   // or "pending_approval"
}
```

**Errors**:
- `400 INVALID_OR_EXPIRED_TOKEN` — token not found, expired, or already consumed (generic, anti-enumeration)

---

### POST /api/v1/accounts/resend-verification

**Purpose**: Request a new verification email.  
**Auth**: None

**Request**:
```json
{"email": "user@example.com"}
```

**Response** `202 Accepted` (always — anti-enumeration):
```json
{
  "message": "If a pending verification account exists for this email, a new verification email has been sent"
}
```

**Errors**:
- `429 RATE_LIMIT_EXCEEDED` — more than `ACCOUNTS_RESEND_RATE_LIMIT` resends in the past hour

---

### GET /api/v1/accounts/invitations/{token}

**Purpose**: Get invitation details before acceptance (so the UI can pre-fill the email and show role assignments).  
**Auth**: None

**Response** `200 OK`:
```json
{
  "invitee_email": "invitee@example.com",
  "inviter_display_name": "Admin User",
  "roles": ["workspace_editor"],
  "message": "Welcome to our team!",
  "expires_at": "2026-04-18T12:00:00Z"
}
```

**Errors**:
- `404 INVITATION_NOT_FOUND` — token not found, expired, consumed, or revoked

---

### POST /api/v1/accounts/invitations/{token}/accept

**Purpose**: Accept an invitation and create an account.  
**Auth**: None

**Request**:
```json
{
  "token": "<plaintext_token>",
  "display_name": "Jane Smith",
  "password": "SecureP@ssw0rd!"
}
```

**Response** `201 Created`:
```json
{
  "user_id": "uuid",
  "email": "invitee@example.com",
  "status": "active",
  "display_name": "Jane Smith"
}
```

**Errors**:
- `400 INVITATION_ALREADY_CONSUMED` — invitation already used
- `400 INVITATION_EXPIRED` — invitation has expired
- `400 INVITATION_REVOKED` — invitation was revoked
- `409 EMAIL_ALREADY_REGISTERED` — invitee email already has an active account
- `422 VALIDATION_ERROR` — display_name or password validation failure

---

## Admin Endpoints (Authentication Required — `workspace_admin` or `superadmin`)

### GET /api/v1/accounts/pending-approvals

**Purpose**: List accounts awaiting admin approval.  
**Auth**: JWT — `workspace_admin` or `superadmin` role required  
**Query params**: `page` (int, default 1), `page_size` (int, default 20)

**Response** `200 OK`:
```json
{
  "items": [
    {
      "user_id": "uuid",
      "email": "user@example.com",
      "display_name": "Jane Smith",
      "registered_at": "2026-04-11T09:00:00Z",
      "email_verified_at": "2026-04-11T09:05:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_next": true,
  "has_prev": false
}
```

---

### POST /api/v1/accounts/{user_id}/approve

**Purpose**: Approve a pending user account.  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**:
```json
{"reason": "Approved after manual review"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "active"}
```

**Errors**:
- `404 USER_NOT_FOUND`
- `409 INVALID_TRANSITION` — user is not in `pending_approval` status

---

### POST /api/v1/accounts/{user_id}/reject

**Purpose**: Reject a pending user account (archives it).  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**:
```json
{"reason": "Does not meet onboarding criteria"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "archived"}
```

**Errors**:
- `404 USER_NOT_FOUND`
- `409 INVALID_TRANSITION` — user is not in `pending_approval` status

---

### POST /api/v1/accounts/{user_id}/suspend

**Purpose**: Temporarily suspend an active user.  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**:
```json
{"reason": "Security incident under investigation"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "suspended"}
```

**Errors**:
- `404 USER_NOT_FOUND`
- `409 INVALID_TRANSITION`

---

### POST /api/v1/accounts/{user_id}/reactivate

**Purpose**: Reactivate a suspended user.  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request** (optional reason):
```json
{"reason": "Investigation cleared"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "active"}
```

---

### POST /api/v1/accounts/{user_id}/block

**Purpose**: Permanently block a user (stronger than suspend).  
**Auth**: JWT — `superadmin` only (stronger action requires higher privilege)

**Request**:
```json
{"reason": "Confirmed policy violation"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "blocked"}
```

---

### POST /api/v1/accounts/{user_id}/unblock

**Purpose**: Unblock a blocked user.  
**Auth**: JWT — `superadmin` only

**Request** (optional reason):
```json
{"reason": "Appeal approved"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "active"}
```

---

### POST /api/v1/accounts/{user_id}/archive

**Purpose**: Soft-delete a user account.  
**Auth**: JWT — `superadmin` only

**Request** (optional reason):
```json
{"reason": "Account closure request"}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "status": "archived"}
```

---

### POST /api/v1/accounts/{user_id}/reset-mfa

**Purpose**: Clear a user's MFA enrollment (admin action).  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**: Empty body `{}`

**Response** `200 OK`:
```json
{"user_id": "uuid", "mfa_cleared": true}
```

---

### POST /api/v1/accounts/{user_id}/reset-password

**Purpose**: Admin-initiated password reset.  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**:
```json
{"force_change_on_login": true}
```

**Response** `200 OK`:
```json
{"user_id": "uuid", "password_reset_initiated": true}
```

---

### POST /api/v1/accounts/{user_id}/unlock

**Purpose**: Clear a lockout imposed by failed login attempts (auth bounded context lockout counter).  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**: Empty body `{}`

**Response** `200 OK`:
```json
{"user_id": "uuid", "unlocked": true}
```

---

### POST /api/v1/accounts/invitations

**Purpose**: Create a new invitation.  
**Auth**: JWT — `workspace_admin` or `superadmin`

**Request**:
```json
{
  "email": "newuser@example.com",
  "roles": ["workspace_editor"],
  "workspace_ids": ["uuid1"],
  "message": "Welcome to the platform!"
}
```

**Response** `201 Created`:
```json
{
  "id": "uuid",
  "invitee_email": "newuser@example.com",
  "roles": ["workspace_editor"],
  "workspace_ids": ["uuid1"],
  "status": "pending",
  "expires_at": "2026-04-18T12:00:00Z",
  "created_at": "2026-04-11T12:00:00Z"
}
```

**Errors**:
- `409 EMAIL_ALREADY_REGISTERED` — email already has an active account
- `422 VALIDATION_ERROR`

---

### GET /api/v1/accounts/invitations

**Purpose**: List invitations created by the current admin.  
**Auth**: JWT — `workspace_admin` or `superadmin`  
**Query params**: `status` (filter), `page`, `page_size`

**Response** `200 OK`:
```json
{
  "items": [...InvitationResponse],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "has_next": false,
  "has_prev": false
}
```

---

### DELETE /api/v1/accounts/invitations/{invitation_id}

**Purpose**: Revoke a pending invitation.  
**Auth**: JWT — original inviter or `superadmin`

**Response** `200 OK`:
```json
{"invitation_id": "uuid", "status": "revoked"}
```

**Errors**:
- `404 INVITATION_NOT_FOUND`
- `409 INVITATION_ALREADY_CONSUMED_OR_EXPIRED` — cannot revoke a consumed/expired invitation
