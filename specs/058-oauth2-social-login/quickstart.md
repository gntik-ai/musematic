# Quickstart Test Scenarios: OAuth2 Social Login

**Phase 1 output for**: [plan.md](plan.md)  
**Date**: 2026-04-18

Each scenario is independently verifiable. Scenarios 1–6 cover the happy path. Scenarios 7–12 cover security and edge cases. Scenarios 13–15 cover the frontend. Scenarios 16–17 cover admin configuration.

---

## Scenario 1 — Google New-User Auto-Provision (Happy Path)

**Setup**: Google provider configured and enabled. Test Google account has never signed in.

```bash
# 1. Get authorization URL
GET /api/v1/auth/oauth/google/authorize
# Expected: 200, {redirect_url: "https://accounts.google.com/...?state=...&code_challenge=..."}

# 2. Complete Google consent (manual or mock)
# Provider redirects to: GET /api/v1/auth/oauth/google/callback?code=<code>&state=<state>

# 3. Verify callback response
# Expected: 302 redirect to /home with Set-Cookie: session=<token>

# 4. Verify new user in DB
SELECT * FROM users WHERE email = 'testuser@gmail.com';
# Expected: 1 row, correct name, default_role = 'member'

SELECT * FROM oauth_links WHERE external_id = '<google_sub>';
# Expected: 1 row, provider_id = google provider, user_id = new user

# 5. Verify audit record
SELECT * FROM oauth_audit_entries ORDER BY created_at DESC LIMIT 1;
# Expected: action='user_provisioned', outcome='success', provider_type='google', no token values
```

---

## Scenario 2 — GitHub New-User Auto-Provision (Happy Path)

**Setup**: GitHub provider configured and enabled. Test GitHub account has never signed in.

```bash
GET /api/v1/auth/oauth/github/authorize
# Expected: 200, {redirect_url: "https://github.com/login/oauth/authorize?..."}
# No code_challenge in URL (GitHub supports PKCE but spec uses PKCE for all flows per FR-001)

# After consent:
GET /api/v1/auth/oauth/github/callback?code=<code>&state=<state>
# Expected: 302, Set-Cookie: session=<token>

# Verify: user created with GitHub primary verified email
SELECT * FROM users WHERE email = 'githubuser@example.com';
```

---

## Scenario 3 — Returning User Sign-In (Existing Link)

**Setup**: User previously signed in with Google; `oauth_links` row exists.

```bash
# Complete Google authorize/callback flow for the same Google account
# Expected: no new user created, same user_id returned in session
# Verify: oauth_links.last_login_at updated
SELECT last_login_at FROM oauth_links WHERE external_id = '<google_sub>';
```

---

## Scenario 4 — Account Linking (Existing Local-Password User)

**Setup**: User has a local-password account. No OAuth links yet.

```bash
# 1. Sign in with local password, get session token
POST /api/v1/auth/login → session token

# 2. Initiate link
POST /api/v1/auth/oauth/google/link
Authorization: Bearer <session_token>
# Expected: 200, {redirect_url: "https://accounts.google.com/..."}

# 3. Complete Google consent
# Callback processed as link (not new session)

# 4. Verify link created
SELECT * FROM oauth_links WHERE user_id = '<existing_user_id>';
# Expected: 1 row for google provider

# 5. Sign out, sign in via Google
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<state>
# Expected: session issued for the existing user (not a new user)
```

---

## Scenario 5 — Domain Restriction Rejection (Google)

**Setup**: Google provider configured with `domain_restrictions: ["company.com"]`. Test account uses `@othercompany.com`.

```bash
# Complete Google authorize flow with othercompany.com account
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<state>
# Expected: 302 redirect to /login?error=domain_not_allowed

# Verify: no user created, no oauth_link created
SELECT COUNT(*) FROM users WHERE email = 'user@othercompany.com';
# Expected: 0

# Verify audit record
SELECT * FROM oauth_audit_entries ORDER BY created_at DESC LIMIT 1;
# Expected: action='sign_in_failed', outcome='failure', failure_reason='domain_restriction'
```

---

## Scenario 6 — Unlink Provider

**Setup**: User has local password + Google linked.

```bash
# Unlink Google
DELETE /api/v1/auth/oauth/google/link
Authorization: Bearer <session_token>
# Expected: 204

# Verify link removed
SELECT COUNT(*) FROM oauth_links WHERE user_id = '<user_id>' AND provider_id = '<google_provider_id>';
# Expected: 0

# Verify Google sign-in now treats user as new identity
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<state>
# Expected: new user auto-provisioned (not the old user)
```

---

## Scenario 7 — Stale State Rejection (TTL Expired)

**Setup**: State stored in Redis with 600 s TTL. Wait >600 s or manually delete the key.

```bash
# Attempt callback with expired state
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<old_state>
# Expected: 302 redirect to /login?error=expired_session, no session issued

# Verify: state key no longer exists in Redis
redis-cli GET "oauth:state:<nonce>"
# Expected: nil
```

---

## Scenario 8 — HMAC State Tampering

**Setup**: Valid state from an authorize call. Tamper with the HMAC portion.

```bash
# Replace the HMAC part of the state parameter with random bytes
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<nonce>.<invalid_hmac>
# Expected: 302 redirect to /login?error=invalid_state
```

---

## Scenario 9 — Rate Limit on Callback

**Setup**: `AUTH_OAUTH_RATE_LIMIT_MAX=10`, `AUTH_OAUTH_RATE_LIMIT_WINDOW=60`.

