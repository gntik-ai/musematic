# Tasks: UPD-037 — Public Signup Flow, OAuth UI Completion, Email Verification UX

**Feature**: 087-public-signup-flow
**Branch**: `087-public-signup-flow`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Email + password signup on self-service platform → email verification → first login (the canonical self-service onboarding flow; the MVP)
- **US2 (P1)** — Signup on platform with admin approval required → `/waiting-approval` after verification → admin approves → notification → login
- **US3 (P1)** — Signup via Google or GitHub OAuth → dedicated callback page → auto-provisioning → first-time profile completion (when external profile incomplete) → home
- **US4 (P2)** — Existing user links additional OAuth provider from `/settings/account/connections` with safety rail blocking unlink-when-only-method
- **US5 (P3)** — Account recovery via linked OAuth from `/forgot-password` page (anti-enumeration preserved)

Independent-test discipline: every US MUST be runnable in isolation against a kind cluster with the platform Helm chart installed; the new J19 New User Signup journey + the 8 BC-suite tests under `tests/e2e/suites/signup/` are the primary verification surfaces; the constitution Rule 35 anti-enumeration regression test (T067) catches any new path that leaks email-existence information.

**Wave-12 sub-division** (per plan.md §"Wave layout"):
- W12.0 — Setup: T001-T002
- W12A — Backend gap-fillers (Track A): T003-T010
- W12B — UI (Track B): T011-T053
- W12C — E2E (Track C): T054-T072
- W12D — Polish + docs: T073-T080

---

## Phase 1: Setup

- [ ] T001 [W12.0] Verify the existing rate-limit middleware policy for `POST /api/v1/accounts/register` matches FR-588 thresholds (5 attempts/hour per-IP, 3 attempts/24h per-email) per plan.md research R6: read the platform's `RateLimiterService.resolve_anonymous_policy("register")` configuration (or equivalent — feature 086 inventory reports the policies live in PostgreSQL via the `rate_limit_middleware.py` at `apps/control-plane/src/platform/common/middleware/`); document the current settings in `specs/087-public-signup-flow/contracts/rate-limit-policies.md` (NEW file). If thresholds do not match FR-588, T010 adjusts them.
- [ ] T002 [P] [W12.0] Audit the existing `accounts/email.py` localization path per plan.md open question Q2: read `apps/control-plane/src/platform/accounts/email.py` (lines 10-31) and verify whether the verification email template applies the user's `Accept-Language` from the signup request. If localization is delegated to the notification client (feature 077), document the delegation in `specs/087-public-signup-flow/contracts/email-localization.md`; if missing, file the gap back into feature 077's roadmap (NOT in scope for UPD-037).

---

## Phase 2: Foundational Track A — Backend Gap-Fillers (Blocks US3 + US4 + US5)

**Story goal**: Two genuinely-missing backend pieces (verified per inventory) + one rename (4 call sites) + one new admin endpoint. Without these, US3's first-time OAuth profile completion (FR-596) and US4's `/settings/account/connections` link UI (FR-594) cannot work.

### Alembic migration + UserStatus enum extension

- [ ] T003 [W12A] Create Alembic migration `apps/control-plane/migrations/versions/066_pending_profile_completion.py` per plan.md correction §5: `op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'pending_profile_completion'")`. The migration is a tiny ALTER TYPE — no rollback needed (PostgreSQL enums are append-only; leaving the value in place harmlessly is the de-facto rollback). Run `make migrate` to verify the migration applies cleanly on a fresh kind cluster.
- [ ] T004 [W12A] Modify `apps/control-plane/src/platform/accounts/models.py` (lines 15-21) per plan.md correction §5: extend the `UserStatus` StrEnum with `pending_profile_completion = "pending_profile_completion"`. Place the value AFTER `pending_approval` and BEFORE `active` in the declaration order to mirror the lifecycle.
- [ ] T005 [W12A] Modify `apps/control-plane/src/platform/accounts/state_machine.py` (lines 6-30) per plan.md correction §5: add the new transition row `UserStatus.pending_profile_completion: {UserStatus.active}`. The state lives in the OAuth-only path — local-signup users bypass this state entirely.

### `PATCH /api/v1/accounts/me` endpoint

- [ ] T006 [W12A] Modify `apps/control-plane/src/platform/accounts/schemas.py` per plan.md design Track A: add `ProfileUpdateRequest` (Pydantic model with optional `locale: str | None`, `timezone: str | None`, `display_name: str | None` — at least one MUST be set; max-length validators per FR-489 / next-intl locale codes). Add `ProfileUpdateResponse` (returns the updated user record).
- [ ] T007 [W12A] Modify `apps/control-plane/src/platform/accounts/service.py` per plan.md design Track A: add `async def update_profile(self, user_id: UUID, request: ProfileUpdateRequest) -> ProfileUpdateResponse`. The method (a) loads the user; (b) returns 403 with `error_code="profile_completion_not_allowed"` if status is NOT `pending_profile_completion` per plan.md research R2 (defence in depth — the client cannot bypass the check); (c) updates the user's allowlisted fields; (d) transitions status `pending_profile_completion → active` per the state-machine row from T005; (e) emits `user.profile_completed` event on the existing `accounts.events` Kafka topic (feature 016's existing producer is reused — no new topic per plan correction §6's rationale of NOT creating new topics for events that fit existing scopes).
- [ ] T008 [W12A] Modify `apps/control-plane/src/platform/accounts/router.py` (existing endpoints at lines 61-82) per plan.md correction §4: add `@router.patch("/me", response_model=ProfileUpdateResponse, status_code=200)` decorator. The endpoint depends on `Depends(get_current_user)` (the existing auth dependency at `apps/control-plane/src/platform/common/dependencies.py:38-66`); calls `service.update_profile(current_user["sub"], request)` from T007.

