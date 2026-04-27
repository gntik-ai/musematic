# Quickstart: Public Signup Flow

## Enable Local Signup

1. Set `NEXT_PUBLIC_FEATURE_SIGNUP_ENABLED=true` for the web app.
2. Set `ACCOUNTS_SIGNUP_MODE=open` on the control plane.
3. Open `/login`, follow the `Sign up` link, submit email, display name, password, AI disclosure consent, and terms consent.
4. Confirm the browser lands on `/verify-email/pending?email=...`.
5. Use the verification email link. It should load `/verify-email?token=...`, call `POST /api/v1/accounts/verify-email`, then redirect to `/login`.

## Approval Mode

1. Set `ACCOUNTS_SIGNUP_MODE=admin_approval`.
2. Register and verify a new user.
3. Confirm the verification page redirects to `/waiting-approval`.
4. Approve the user from the admin workbench once feature 086's user-management page is available.

## OAuth Signup

1. Configure Google or GitHub through `/api/v1/admin/oauth/providers/{provider}`.
2. Use `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` to verify that an authorization URL can be generated without persisting OAuth state.
3. Open `/signup` and choose `Sign up with Google` or `Sign up with GitHub`.
4. The backend callback remains `/api/v1/auth/oauth/{provider}/callback`; after backend processing, the frontend redirect target is `/auth/oauth/{provider}/callback`.
5. If the external profile lacks locale, timezone, or display name, the user lands on `/profile-completion`; submitting the form transitions the account to `active`.

## Account Connections

1. Sign in as an existing user.
2. Open `/settings/account/connections`.
3. Link or unlink configured OAuth providers. The backend continues to enforce the last-authentication-method safety rail.

## Known Follow-Ups

- FR-588 route-specific registration rate limiting still needs the per-email 3-per-24h limiter and per-IP 5-per-hour limiter documented in `contracts/rate-limit-policies.md`.
- Verification email locale propagation is delegated to feature 077; see `contracts/email-localization.md`.
- Full J19/E2E coverage is still pending.
