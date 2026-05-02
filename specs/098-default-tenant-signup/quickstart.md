# Quickstart — UPD-048 Public Signup at Default Tenant Only (Local Validation)

**Audience**: An engineer about to start building Phase A, B, or C of UPD-048, or wanting to validate the feature end-to-end.

**Preconditions**:

- UPD-046 (tenant architecture) is fully landed: default tenant exists, hostname resolver is wired, RLS policies active, opaque-404 helper available.
- UPD-047 (subscriptions) is landed: `SubscriptionService.provision_for_default_workspace` is callable.
- The local E2E harness from UPD-046 is reachable at `http://localhost:8081`. `app.localhost` resolves to the default tenant; `acme.localhost` resolves to a pre-provisioned Enterprise tenant.
- UPD-046's PostgreSQL bootstrap pre-creates `musematic_platform_staff` with `BYPASSRLS`.

This walkthrough exercises the end-to-end flows: default-tenant signup → verification → workspace auto-create → wizard; Enterprise subdomain signup attempt → 404; first-admin invitation flow at `/setup`; cross-tenant invitation; multi-tenant switcher.

## 0. Preconditions

```bash
make dev-up
export PLATFORM_API_URL=http://localhost:8081
export PLATFORM_UI_URL=http://localhost:8080
export DEFAULT_TENANT_HOST=app.localhost
export ACME_TENANT_HOST=acme.localhost
export PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict
```

Confirm UPD-048 migrations 106 + 107 applied:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT to_regclass('user_onboarding_states'),
          to_regclass('tenant_first_admin_invitations');"
# Expect: both not null
```

## 1. Default-tenant signup

```bash
# Submit signup
curl -isS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.test",
    "display_name": "Alice Example",
    "password": "Test1234!Strong"
  }' \
  "$PLATFORM_API_URL/api/v1/accounts/register"
# Expect: HTTP/1.1 202 with anti-enumeration neutral body
```

Fetch the verification token from the dev SMTP relay or the dev-only test helper:

```bash
VERIFY_TOKEN=$(python tests/e2e/scripts/dev_email.py latest \
  --to alice@example.test \
  --field verify_token)

# Verify
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$VERIFY_TOKEN\"}" \
  "$PLATFORM_API_URL/api/v1/accounts/verify-email" | jq
```

Confirm the workspace and Free subscription auto-created:

```bash
ALICE_USER_ID=$(kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -t -c \
  "SELECT id FROM users WHERE email='alice@example.test';" | tr -d '[:space:]')

kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT w.id, w.name, w.is_default, s.plan_id, s.status
     FROM workspaces w
     LEFT JOIN subscriptions s ON s.scope_type='workspace' AND s.scope_id = w.id
    WHERE w.created_by_user_id = '$ALICE_USER_ID';"
# Expect: 1 row, is_default=true, status='active' or 'trial'
```

## 2. Onboarding wizard

```bash
ALICE_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email alice@example.test \
  --tenant default)

# Get initial wizard state
curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  "$PLATFORM_API_URL/api/v1/onboarding/state" | jq

# Advance step 1
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspace_name":"Alice research"}' \
  "$PLATFORM_API_URL/api/v1/onboarding/step/workspace-name" | jq
# Expect: { "next_step": "invitations" }

# Skip step 2
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"invitations":[]}' \
  "$PLATFORM_API_URL/api/v1/onboarding/step/invitations" | jq

# Dismiss
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  "$PLATFORM_API_URL/api/v1/onboarding/dismiss" | jq

# Re-launch from settings
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  "$PLATFORM_API_URL/api/v1/onboarding/relaunch" | jq
# Expect: dismissed_at=null, last_step_attempted='first_agent' (resume at first incomplete)
```

## 3. Signup at Enterprise subdomain returns opaque 404

```bash
for slug in acme bogus xyz123; do
  curl -isS -o /tmp/$slug-signup.body -D /tmp/$slug-signup.headers \
    -X POST -H "Host: $slug.localhost" \
    -H "Content-Type: application/json" \
    -d '{"email":"x@x.test","display_name":"Probe","password":"x"}' \
    "$PLATFORM_API_URL/api/v1/accounts/register"