### OAuth callback redirect rename (4 call sites)

- [ ] T009 [W12A] Modify `apps/control-plane/src/platform/auth/router_oauth.py` per plan.md correction §3 + design Track A: rename helper `_frontend_login_redirect(request: Request) -> str` at lines 37-41 to `_frontend_oauth_callback_redirect(request: Request, provider: str) -> str` returning `f"{origin}/auth/oauth/{provider}/callback"`. Update ALL FOUR call sites:
  - **Line 126** (error redirect): `url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={error}"`
  - **Line 131** (invalid_oauth_callback error): `url=f"{_frontend_oauth_callback_redirect(request, provider)}?error=invalid_oauth_callback"`
  - **Line 144** (provider error): `url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={exc.code.lower()}"`
  - **Line 154** (success login flow): `url=f"{_frontend_oauth_callback_redirect(request, provider)}#oauth_session={fragment}"`
  Line 149's `_frontend_profile_redirect()` for the `oauth_linked` redirect is **PRESERVED unchanged** — that path goes to `/profile` (feature 086's link-management flow), NOT the signup callback.
- [ ] T010 [W12A] [US3] Update the OAuth provider's auto-provisioning at `apps/control-plane/src/platform/auth/oauth_service.py:354` (`_auto_provision_user()`) per plan.md design Track A: when external profile lacks `locale` OR `timezone` OR `display_name`, set the user's status to `UserStatus.pending_profile_completion` (T004); else preserve the existing logic (`pending_approval` if approval mode is on, `active` otherwise). The check is at the moment of user creation; subsequent OAuth logins for the same user inherit their existing status.

### Admin OAuth provider test-connectivity endpoint (depends on UPD-036)

- [ ] T011 [W12A] Modify `apps/control-plane/src/platform/auth/admin_router.py` (created by feature 086 / UPD-036 T034) per plan.md correction §2: add `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` endpoint per FR-595. The endpoint depends on `Depends(require_admin)` from feature 086's RBAC; calls the existing `oauth_service.get_authorization_url(provider, dry_run=True)` (extending the existing method at `oauth_service.py:200-228` to support a `dry_run` flag that skips state persistence) and returns `{"reachable": bool, "auth_url_returned": bool, "diagnostic": str}`. The test-connectivity is the canonical FR-595 contract.

---

## Phase 3: Foundational Track B — Shared Components + API Methods (Blocks US1 + US3 + US4)

**Story goal**: 4 new shared components + extension to the existing `<OAuthProviderButtons>` + 4 new API methods on `lib/api/auth.ts`. Every page from Phase 4+ uses these.

### API methods

- [ ] T012 [W12B] Modify `apps/web/lib/api/auth.ts` per plan.md correction §7: add 4 new methods after the existing OAuth methods at lines 169-200:
  - `register(payload: { email: string; display_name: string; password: string }): Promise<RegisterResponse>` — calls `POST /api/v1/accounts/register` with `skipAuth=true` (signup is unauthenticated)
  - `verifyEmail(token: string): Promise<VerifyEmailResponse>` — calls `POST /api/v1/accounts/verify-email` with `{token}` body and `skipAuth=true`
  - `resendVerification(email: string): Promise<ResendVerificationResponse>` — calls `POST /api/v1/accounts/resend-verification` with `{email}` body and `skipAuth=true`
  - `updateProfile(payload: { locale?: string; timezone?: string; display_name?: string }): Promise<ProfileUpdateResponse>` — calls `PATCH /api/v1/accounts/me` (authenticated; the existing JWT-injection middleware at `lib/api.ts:70-100` handles the auth header)
  Each method's response type is exported from this file for typed consumption by the new pages.

### Shared components

