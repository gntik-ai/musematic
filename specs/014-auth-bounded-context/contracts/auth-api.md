# REST Contract: Auth API

**Path prefix**: `/api/v1/auth`  
**Feature**: 014-auth-bounded-context

---

## POST /api/v1/auth/login

**Auth**: None (public endpoint)

### Request Body

```json
{
  "email": "user@example.com",
  "password": "SecureP@ss123"
}
```

### Response (200 OK) — Login Success (no MFA)

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Response (200 OK) — MFA Required

```json
{
  "mfa_required": true,
  "mfa_token": "temp-mfa-token-uuid"
}
```

### Error Responses

| Status | Code | When |
|--------|------|------|
| 401 | `INVALID_CREDENTIALS` | Wrong email or password |
| 403 | `ACCOUNT_LOCKED` | Account locked due to failed attempts |
| 422 | `VALIDATION_ERROR` | Invalid request body |

---

## POST /api/v1/auth/mfa/verify

**Auth**: None (uses temporary MFA token from login)

### Request Body

```json
{
  "mfa_token": "temp-mfa-token-uuid",
  "totp_code": "123456"
}
```

### Response (200 OK)

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Error Responses

| Status | Code | When |
|--------|------|------|
| 401 | `INVALID_MFA_CODE` | Wrong or expired TOTP code |
| 401 | `INVALID_MFA_TOKEN` | Expired or invalid MFA token |

---

## POST /api/v1/auth/mfa/enroll

**Auth**: Required (Bearer JWT)

### Response (200 OK)

```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/Musematic:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Musematic",
  "recovery_codes": [
    "A1B2C3D4", "E5F6G7H8", "I9J0K1L2", "M3N4O5P6", "Q7R8S9T0",
    "U1V2W3X4", "Y5Z6A7B8", "C9D0E1F2", "G3H4I5J6", "K7L8M9N0"
  ]
}
```

### Error Responses

| Status | Code | When |
|--------|------|------|
| 409 | `MFA_ALREADY_ENROLLED` | MFA is already active |

---

## POST /api/v1/auth/mfa/confirm

**Auth**: Required (Bearer JWT)

### Request Body

```json
{
  "totp_code": "123456"
}
```

### Response (200 OK)

```json
{
  "status": "active",
  "message": "MFA enrollment confirmed"
}
```

### Error Responses

| Status | Code | When |
|--------|------|------|
| 401 | `INVALID_MFA_CODE` | Wrong TOTP code — enrollment not confirmed |
| 404 | `NO_PENDING_ENROLLMENT` | No pending MFA enrollment found |

---

## POST /api/v1/auth/refresh

**Auth**: None (uses refresh token)

### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

### Response (200 OK)

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Error Responses

| Status | Code | When |
|--------|------|------|
| 401 | `INVALID_REFRESH_TOKEN` | Expired, revoked, or invalid refresh token |

---

## POST /api/v1/auth/logout

**Auth**: Required (Bearer JWT)

### Response (200 OK)

```json
{
  "message": "Session terminated"
}
```

---

## POST /api/v1/auth/logout-all

**Auth**: Required (Bearer JWT)

### Response (200 OK)

```json
{
  "message": "All sessions terminated",
  "sessions_revoked": 3
}
```

---

## Correlation Headers

| Header | Direction | Description |
|--------|-----------|-------------|
| `X-Correlation-ID` | Request/Response | Propagated or auto-generated UUID |
| `X-Request-ID` | Response | Server-generated request ID |

## Service Account Authentication

| Header | Description |
|--------|-------------|
| `X-API-Key` | Service account API key (`msk_...`) |

When `X-API-Key` is present, it takes precedence over `Authorization: Bearer`.

## Error Body Format (all routes)

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid email or password",
    "details": {}
  }
}
```