```bash
# Send 11 requests from the same IP within 60 seconds
for i in {1..11}; do
  curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:8000/api/v1/auth/oauth/google/callback?code=x&state=y"
done
# Expected: first 10 return 302 (to login with error, state invalid), 11th returns 429
# 429 response must include Retry-After header
# State entries in Redis must NOT be decremented/consumed for rejected requests
```

---

## Scenario 10 — Client Secret Never Exposed

**Automated scan scenarios**:

```bash
# Admin list all providers
GET /api/v1/admin/oauth/providers
Authorization: Bearer <admin_token>
# Response body must not contain the resolved secret value
# Grep result for secrets pattern:
echo '<response_body>' | grep -E "(secret|password|token|key)" | grep -v "_ref"
# Expected: no matches (only client_secret_ref is present, not the value)

# Check structured logs during token exchange
grep -E "(client_secret|access_token|id_token|authorization_code)" /var/log/platform/*.json
# Expected: no matches

# Check audit entries
SELECT changed_fields FROM oauth_audit_entries WHERE action = 'provider_configured';
# Expected: changed_fields contains key names but no resolved secret values
```

---

## Scenario 11 — Unlink Rejected: Last Auth Method

**Setup**: User has only a Google link and no local password.

```bash
DELETE /api/v1/auth/oauth/google/link
Authorization: Bearer <session_token>
# Expected: 409 Conflict
# Response: {"detail": "Cannot unlink: this is your only authentication method"}

# Verify: oauth_links unchanged
SELECT COUNT(*) FROM oauth_links WHERE user_id = '<user_id>';
# Expected: 1 (unchanged)
```

---

## Scenario 12 — Provider Disabled Mid-Flow

**Setup**: User starts authorize flow. Admin disables provider before callback.

```bash
# 1. Get redirect URL (state stored in Redis)
GET /api/v1/auth/oauth/google/authorize
# → state stored in Redis

# 2. Admin disables provider
PUT /api/v1/admin/oauth/providers/google
{"enabled": false, ...}

# 3. Callback arrives (valid code and state from Redis)
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<valid_state>
# Expected: 302 redirect to /login?error=provider_disabled
# No session issued. State entry consumed (single-use).
```

---

## Scenario 13 — Login Page Shows Only Enabled Providers

```bash
# Verify public providers endpoint
GET /api/v1/auth/oauth/providers
# Expected: only {provider_type, display_name} for enabled providers
# No credentials, no restrictions

# After disabling Google:
PUT /api/v1/admin/oauth/providers/google {"enabled": false}
GET /api/v1/auth/oauth/providers
# Expected: Google absent from list
```

---

## Scenario 14 — Group-to-Role Mapping on Provisioning

**Setup**: Google provider with `group_role_mapping: {"engineering": "workspace_admin"}`. Test Google account is a member of the `engineering` Workspace group.

```bash
# Complete Google sign-in for user with engineering group membership
GET /api/v1/auth/oauth/google/callback?code=<code>&state=<state>
# After provisioning:
SELECT role FROM users WHERE email = 'engineer@company.com';
# Expected: role = 'workspace_admin' (not 'member' default)

SELECT external_groups FROM oauth_links WHERE external_id = '<sub>';
# Expected: array containing "engineering"
```

---

## Scenario 15 — Org Restriction Rejection (GitHub)

**Setup**: GitHub provider with `org_restrictions: ["my-org"]`. Test account is not a member of `my-org`.

```bash
GET /api/v1/auth/oauth/github/callback?code=<code>&state=<state>
# Expected: 302 redirect to /login?error=org_not_allowed

# Verify: no user created
SELECT COUNT(*) FROM users WHERE created_via = 'github_oauth' ORDER BY created_at DESC LIMIT 1;
# Expected: 0 new rows
```

---

## Scenario 16 — Admin Configuration Round-Trip

```bash
# 1. Configure Google provider for the first time
PUT /api/v1/admin/oauth/providers/google
Content-Type: application/json
{
  "display_name": "Sign in with Google",
  "enabled": false,
  "client_id": "test-client-id",
  "client_secret_ref": "k8s:platform-control/oauth-google/client-secret",
  "redirect_uri": "https://platform.example.com/api/v1/auth/oauth/google/callback",
  "scopes": ["openid", "email", "profile"],
  "domain_restrictions": [],
  "org_restrictions": [],
  "group_role_mapping": {},
  "default_role": "member",
  "require_mfa": false
}
# Expected: 201 Created

# 2. Verify audit entry created
SELECT action, actor_id FROM oauth_audit_entries ORDER BY created_at DESC LIMIT 1;
# Expected: action='provider_configured', actor_id=<admin_user_id>

# 3. Enable provider
PUT /api/v1/admin/oauth/providers/google {"enabled": true, ...}
# Expected: 200 OK

# 4. Verify on login page
GET /api/v1/auth/oauth/providers
# Expected: Google appears in list
```

---

## Scenario 17 — Audit Feed Contains No Token Values

**Automated invariant check** (should be part of CI):

```python
# After running all sign-in scenarios, scan all audit entries for token-like values
import re
rows = db.execute("SELECT * FROM oauth_audit_entries").fetchall()
token_pattern = re.compile(r'[A-Za-z0-9\-_]{64,}')  # long base64-like strings
for row in rows:
    text = str(row)
    assert not token_pattern.search(text), f"Possible token found in audit entry: {row.id}"
```
