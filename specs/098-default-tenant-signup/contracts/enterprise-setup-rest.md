# Contract — Enterprise Tenant `/setup` REST API

**Prefix**: `/api/v1/setup/*`
**Owner**: `apps/control-plane/src/platform/accounts/setup_router.py`
**Authorization**: Token-gated — every endpoint requires a valid, unconsumed, unexpired `tenant_first_admin_invitations` token attached as a query parameter on the first request and as a server-issued setup-session cookie on subsequent requests.
**OpenAPI tag**: `setup`.

This namespace runs at the Enterprise tenant subdomain (e.g., `acme.musematic.ai/api/v1/setup/...`). The hostname middleware resolves the tenant via the standard UPD-046 path; the setup endpoints additionally validate the invitation token bound to that exact tenant.

## `GET /api/v1/setup/validate-token`

Validates a setup token. Used by `(auth)/setup/page.tsx` on initial load to decide whether to render the wizard or the "expired" error page.

**Query parameters**: `token=<raw-token>`.

**Response 200**:

```jsonc
{
  "valid": true,
  "tenant_id": "uuid",
  "tenant_slug": "acme",
  "tenant_display_name": "Acme Corp",
  "target_email": "cto@acme.test",
  "expires_at": "2026-05-09T10:00:00Z",
  "current_step": "tos",                          // resume position
  "completed_steps": []
}
```

**Response 410**: token expired or already consumed or superseded by a resend. Body: standard `PlatformError` with code `setup_token_invalid`.

The response sets a setup-session cookie scoped to the tenant subdomain so subsequent step requests can be made without echoing the token in the URL.

## `POST /api/v1/setup/step/tos`

Records Terms-of-Service acceptance. Body:

```jsonc
{ "tos_version": "2026-05-01", "accepted_at_ts": "2026-05-02T10:30:00Z" }
```

Response 200: `{ "next_step": "credentials" }`. Audit-chain entry recorded.

## `POST /api/v1/setup/step/credentials`

Sets up credentials for the tenant-admin user. Body (one of):

```jsonc
{ "method": "password", "password": "<plaintext>" }
```

OR (for OAuth linking when the tenant has an OAuth provider configured):

```jsonc
{ "method": "oauth", "provider": "google", "oauth_token": "<from-oauth-callback>" }
```

Response 200: `{ "next_step": "mfa" }`. Audit-chain entry recorded. The user record in the Acme tenant is created at this step.

## `POST /api/v1/setup/step/mfa/start`

Initiates TOTP enrolment. Empty body.

Response 200:

```jsonc
{
  "totp_secret": "base32-encoded-secret",
  "provisioning_uri": "otpauth://totp/Musematic:cto@acme.test?secret=...&issuer=Musematic",
  "recovery_codes_to_generate_count": 10
}
```

The frontend renders the QR code and recovery codes from this response.

## `POST /api/v1/setup/step/mfa/verify`

Completes TOTP enrolment. Body:

```jsonc
{ "totp_code": "123456" }
```

Response 200: `{ "next_step": "workspace", "recovery_codes": ["...", "..."] }`. The recovery codes are returned ONCE (per UPD-014 pattern); the frontend mandates the user acknowledge they have stored them. Audit-chain entry recorded.

**This endpoint is the ONLY exit from the MFA step**. Subsequent step endpoints invoke the `assert_role_mfa_requirement('tenant_admin', user)` server-side guard; without a verified MFA enrolment they return 403 `code=mfa_enrollment_required` (per FR-013, SC-004).

## `POST /api/v1/setup/step/workspace`

Creates the first workspace. Body:

```jsonc
{ "name": "Acme Research" }
```

Response 200: `{ "next_step": "invitations", "workspace_id": "uuid" }`. Audit-chain entry recorded.

## `POST /api/v1/setup/step/invitations`

Sends initial invitations (or skips). Body:

```jsonc
{
  "invitations": [
    { "email": "alice@acme.test", "role": "workspace_admin" },
    { "email": "bob@acme.test",   "role": "workspace_member" }
  ]
}
```

OR an empty `invitations` array to skip. Response 200: `{ "next_step": "done", "invitations_sent": 2 }`. Audit-chain entry recorded.

## `POST /api/v1/setup/complete`

Finalises the setup flow. Empty body. Response 200: `{ "redirect_to": "/admin/dashboard" }`. The setup-session cookie is invalidated; the standard tenant-admin login session is established. Audit-chain entry `accounts.setup.completed` recorded.

## Error model

Standard `PlatformError`. Notable codes:

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated`, `setup_session_invalid` |
| 403 | `mfa_enrollment_required` (MFA gate refusal) |
| 410 | `setup_token_invalid` (token expired, consumed, or superseded) |
| 422 | `invalid_step_payload`, `password_too_weak`, `oauth_provider_unavailable` |
| 409 | `setup_already_completed` |

## Resend behaviour

When super admin clicks "Resend invitation" on `/admin/tenants/{id}` (UPD-046 endpoint), the platform calls `TenantFirstAdminInviteService.resend(invitation_id)` which:

1. Sets `prior_token_invalidated_at = now()` on the existing row.
2. Creates a fresh `tenant_first_admin_invitations` row with a new `token_hash` and the same `target_email`.
3. Sends a fresh invitation email.
4. Records audit-chain entry `accounts.first_admin_invitation.resent` naming the prior and new token IDs.

Any subsequent `GET /api/v1/setup/validate-token` with the prior token returns 410 `code=setup_token_invalid` with no special "superseded" disclosure (the user simply requests a new invitation).

## Test contract

Integration tests in `apps/control-plane/tests/integration/accounts/`:

- `test_setup_token_lifecycle.py` — happy path; expired path; consumed-twice rejection; superseded path returns the same opaque 410 as expired.
- `test_setup_flow_mandatory_mfa.py` — automated probe attempts every step's endpoint after `step/credentials` without first completing `step/mfa/verify`; all return 403 `mfa_enrollment_required` (SC-004).
- `test_first_admin_invite.py` — issue, resend, validate-token round-trips; resend invalidates prior; audit-chain entries present for each.