done

# All bodies and headers byte-identical (ignoring per-request timing tags):
sha256sum /tmp/*-signup.body
sha256sum /tmp/*-signup.headers
# Expect: all body hashes match; all header hashes match
```

## 4. Enterprise tenant first-admin onboarding

```bash
# Provision Acme via UPD-046 (skip if already provisioned)
SUPERADMIN_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email superadmin@e2e.test --role superadmin)
ACME_PROVISION=$(./scripts/dev/provision-enterprise-tenant.sh acme cto@acme.test)

# Fetch the first-admin invitation token from the dev SMTP relay
SETUP_TOKEN=$(python tests/e2e/scripts/dev_email.py latest \
  --to cto@acme.test \
  --field setup_token)

# Validate the token
curl -sS -H "Host: $ACME_TENANT_HOST" \
  "$PLATFORM_API_URL/api/v1/setup/validate-token?token=$SETUP_TOKEN" | jq
# Expect: { "valid": true, "tenant_slug": "acme", "current_step": "tos", ... }
# Expect: Set-Cookie: setup_session=...

# Walk through the steps
curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"tos_version":"2026-05-02","accepted_at_ts":"2026-05-02T10:30:00Z"}' \
  "$PLATFORM_API_URL/api/v1/setup/step/tos"

curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"method":"password","password":"Acme2026!Strong"}' \
  "$PLATFORM_API_URL/api/v1/setup/step/credentials"

# Try to skip MFA — expect 403
curl -isS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt \
  "$PLATFORM_API_URL/api/v1/setup/step/workspace"
# Expect: HTTP/1.1 403, code=mfa_enrollment_required

# Complete MFA enrolment
MFA_START=$(curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  "$PLATFORM_API_URL/api/v1/setup/step/mfa/start")
TOTP_SECRET=$(echo "$MFA_START" | jq -r .totp_secret)
TOTP_CODE=$(python tests/e2e/scripts/totp.py "$TOTP_SECRET")

curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  -H "Content-Type: application/json" \
  -d "{\"totp_code\":\"$TOTP_CODE\"}" \
  "$PLATFORM_API_URL/api/v1/setup/step/mfa/verify" | jq
# Expect: { "next_step": "workspace", "recovery_codes": [...10 codes...] }

# Workspace
curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme Research"}' \
  "$PLATFORM_API_URL/api/v1/setup/step/workspace"

# Skip invitations
curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt -c /tmp/cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"invitations":[]}' \
  "$PLATFORM_API_URL/api/v1/setup/step/invitations"

# Complete
curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -b /tmp/cookies.txt \
  "$PLATFORM_API_URL/api/v1/setup/complete" | jq
# Expect: { "redirect_to": "/admin/dashboard" }
```

Try to reuse the token after consumption:

```bash
curl -isS -H "Host: $ACME_TENANT_HOST" \
  "$PLATFORM_API_URL/api/v1/setup/validate-token?token=$SETUP_TOKEN"
# Expect: HTTP/1.1 410, code=setup_token_invalid
```

## 5. Resend a first-admin invitation

```bash
# As super admin, resend
ACME_TENANT_ID=$(curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/tenants?slug=acme" | jq -r '.items[0].id')

curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/tenants/$ACME_TENANT_ID/resend-first-admin-invitation" | jq

# Confirm prior token invalidated
curl -isS -H "Host: $ACME_TENANT_HOST" \
  "$PLATFORM_API_URL/api/v1/setup/validate-token?token=$SETUP_TOKEN"
# Expect: HTTP/1.1 410 — same opaque expired surface
```

## 6. Cross-tenant invitation

```bash
# Pre-create Juan in the default tenant via signup (same as section 1)
# Then, as the Acme tenant admin, invite juan@example.test:
ACME_ADMIN_TOKEN=<token issued by the /setup completion above>

curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -H "Authorization: Bearer $ACME_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"juan@example.test","roles":["viewer"]}' \
  "$PLATFORM_API_URL/api/v1/accounts/invitations"

# Juan receives invite; opens accept page
JUAN_INVITE_TOKEN=$(python tests/e2e/scripts/dev_email.py latest \
  --to juan@example.test \
  --field invite_token)

curl -sS -X POST -H "Host: $ACME_TENANT_HOST" \
  -H "Content-Type: application/json" \
  -d "{\"token\":\"$JUAN_INVITE_TOKEN\",\"display_name\":\"Juan Example\",\"password\":\"AcmeJuan2026!\"}" \
  "$PLATFORM_API_URL/api/v1/accounts/invitations/$JUAN_INVITE_TOKEN/accept" | jq

# Verify two independent records exist
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD="$PLATFORM_STAFF_DB_PASSWORD" \
  psql -h 127.0.0.1 -U musematic_platform_staff -d musematic -c \
  "SELECT u.id, u.email, t.slug FROM users u JOIN tenants t ON u.tenant_id=t.id WHERE u.email='juan@example.test';"
# Expect: 2 rows, slug ∈ {default, acme}
```

## 7. `/me/memberships` introspection

```bash
JUAN_DEFAULT_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email juan@example.test --tenant default)

curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $JUAN_DEFAULT_TOKEN" \
  "$PLATFORM_API_URL/api/v1/me/memberships" | jq
# Expect:
# {
#   "memberships": [
#     { "tenant_slug": "default", "is_current_tenant": true, ... },
#     { "tenant_slug": "acme",    "is_current_tenant": false, "login_url": "https://acme.musematic.ai/login" }
#   ],
#   "count": 2
# }
```

## 8. Tenant switcher rendering

Open a browser, sign in as Juan at `app.localhost:8080`. Confirm the shell renders a tenant switcher in the header listing both tenants. Click "Acme" — confirm the browser redirects to `acme.localhost:8080/login` and Juan is treated as unauthenticated until he signs in at Acme.

Sign in as a single-tenant user (Alice from section 1). Confirm the tenant switcher is HIDDEN.

## 9. Run the E2E suites

```bash
PLATFORM_API_URL=$PLATFORM_API_URL RUN_SIGNUP_DEFAULT_ONLY_E2E=true \
  pytest apps/control-plane/tests/e2e/suites/signup_default_only/ -v
```

Expected: J19 (UPD-037 regression with default-tenant assertions), the new tenant-admin setup suite, the cross-tenant invitation suite, and the multi-tenant switcher suite all pass.

## Done

If every step above succeeds, your local-dev cluster has a working tenant-aware signup, an Enterprise first-admin onboarding flow, cross-tenant identity, and the tenant switcher. You are ready to build Phases A–C and the E2E phase.

## Validation status

On 2026-05-02, this walkthrough was updated to match the implemented request contracts. A fresh kind-cluster validation attempt was made with:

```bash
PRUNE_DOCKER_CACHE=0 DOCKER_BUILD_CACHE_DIR=/tmp/musematic-docker-cache make dev-up
```

The run failed while creating the `amp-e2e` kind cluster, before any platform charts or UPD-048 steps could execute:

```text
ERROR: failed to create cluster: could not find a log line that matches "Reached target .*Multi-User System.*|detected cgroup v1"
```

Re-run this quickstart after the kind node bootstrap issue is resolved.

A second fresh-kind validation attempt was run on 2026-05-02 during `/speckit.implement` with the same command. It reproduced the same `kind create cluster` failure, still before any platform charts or UPD-048 endpoint checks could run. No additional request-contract drift was observed because the quickstart steps were not reached.