- [ ] T013 [P] [W12B] Create `apps/web/components/features/auth/PasswordStrengthMeter.tsx` per plan.md design Track B: a visual indicator for FR-587 client-side validation. Inputs: `password: string` prop. Outputs: a coloured bar + textual descriptor (Weak / Fair / Good / Strong) computed via the existing password-strength wordlist + character-class check from feature 017 (the password reset flow uses an equivalent visual — this component is a refactor + reuse). The component is purely visual; the actual server-side validation (FR-587 authoritative) is enforced by the backend `RegisterRequest` schema at `accounts/schemas.py:36-49`.
- [ ] T014 [P] [W12B] Create `apps/web/components/features/auth/ConsentCheckbox.tsx` per FR-510 + plan.md design Track B: a Checkbox component (shadcn/ui primitive) with embedded links to the AI disclosure, terms, and privacy policy. Inputs: `value: boolean`, `onChange: (value: boolean) => void`, `consentVersion: string` prop (the consent text version stored per user on signup per the brownfield input's security note). Renders the localized consent text via next-intl's `t()`.
- [ ] T015 [P] [W12B] Create `apps/web/components/features/auth/CaptchaWidget.tsx` per plan.md correction §10 + research R2: a no-op placeholder when no CAPTCHA provider is configured; reads `process.env.NEXT_PUBLIC_CAPTCHA_PROVIDER` (`hcaptcha` | `turnstile` | undefined). When undefined, the component renders nothing and `onTokenChange(null)` is never called. The actual hCaptcha or Turnstile integration is a follow-up (NOT in scope per spec correction §7).
- [ ] T016 [P] [W12B] Create `apps/web/components/features/auth/SignupForm.tsx` per plan.md design Track B: React Hook Form + Zod schema (email, display_name, password matching the backend's `RegisterRequest` schema at `accounts/schemas.py:36-49` validators); composes `<PasswordStrengthMeter>` (T013), `<ConsentCheckbox>` (T014 — TWO checkboxes: AI disclosure + terms), `<CaptchaWidget>` (T015), and a Submit button. On submit, calls `register(payload)` from T012. On 202 success, navigates to `/verify-email/pending?email={email}`. On 429 rate-limit, displays a clear "You can try again in N minutes" countdown using the `Retry-After` header.
- [ ] T017 [P] [W12B] Create `apps/web/components/features/auth/EmailVerificationStatus.tsx` per FR-590 + plan.md research R8: polls `GET /api/v1/accounts/me` at 5s cadence with backoff to 30s after 60s of no status change. Inputs: `email: string`. Outputs: the current verification status (`pending_verification` / `pending_approval` / `active` / etc.) + a manual "Refresh status" button. When status transitions to `active` OR `pending_approval`, automatically navigates to the next page (US1: `/login`, US2: `/waiting-approval`).
- [ ] T018 [P] [W12B] Create `apps/web/components/features/auth/OAuthCallbackHandler.tsx` per plan.md design Track B canonical sketch: client component (`"use client"`); reads `?error=…` query param AND `#oauth_session=…` fragment from `window.location`; calls `history.replaceState(null, '', window.location.pathname)` to clear fragment per FR-593; uses existing `decodeOAuthSessionFragment()` helper from `lib/api/auth.ts:98-115` (verified per inventory) per plan.md correction §11; uses existing `isOAuthCallbackMfaResponse()` helper per plan.md correction §12. Routes:
  - MFA required → `/login/mfa?session_token={token}`
  - `user.status === "pending_profile_completion"` → `/profile-completion`
  - `user.status === "pending_approval"` → `/waiting-approval`
  - Else → `/home`
  Renders loading / success / error states.
- [ ] T019 [P] [W12B] Create `apps/web/components/features/auth/OAuthLinkList.tsx` per FR-594: renders linked providers with linked-since date + unlink action; the unlink button is **disabled** when `links.length === 1` AND the user has NO local password set per FR-594's safety rail (uses `GET /api/v1/auth/oauth/links` from `lib/api/auth.ts:175` to fetch the list; the user's `has_local_password` is read from the auth store). Disabled-state tooltip: "you must keep at least one authentication method — set a local password or link another provider first" per spec User Story 4 acceptance scenario 4. On link-click, calls `linkOAuthProvider(providerType)` from `lib/api/auth.ts:188`; on unlink-click, calls `unlinkOAuthProvider(providerType)` from `lib/api/auth.ts:196` after a typed-confirmation dialog.

### Existing component extension

- [ ] T020 [W12B] Modify `apps/web/components/features/auth/OAuthProviderButtons.tsx` per plan.md correction §6 + design Track B canonical signature: add a `variant: "login" | "signup"` prop (default `"login"` for backwards compatibility). The button label at line 67 is replaced with `${labelPrefix} ${provider.display_name}` where `labelPrefix = variant === "signup" ? "Sign up with" : "Continue with"`. The existing test file at `OAuthProviderButtons.test.tsx` is extended (T021).
- [ ] T021 [P] [W12B] Modify `apps/web/components/features/auth/OAuthProviderButtons.test.tsx` per plan.md correction §6: add coverage for the new `variant` prop. Two new test cases: (a) `variant="signup"` renders "Sign up with Google" / "Sign up with GitHub"; (b) default (no prop / `variant="login"`) preserves the existing "Continue with Google" / "Continue with GitHub" rendering — backwards-compat assertion.

---

## Phase 4: User Story 1 — Email + Password Self-Service Signup (P1) 🎯 MVP

**Story goal**: New visitor signs up → email verification → first login on a self-service platform in ≤ 3 minutes (excluding email delivery time). The MVP — every other US layers on top.

### Pages

- [ ] T022 [US1] [W12B] Create `apps/web/app/(auth)/signup/page.tsx` per FR-586: server component that checks the platform's `FEATURE_SIGNUP_ENABLED` flag (from feature 086's admin feature-flags). If disabled, renders the redirect to `/signup/disabled`. Else, renders `<SignupForm>` (T016) + `<OAuthProviderButtons variant="signup" />` (T020). The page also checks the auth cookie server-side and redirects to `/home` if the user is already authenticated (per plan.md risk-register row 11). Uses next-intl's `t()` for every string.
- [ ] T023 [US1] [W12B] Create `apps/web/app/(auth)/signup/disabled/page.tsx` per FR-586's last sentence: a clear "Signups are currently disabled" message + administrator contact link, NOT a 404. The administrator contact email is read from the platform settings (`PLATFORM_ADMIN_CONTACT_EMAIL` env var or equivalent feature 086 setting).
- [ ] T024 [US1] [W12B] Modify `apps/web/app/(auth)/login/page.tsx` per FR-586 + spec User Story 1 acceptance scenario 1: add a prominent "Sign up" link below the LoginForm pointing to `/signup`. The link is conditional — hidden when `FEATURE_SIGNUP_ENABLED=false` (matches the `/signup` page's hidden-when-disabled behaviour for consistency). Pass `variant="login"` to the existing `<OAuthProviderButtons />` (T020). PRESERVE the existing fragment-handling logic at lines 92-128 per plan.md risk-register row 2 (backwards compat — no breaking change to in-flight OAuth flows during deploy).
- [ ] T025 [US1] [W12B] Create `apps/web/app/(auth)/verify-email/pending/page.tsx` per FR-590: client component reading `?email={email}` query param. Renders `<EmailVerificationStatus email={email} />` (T017) — the component handles the polling + auto-navigation. Also renders a "Resend verification" button that calls `resendVerification(email)` from T012; the button is rate-limited client-side by tracking the last-click timestamp (matching the FR-588 3/24h per-email server-side limit; the client-side throttle prevents needless 429s).
- [ ] T026 [US1] [W12B] Create `apps/web/app/(auth)/verify-email/page.tsx` per FR-589: client component reading `?token={token}` query param. On mount, calls `verifyEmail(token)` from T012. The 3 token states per spec User Story 1 acceptance scenarios 4-6:
  - **Success** (200): renders "Email verified — redirecting…"; reads the response's `status` field (`active` → redirect to `/login` after 3s with success banner; `pending_approval` → redirect to `/waiting-approval`).
  - **Expired** (400 with `error_code="token_expired"`): renders "Verification link expired" + a resend form (similar to T025 but inline).
  - **Re-used** (200 if backend returns success idempotently — verified via `accounts/service.py:132-174`'s `verify_email` method which does NOT raise on already-verified tokens): treated as success per spec User Story 1 acceptance scenario 6.

### Tests

- [ ] T027 [P] [US1] [W12B] Add Vitest unit test `apps/web/components/features/auth/SignupForm.test.tsx`: verify (a) form rendering with all required fields; (b) Zod validation rejects malformed email + weak password before submit; (c) Submit calls `register()` mutation; (d) 202 response navigates to `/verify-email/pending?email={email}`; (e) 429 response renders the countdown with `Retry-After`-derived seconds.
- [ ] T028 [P] [US1] [W12C] Add E2E test `tests/e2e/suites/signup/test_signup_email_password.py` per spec User Story 1 acceptance scenarios + FR-589: on a kind cluster with `FEATURE_SIGNUP_ENABLED=true` and `FEATURE_SIGNUP_REQUIRES_APPROVAL=false`, navigate to `/login`; click "Sign up" link; verify it navigates to `/signup`; fill the form (email valid RFC 5322, display_name, password ≥ 12 chars + uppercase + lowercase + digit + special, accept consents); submit. Verify (a) `POST /api/v1/accounts/register` returns 202; (b) browser navigates to `/verify-email/pending`; (c) verification email arrives at the test inbox within 60s; (d) clicking the email link navigates to `/verify-email?token=…`; (e) the token is consumed via `POST /api/v1/accounts/verify-email`; (f) the page auto-navigates to `/login` after 3s; (g) login with the registered credentials succeeds; (h) the user lands on `/home`.

---

## Phase 5: User Story 2 — Admin Approval Required (P1)

**Story goal**: Approval-required deployments — post-verification user lands on `/waiting-approval`; admin approves via feature 086's workbench; user receives notification; can then log in.

### Pages

- [ ] T029 [US2] [W12B] Create `apps/web/app/(auth)/waiting-approval/page.tsx` per FR-591: server component reading the user's status from the auth cookie / session. Renders status badge + estimated review time (read from the platform settings `signup_approval_estimated_review_time` — feature 086's admin settings) + administrator contact link. The page is NOT a redirect target for `active` users — server-side redirects to `/home` if the user is `active`. The page subscribes to a WebSocket admin channel for status updates (the existing `accounts.events` topic — when admin approves, the user receives a real-time "approval granted" notification AND the UI auto-navigates to `/login` per spec User Story 2 acceptance scenario 5).
- [ ] T030 [US2] [W12B] Modify `apps/control-plane/src/platform/accounts/service.py` per spec User Story 2 acceptance scenario 2: when a `pending_approval` user attempts to log in, return 403 with `error_code="account_pending_approval"` and a `redirect_to: "/waiting-approval"` field. The login endpoint (feature 014's `auth/router.py`) catches this and forwards the redirect to the client. Verify the existing login flow already handles this case per the existing `state_machine.py` rejection logic; if not, this is a tiny addition.

### Tests

- [ ] T031 [US2] [W12C] Add E2E test `tests/e2e/suites/signup/test_signup_with_approval_required.py` per spec User Story 2 acceptance scenarios: install platform with `FEATURE_SIGNUP_REQUIRES_APPROVAL=true`; sign up + verify email; verify (a) post-verification user lands on `/waiting-approval` (NOT `/login`); (b) attempts to log in are refused with the redirect-to-waiting-approval per T030; (c) admin approval via `/admin/users/{id}` (feature 086 workbench) transitions the user's status to `active`; (d) the user receives an "Approval granted" notification on the configured channel (verifies via the `accounts.events` Kafka topic consumer in the test fixture); (e) login post-approval succeeds; (f) admin REJECTION transitions the user's status to `rejected` (terminal) and the user receives a "Approval rejected" notification.

---

## Phase 6: User Story 3 — Google + GitHub OAuth Signup (P1)

**Story goal**: OAuth signup with domain restriction (Google) + org restriction (GitHub) + dedicated callback page + first-time profile completion when external profile incomplete.

### Pages

- [ ] T032 [US3] [W12B] Create `apps/web/app/(auth)/auth/oauth/[provider]/callback/page.tsx` per FR-593 + plan.md correction §2: client component renders `<OAuthCallbackHandler provider={params.provider} />` (T018). The page accepts the literal `auth/` URL segment per plan.md correction §2 (the parentheses-stripped `(auth)` route group means the file at `(auth)/auth/oauth/[provider]/callback/page.tsx` resolves to URL `/auth/oauth/{provider}/callback`).
- [ ] T033 [US3] [W12B] Create `apps/web/app/(auth)/auth/oauth/error/page.tsx` per FR-449 + FR-450: server component reading `?reason={reason}` query param. Renders different error UI per reason: `domain_not_permitted` (Google), `org_not_permitted` (GitHub), `expired_state`, `provider_error`, `network_failure`, `user_denied_access` (the spec edge-case for `error=access_denied`). Each variant has a clear administrator-contact CTA AND a "Try again" button that redirects to `/signup` per plan.md research R7.
- [ ] T034 [US3] [W12B] Create `apps/web/app/(auth)/profile-completion/page.tsx` per FR-596: server component checks the user's status; redirects to `/home` if user is NOT `pending_profile_completion` per plan.md research R2 (defence in depth). Renders the profile-completion form: locale dropdown (defaults to `navigator.language`), timezone dropdown (defaults to `Intl.DateTimeFormat().resolvedOptions().timeZone`), display_name input (defaults to OAuth provider's `display_name` or email local-part) per plan.md research R9. On submit, calls `updateProfile()` from T012 — the backend transitions status to `active` and the page navigates to `/home`. The form has NO Cancel button per plan.md risk-register row 10 — the user MUST submit to proceed.

### Tests

- [ ] T035 [P] [US3] [W12C] Add E2E test `tests/e2e/suites/signup/test_signup_oauth_google.py` per spec User Story 3 acceptance scenarios 1-6: on a kind cluster with Google OAuth enabled (using the platform's existing `mockOAuth` config from feature 014's E2E setup) AND domain restriction `@example.com`, navigate to `/signup`; click "Sign up with Google"; complete the mock-Google flow with `@example.com` email; verify (a) browser redirects to `/auth/oauth/google/callback`; (b) `<OAuthCallbackHandler>` clears the `#oauth_session=…` fragment from history; (c) if the mock profile lacks locale/timezone, the redirect goes to `/profile-completion`; (d) submitting the form transitions user to `active` and redirects to `/home`; (e) the audit chain has a `signup_source=oauth_google` entry; (f) repeat with `@unauthorized.com` — verify redirect to `/auth/oauth/error?reason=domain_not_permitted` with the clear error message.
- [ ] T036 [P] [US3] [W12C] Add E2E test `tests/e2e/suites/signup/test_signup_oauth_github.py` per spec User Story 3 acceptance scenario 7: same pattern as T035 but for GitHub with org restriction. Verify (a) browser redirects to `/auth/oauth/github/callback`; (b) GitHub's organisation restriction is honoured; (c) audit chain records `signup_source=oauth_github`.
- [ ] T037 [P] [US3] [W12C] Add E2E test for the OAuth-callback fragment-clearance behaviour per FR-593 + SC-010: after the OAuth flow, verify `window.history.length` does NOT contain the fragment-decorated URL (the `history.replaceState` call in `<OAuthCallbackHandler>` cleared it). Test using Playwright's `page.evaluate(() => history.state)` to inspect the history.

---

## Phase 7: User Story 4 — OAuth Link Management (P2)

**Story goal**: Existing user links additional OAuth provider from `/settings/account/connections`; safety rail blocks unlink-when-only-method.

### Pages

- [ ] T038 [US4] [W12B] Create `apps/web/app/(main)/settings/account/connections/page.tsx` per FR-594 + plan.md correction §8: server component (uses `(main)` layout, NOT `(auth)`); requires authentication via the existing auth-cookie check. Renders `<OAuthLinkList />` (T019). The page is a sibling sub-route of the existing `(main)/settings/page.tsx`; it does NOT modify the existing settings layout.

### Tests

- [ ] T039 [US4] [W12C] Add E2E test `tests/e2e/suites/signup/test_oauth_link_management.py` per spec User Story 4 acceptance scenarios: as an authenticated user with a local password and Google linked, navigate to `/settings/account/connections`; verify (a) the page lists Google with linked-since date AND a "Link GitHub" button; (b) clicking "Link GitHub" initiates the OAuth flow with link-intent state token; (c) on callback, the user is redirected to `/profile?message=oauth_linked` (the line-149 `_frontend_profile_redirect` per plan correction §3 — preserved unchanged); (d) returning to `/settings/account/connections` shows GitHub in the list; (e) attempt to unlink Google when GitHub + local password remain → succeeds; (f) attempt to unlink the only auth method → REJECTED with the clear error per FR-594; (g) attempt to link a Google identity already linked to another user → REJECTED.

---

## Phase 8: User Story 5 — Account Recovery via Linked OAuth (P3)

**Story goal**: User has Google linked + forgot password; `/forgot-password` surfaces "Sign in with Google to recover access" CTA. Anti-enumeration preserved.

### Page modification

- [ ] T040 [US5] [W12B] Modify `apps/web/app/(auth)/forgot-password/page.tsx` per FR-598 + plan.md research R5: extend the existing forgot-password page with the OAuth-recovery CTA. The CTA is rendered ONLY when the backend's `GET /api/v1/auth/oauth/links?email={email}` returns a non-empty list AND the response shape is byte-identical for unregistered emails (anti-enumeration preserved per Constitution Rule 35 — verified by T067). On CTA click, the OAuth flow initiates with a recovery-intent state token; on callback completion, the user is logged in and prompted to optionally set a new local password (dismissible — NOT required per spec User Story 5 acceptance scenario 3). The audit chain records `password_reset_via_oauth_recovery` per spec User Story 5 acceptance scenario 4.

### Tests

- [ ] T041 [US5] [W12C] Add E2E test `tests/e2e/suites/signup/test_oauth_recovery.py` per spec User Story 5 acceptance scenarios: seed user U with Google linked AND a local password; navigate to `/login`; click "Forgot password?"; on `/forgot-password`, enter U's email; verify (a) the OAuth recovery CTA renders; (b) clicking Google completes OAuth; (c) the user is logged in; (d) a one-time prompt offers "Set a new local password" — dismissible; (e) audit chain records the recovery; (f) seed user V with NO OAuth linked; enter V's email → verify the CTA does NOT render (anti-enumeration: the absence of the CTA is the only signal).

---

## Phase 9: i18n — 7 Locale Catalogs

**Story goal**: All new admin strings translated into the 7 supported locales per plan.md correction §1.

- [ ] T042 [P] [W12B] Add the new auth strings to `apps/web/messages/en.json` (currently empty `{}` per the inventory). Strings to add: signup form labels + validation messages, verify-email pending + token states, waiting-approval status + estimated review time + admin contact, OAuth callback loading/success/error + per-error-reason messages (`domain_not_permitted`, `org_not_permitted`, `expired_state`, etc.), profile-completion form labels + defaults, settings-connections list + unlink-disabled tooltip, forgot-password OAuth-recovery CTA. Group keys under top-level `auth.signup.*`, `auth.verify.*`, `auth.oauth.*`, `auth.connections.*` namespaces.
- [ ] T043 [P] [W12B] Add the same string keys to `apps/web/messages/es.json`, `de.json`, `fr.json`, `it.json`, `zh-CN.json`, AND `ja.json` per plan.md correction §1 (7 locales on disk). Coordinate with translation vendor for accurate translations; ship with English-fallback if translations slip per plan.md risk-register row 5 (the existing CI translation-drift check from feature 083 catches missing keys).

---

## Phase 10: E2E Coverage — J19 Journey + Extensions

**Story goal**: New J19 New User Signup journey covering all 5 user stories; extensions to J02 Creator + J03 Consumer journeys per FR-599.

### J19 New journey

- [ ] T044 [W12C] Author `tests/e2e/journeys/test_j19_new_user_signup.py` per FR-599 + plan.md design Track C: the J19 journey covers all 5 user stories end-to-end:
  1. **US1**: visitor → /signup (email+password) → /verify-email/pending → email arrives → /verify-email?token → /login → /home (≥ 8 assertion points)
  2. **US2**: same but with `FEATURE_SIGNUP_REQUIRES_APPROVAL=true` → /waiting-approval → admin approves → notification received → login (≥ 5 assertion points)
  3. **US3 Google**: /signup → "Sign up with Google" → mock-Google flow → /auth/oauth/google/callback → /profile-completion → submit → /home (≥ 6 assertion points)
  4. **US3 GitHub**: same for GitHub with org restriction (≥ 4 assertion points)
  5. **US4**: authenticated user → /settings/account/connections → "Link GitHub" → callback → returns to settings (≥ 4 assertion points)
  6. **US5**: forgot-password with OAuth-recovery CTA → completes OAuth → optional password set (≥ 3 assertion points)
  Total: ≥ 30 assertion points spanning the whole signup surface. Uses Playwright's `axe-playwright-python` per FR-526 to scan every visited new page; verifies zero AA violations per the existing CI gate from feature 085.

### J02 + J03 extensions

- [ ] T045 [W12C] Modify `tests/e2e/journeys/test_j02_creator_to_publication.py` per FR-599: extend the existing journey (already extended in features 085 + 086) with an OPTIONAL OAuth-signup pre-step. When the test parameter `signup_method=oauth_google`, the creator's account is provisioned via Google OAuth instead of email+password; the rest of the journey proceeds unchanged. +3 assertion points.
- [ ] T046 [W12C] Modify `tests/e2e/journeys/test_j03_consumer_discovery_execution.py` per FR-599: same pattern as T045 — optional OAuth-signup pre-step with `signup_method=oauth_github`. +3 assertion points.

---

## Phase 11: Constitutional + CI Gates

**Story goal**: Anti-enumeration regression test + rate-limit verification per FR-588 + verify the `<OAuthProviderButtons>` extension preserves backwards compatibility.

- [ ] T047 [P] [W12C] Add E2E test `tests/e2e/suites/signup/test_email_enumeration_resistance.py` per Constitution Rule 35 + plan.md risk-register row 3: comprehensive negative test verifying byte-equivalent responses for new vs existing emails on (a) `POST /api/v1/accounts/register`; (b) `POST /api/v1/accounts/verify-email` with invalid vs expired tokens; (c) `POST /api/v1/accounts/resend-verification`; (d) `GET /api/v1/auth/oauth/links?email={email}` (the empty-list-vs-empty-list test for User Story 5 anti-enumeration). For each: register user A with email `existing@test.com`; attempt the operation with both `existing@test.com` and `new@test.com`; assert the response bodies are byte-equivalent (after stripping correlation IDs and timestamps). The test fails the build on any divergence.
- [ ] T048 [P] [W12C] Add E2E test `tests/e2e/suites/signup/test_rate_limiting.py` per FR-588 + plan.md research R6: send 6 register requests from the same IP within 1 hour; verify the 6th returns 429 with `Retry-After` header. Send 4 register requests with the same email within 24h; verify the 4th returns 429. Verify the rate-limit policy thresholds match FR-588 (5/hour per-IP, 3/24h per-email) — if the policy was adjusted in T001, this test verifies the configuration end-to-end.

---

## Phase 12: Polish + Documentation

- [ ] T049 [P] [W12D] Author `specs/087-public-signup-flow/quickstart.md` — operator's "first 30 minutes" guide: walks through enabling self-signup via the admin workbench, the verification flow, switching to approval mode, configuring OAuth providers, end-to-end signup test. Reuses the speckit `quickstart.md` convention from prior features.
- [ ] T050 [P] [W12D] Update `apps/web/app/(auth)/login/page.tsx` documentation comments to reference the new `/signup` flow. Add a top-of-file comment block noting the OAuth fragment-handling logic at lines 92-128 is **legacy backwards-compat** post-UPD-037 (the new flow uses `/auth/oauth/{provider}/callback`); after one release, consider deprecating per plan.md risk-register row 2.
- [ ] T051 [P] [W12D] Update the OAuth provider configuration documentation (under `deploy/helm/platform/README.md` or equivalent) per plan.md risk-register row 1: document that the BACKEND callback URL `/api/v1/auth/oauth/{provider}/callback` is unchanged; only the FRONTEND redirect target after the backend processes the callback changes. NO Google/GitHub OAuth provider-console reconfiguration is needed when deploying UPD-037.
- [ ] T052 [P] [W12D] Update `CLAUDE.md` (project root) per the speckit convention: append "Active Technologies" section with feature 087's stack identifiers; append "Recent Changes" with a 1-2 line summary of UPD-037's contributions; record the 12 brownfield-input corrections from plan.md correction list as future-planner reference. Keep the file under the 200-line rule.
- [ ] T053 [W12D] Cross-feature coordination follow-up: confirm with feature 086's owner that `/admin/oauth-providers` page exists by the time UPD-037 lands (T011 depends on it); confirm with feature 077's owner that the verification email + approval-granted/rejected notification routing works via the existing `accounts.events` Kafka topic. Record the sign-offs in this task's commit message.
- [ ] T054 [W12D] Run the full E2E suite end-to-end on the kind cluster: `make e2e-up && make e2e-test && make e2e-journeys && make e2e-down`; verify all 8 new BC-suite tests pass (T028, T031, T035, T036, T037, T039, T041, T047, T048) AND J19 + extended J02 + J03 pass; verify zero axe-core AA violations per FR-526; verify the rate-limit test (T048) reports the correct thresholds; verify the anti-enumeration test (T047) reports byte-equivalent responses.

---

## Task Count Summary

| Phase | Range | Count | Wave | Parallelizable |
|---|---|---|---|---|
| Phase 1 — Setup | T001-T002 | 2 | W12.0 | partially |
| Phase 2 — Track A Backend Gap-Fillers | T003-T011 | 9 | W12A | mostly sequential |
| Phase 3 — Track B Foundational (components + API) | T012-T021 | 10 | W12B.1 | mostly parallel |
| Phase 4 — US1 P1 MVP (email+password signup) | T022-T028 | 7 | W12B.2 + W12C.1 | partially |
| Phase 5 — US2 P1 (admin approval) | T029-T031 | 3 | W12B.3 + W12C.2 | partially |
| Phase 6 — US3 P1 (Google + GitHub OAuth signup) | T032-T037 | 6 | W12B.4 + W12C.3 | mostly parallel |
| Phase 7 — US4 P2 (OAuth link management) | T038-T039 | 2 | W12B.5 + W12C.4 | partially |
| Phase 8 — US5 P3 (OAuth recovery) | T040-T041 | 2 | W12B.6 + W12C.5 | partially |
| Phase 9 — i18n (7 locales) | T042-T043 | 2 | W12B.7 | yes (per-locale parallel) |
| Phase 10 — E2E J19 + extensions | T044-T046 | 3 | W12C.6 | partially |
| Phase 11 — Constitutional + CI gates | T047-T048 | 2 | W12C.7 | yes |
| Phase 12 — Polish + docs | T049-T054 | 6 | W12D | mostly yes |
| **Total** | | **54** | | |

## MVP Definition

**The MVP is US1 (Phase 4 — email+password signup → email verification → first login on a self-service platform).** Without US1, the platform has no user-acquisition path — the backend has the API but the UI has no entry point. After US1 lands, US2 (admin approval) and US3 (OAuth signup) are the next P1 must-haves; US4 (link management) and US5 (OAuth recovery) are quality-of-life additions that depend on the core flows being in place.

## Dependency Notes

- **T001-T002 (Setup) → all phases**: rate-limit policy verification must happen before T048's rate-limit E2E test.
- **T003-T010 (Track A) → US3 Phase 6**: `pending_profile_completion` enum + `PATCH /me` + OAuth callback redirect rename are upstream of every OAuth-callback-page test.
- **T011 (admin test-connectivity) → UPD-036 / feature 086 admin workbench**: the `/admin/oauth-providers` page must exist; UPD-037 lands AFTER UPD-036.
- **T012 (API methods) → all UI pages**: every new page that submits a form depends on `lib/api/auth.ts` having the 4 new methods.
- **T013-T021 (shared components) → all UI pages**: every page consumes at least one shared component.
- **T020 (`<OAuthProviderButtons>` extension) → T022 + T024 + T038**: signup, login, and connections pages all use the extended component.
- **T044 (J19 journey) ← T028 + T031 + T035 + T036 + T039 + T041**: J19 reuses the BC-suite test scenarios as its journey-step assertions.

## Constitutional Audit Matrix

| Constitution rule / FR | Verified by | Phase |
|---|---|---|
| Rule 35 — email enumeration prohibited | T047 anti-enumeration regression test | Phase 11 |
| Rule 45 — every backend capability has a UI surface | T022 + T025 + T026 + T029 + T032 + T038 + T040 (10 new pages backing the existing endpoints) | Phase 4-8 |
| FR-015 — self-signup admin toggle | T022 server-side check on `FEATURE_SIGNUP_ENABLED` + T023 disabled page | Phase 4 |
| FR-016 — admin approval | T029 `/waiting-approval` page + T030 service-layer 403 with redirect_to | Phase 5 |
| FR-020 — email verification | T026 token-validation page + the existing `accounts/service.py:132-174` `verify_email` method | Phase 4 |
| FR-021 — user statuses | T003-T005 add `pending_profile_completion` enum + state-machine row | Phase 2 |
| FR-448 + FR-449 + FR-450 — OAuth framework + Google + GitHub | T009 redirect rename + T010 auto-provision logic + T032 callback page + T035 + T036 E2E tests | Phase 2 + 6 |
| FR-510 — AI interaction disclosure consent | T014 `<ConsentCheckbox>` shipped on signup form | Phase 3 |
| FR-583 — structured error responses | T009 + T030 + T034 all return `{error_code, message, suggested_action, correlation_id}` | All phases |
| FR-586 through FR-599 | Every task cites its FR | All phases |
| FR-526 — axe-core CI gate | T044 J19 axe scan + T028 / T035 / T036 / T039 / T041 BC-suite scans | Phase 4-10 |
| Wave 12 capstone post-UPD-036 | All tasks tagged W12.0 / W12A / W12B / W12C / W12D | All |
