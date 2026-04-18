# REST API Contracts: OAuth2 Social Login

**Date**: 2026-04-18  
**Router file**: `apps/control-plane/src/platform/auth/router_oauth.py`  
**Base path**: All endpoints under `/api/v1`

---

## Public Endpoints (unauthenticated)

### GET /api/v1/auth/oauth/providers

List enabled OAuth providers for display on the login page.

**Auth**: None (public)  
**Response 200**:
```json
{
  "providers": [
    {
      "provider_type": "google",
      "display_name": "Sign in with Google"
    },
    {
      "provider_type": "github",
      "display_name": "Sign in with GitHub"
    }
  ]
}
```
**Notes**:
- Returns only `enabled=true` providers.
- Never exposes `client_id`, `client_secret_ref`, `redirect_uri`, or any restriction config.

---

### GET /api/v1/auth/oauth/{provider}/authorize

Initiate an OAuth2 authorization flow. Generates PKCE + state, stores state in Redis, returns the provider redirect URL.

**Auth**: None  
**Path params**: `provider` — one of `google`, `github`  
**Response 200**:
```json
{
  "redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&state=...&code_challenge=...&code_challenge_method=S256&..."
}
```
**Errors**:
- `404` — provider not found or disabled

---

### GET /api/v1/auth/oauth/{provider}/callback

Handle provider callback after user consent. Rate-limited by source IP.

**Auth**: None  
**Path params**: `provider` — one of `google`, `github`  
**Query params**: `code` (string), `state` (string), `error` (string, optional)  
**Success response**: `302 Redirect` to frontend with `Set-Cookie: session=<token>; HttpOnly; Secure; SameSite=Lax`  
**Error response**: `302 Redirect` to frontend `/login?error=<sanitized_reason>`  
**Rate limit**: 429 with `Retry-After: {seconds}` when exceeded  
**Notes**:
- If `error` query param is present (user cancelled), redirect to login with appropriate message.
- State is validated first (HMAC integrity + Redis lookup). Failure → redirect to login.
- Domain/org restrictions checked before any user creation. Rejection → redirect to login.
- Duplicate email collision (existing unlinked user) → redirect to login with link-intent prompt.

---

## Authenticated User Endpoints

### POST /api/v1/auth/oauth/{provider}/link

Initiate account linking for an already-authenticated user.

**Auth**: Bearer session token (existing platform session)  
**Path params**: `provider` — one of `google`, `github`  
**Response 200**:
```json
{
  "redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
}
```
**Notes**: Generates new PKCE + state. State is marked as a link flow (not a sign-in) to prevent the callback from creating a new session.  
**Errors**: `400` if provider already linked to this user

---

### DELETE /api/v1/auth/oauth/{provider}/link

Unlink a previously-linked provider from the authenticated user's account.

**Auth**: Bearer session token  
**Path params**: `provider` — one of `google`, `github`  
**Response 204**: No content  
**Errors**:
- `404` — provider not linked to this user
- `409` — cannot unlink: this is the user's only authentication method (FR-017)

---

## Admin Endpoints

### GET /api/v1/admin/oauth/providers

List all configured OAuth providers with full configuration (admin only).

**Auth**: Bearer session token with `platform_admin` role  
**Response 200**:
```json
{
  "providers": [
    {
      "id": "uuid",
      "provider_type": "google",
      "display_name": "Sign in with Google",
      "enabled": true,
      "client_id": "123-abc.apps.googleusercontent.com",
      "client_secret_ref": "k8s:platform-control/oauth-google/client-secret",
      "redirect_uri": "https://platform.example.com/api/v1/auth/oauth/google/callback",
      "scopes": ["openid", "email", "profile"],
      "domain_restrictions": ["company.com"],
      "org_restrictions": [],
      "group_role_mapping": {"engineering": "workspace_admin"},
      "default_role": "member",
      "require_mfa": false,
      "created_at": "2026-04-18T00:00:00Z",
      "updated_at": "2026-04-18T00:00:00Z"
    }
  ]
}
```
**Notes**: `client_secret_ref` is the reference string only — never the resolved secret value.

---

### PUT /api/v1/admin/oauth/providers/{provider}

Create or update a provider configuration.

**Auth**: Bearer session token with `platform_admin` role  
**Path params**: `provider` — one of `google`, `github`  
**Request body**:
```json
{
  "display_name": "Sign in with Google",
  "enabled": true,
  "client_id": "123-abc.apps.googleusercontent.com",
  "client_secret_ref": "k8s:platform-control/oauth-google/client-secret",
  "redirect_uri": "https://platform.example.com/api/v1/auth/oauth/google/callback",
  "scopes": ["openid", "email", "profile"],
  "domain_restrictions": ["company.com"],
  "org_restrictions": [],
  "group_role_mapping": {"engineering": "workspace_admin"},
  "default_role": "member",
  "require_mfa": false
}
```
**Response 200**: Full provider object (same schema as GET admin response, single provider)  
**Response 201**: Created (first time configuring this provider type)  
**Errors**:
- `400` — validation error (e.g., invalid scopes, unknown role in mapping)
- `403` — insufficient permissions  
**Notes**:
- Upsert by `provider_type`. Writes audit entry for configuration change.
- Changing `client_secret_ref` is tracked in `changed_fields` of audit entry (reference only, not resolved value).
- Disabling a provider (`enabled: false`) immediately affects `/authorize` and `/callback`; in-flight sessions remain valid (FR-027).
