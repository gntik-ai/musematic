# Planning Input — UPD-037 Public Signup Flow, OAuth UI Completion, Email Verification UX

> **Captured verbatim from the user's `/speckit.specify` invocation on 2026-04-27.** This file is the immutable record of the brownfield context that authored spec.md. Edits MUST NOT be made here; if a correction is needed, edit spec.md and append a note to the corrections list at the top of this file.

## Corrections Applied During Spec Authoring

1. **Existing OAuth callback redirect target.** The brownfield input describes the current OAuth backend as redirecting to `/login` with a session fragment ("functional but not ideal"). On-disk verification confirms `auth/router_oauth.py:154` does redirect to `_frontend_login_redirect(request)` with `#oauth_session={fragment}`. Spec resolves with a rename of the helper to `_frontend_oauth_callback_redirect(provider)` returning `/auth/oauth/{provider}/callback` per FR-593; the link-management `oauth_linked` redirect at line 149 is preserved (it goes to the user profile, NOT the signup callback).
2. **`(auth)/auth/oauth/...` URL nesting.** The brownfield input layout places the callback page inside the `(auth)` route group. The literal `auth/` segment becomes part of the URL because `(auth)` is parentheses-stripped — the file at `apps/web/app/(auth)/auth/oauth/[provider]/callback/page.tsx` resolves to URL `/auth/oauth/{provider}/callback`.
3. **`/settings/account/connections` location.** The brownfield input places this page under `(main)/settings/account/connections/`. The on-disk `(main)/settings/` has no `account/` subdirectory yet; UPD-037 creates it.
4. **Backend gap-fillers.** The brownfield input lists three potential backend gaps; the plan phase verifies which are missing and adds only those.
5. **`pending_profile_completion` status is NEW.** The brownfield input introduces this state; the on-disk `accounts/state_machine.py` does not have it; UPD-037 adds it via Alembic migration.
6. **Signup-rate-limit specifics.** FR-588 specifies 5/hour per-IP and 3/24h per-email; the brownfield references "rate limiting per FR-588" — spec adopts the FR-588 thresholds verbatim.
7. **Optional CAPTCHA toggle.** FR-588 mentions hCaptcha or Turnstile as admin-activatable; the brownfield does not require CAPTCHA in the MVP. Spec ships a `<CaptchaWidget>` no-op placeholder.
8. **First-time OAuth profile completion endpoint.** Brownfield proposes `PATCH /api/v1/accounts/me`; spec adds this only if it does not already exist (plan-phase verification).
9. **Email verification — GET vs POST.** The clickable link in the email cannot trigger a POST; the user-clicks-link path goes through the frontend `/verify-email?token=…` page first, which then calls `POST /api/v1/accounts/verify-email`.
10. **`<OAuthProviderButtons>` extension.** Existing component at `apps/web/components/features/auth/OAuthProviderButtons.tsx` is REUSED; UPD-037 adds a `context: "login" | "signup"` prop.

---

# UPD-037 — Public Signup Flow, OAuth UI Completion, Email Verification UX

## Brownfield Context

**Current state (verified in repo):**
- Backend `POST /api/v1/accounts/register`, `POST /api/v1/accounts/verify-email`, `POST /api/v1/accounts/resend-verification` endpoints **already exist** and are wired into `main.py`.
- OAuth backend (`auth/services/oauth_providers/github.py` and `google.py`, `oauth_service.py`, `router_oauth.py`) is fully implemented: authorize endpoint, callback endpoint with frontend redirect, state validation, PKCE for Google, account linking logic.
- UI has `/login`, `/forgot-password`, `/reset-password`, `/reset-password/[token]` pages, and an `OAuthProviderButtons` component used in the login page.
- API client (`lib/api/auth.ts`) has methods for OAuth authorization, linking, unlinking, admin provider CRUD.

**Gaps:**
1. **No signup page** exists in the UI (`/signup` is 404). The backend endpoint has no frontend counterpart.
2. **No email verification UX** — user completes signup via API but there is no `/verify-email?token=…` page, no `/verify-email/pending` status page, no resend flow.
3. **No admin approval waiting page** — when FR-016 is enabled, users have nowhere to land.
4. **No dedicated OAuth callback page** — current flow redirects back to `/login` with a session fragment. This is functional but not ideal for UX (mixed login/callback semantics, fragmentary error handling).
5. **No OAuth link management page** in user settings — API methods exist, but the UI is missing.
6. **Admin OAuth configuration UI** is partially covered by UPD-036's `/admin/oauth-providers` page but needs clearer spec alignment with multi-provider support.
7. **No signup via OAuth** — a user can log in with OAuth if already provisioned, but the signup entry point only shows email/password.

**Extends:**
- FR-015 (Self-Signup), FR-016 (Admin Approval), FR-017 (User Invitation), FR-020 (Email Verification), FR-021 (User Statuses).
- FR-448–452 (OAuth framework + Google + GitHub).
- UPD-020 (OAuth feature in the pass, already implemented for backend/UI integration).
- UPD-030 (Accessibility + i18n — signup pages must comply).
- UPD-036 (Admin workbench — admin OAuth provider page lives there).

**FRs:** FR-586 through FR-599 (new section 110).

---

## Summary

UPD-037 closes the gap between a solid backend signup + OAuth foundation and a UI that only exposes login. It adds:
- `/signup` page with email+password signup, password strength meter, consent checkboxes, rate limiting, CAPTCHA option.
- Signup OAuth entry with `/signup?via=google` and `/signup?via=github` paths.
- `/verify-email/pending` post-signup status page.
- `/verify-email?token=…` token-handling page with success and error states.
- `/waiting-approval` page for FR-016 flow.
- `/auth/oauth/{provider}/callback` dedicated callback page replacing the current login-redirect pattern.
- `/settings/account/connections` OAuth link management page.
- OAuth brand-compliant button styling on login AND signup.
- First-time OAuth profile completion form.
- Comprehensive E2E coverage including a new **J19 New User Signup journey**.

---

## User Scenarios

### User Story 1 — Email+password signup on self-service platform (Priority: P1)

An anonymous visitor wants to try the platform. Self-signup is enabled, email verification is required, admin approval is NOT required.

**Independent Test:** Navigate to `/signup`, fill form, submit. Verify email arrives, click link, land on login page with success banner, log in successfully.

**Acceptance:**
1. `/signup` is reachable from the login page.
2. Form validates email format, password strength (client-side), terms acceptance.
3. Submitting triggers `POST /api/v1/accounts/register`.
4. UI redirects to `/verify-email/pending` showing the email address used and a resend button.
5. Verification email arrives within 60s with a localized body.
6. Clicking the link loads `/verify-email?token=…` which validates and transitions status.
7. Page shows success and auto-redirects to `/login` after 3s.
8. Log in succeeds; user lands on the platform home.

### User Story 2 — Signup on platform with admin approval (Priority: P1)

Admin approval is enabled (FR-016). The signup flow must not grant immediate access.

**Independent Test:** Sign up, verify email, land on `/waiting-approval`. Admin approves via admin workbench. User receives notification and can now log in.

**Acceptance:**
1. Post-verification, user lands on `/waiting-approval` (NOT `/login`).
2. Page shows status, estimated review time, contact administrator link.
3. Attempting to log in before approval returns a clear error and routes back to `/waiting-approval`.
4. After admin approves, user receives notification via configured channel.
5. User can now log in; approval state reflected in audit chain.

### User Story 3 — Signup via Google OAuth (Priority: P1)

A user clicks "Sign up with Google" on the signup page. Their Google Workspace domain is on the allowed list.

**Independent Test:** Click Google button, complete Google flow in popup/redirect, land on callback page, profile is auto-provisioned, first-time profile completion form appears if required.

**Acceptance:**
1. `/signup` shows OAuth buttons when providers are enabled.
2. Clicking Google redirects to Google authorize URL with correct scope and state.
3. Google callback returns to `/auth/oauth/google/callback`.
4. Callback page shows loading state, receives session fragment, establishes session.
5. If domain restriction fails, user sees clear error page with administrator contact.
6. If user is first-time and profile is incomplete (locale/timezone), profile completion form appears.
7. After completion, user proceeds to platform home.
8. Audit entry records `signup_source=oauth_google`.

### User Story 4 — User links additional OAuth provider from settings (Priority: P2)

An existing local-password user wants to add GitHub OAuth for convenience.

**Independent Test:** Navigate to `/settings/account/connections`, click "Link GitHub", complete OAuth flow, see GitHub listed as linked provider.

**Acceptance:**
1. Connections page lists currently linked providers with linked-since date.
2. Clicking "Link GitHub" initiates OAuth with a link-intent state token.
3. Callback completes and returns to connections page.
4. New provider appears in list.
5. Attempt to link a provider already linked to another account returns a clear error (cannot link one Google/GitHub identity to multiple platform users).
6. Unlink action is disabled if the provider is the only authentication method (no local password).

### User Story 5 — User recovers account via linked OAuth (Priority: P3)

User forgot their password and has Google linked.

**Independent Test:** Click "Forgot password", see "Sign in with Google" as alternative. Click, complete OAuth, land on account, set new password.

**Acceptance:**
1. Forgot-password page shows OAuth recovery option when any provider is linked.
2. Completing OAuth proves account ownership.
3. User is prompted to set a new local password (not required; OAuth-only login remains valid).
4. Audit entry records password reset via OAuth recovery path.

---

### Edge Cases

- **Self-signup disabled via setting (FR-015)**: `/signup` renders a clear "Signups are currently disabled" message with administrator contact link, NOT a 404.
- **Expired verification token**: `/verify-email?token=…` shows clear error and surfaces a resend form.
- **Already-verified token (double-click)**: page treats it as success (idempotent).
- **OAuth callback with expired state**: callback page shows error, offers retry via signup/login.
- **OAuth callback with an account already linked to a different local user**: clear error prevents account takeover.
- **Domain-restricted OAuth signup from outside allowed domains**: user sees clear "Your domain is not permitted" message.
- **User attempts signup with an email already registered**: server returns neutral "If this is a new email, you will receive a verification" response to prevent email enumeration; if user owns the email they can use forgot-password flow.
- **Signup rate limit exceeded**: 429 response with retry-after; UI surfaces a clear countdown.
- **Network failure during OAuth callback**: callback page offers retry.

---

## UI Routes (Next.js)

```
apps/web/app/(auth)/
├── layout.tsx                              # Existing auth shell
├── login/page.tsx                          # EXTENDED: prominent signup link, improved OAuth button layout
├── signup/
│   ├── page.tsx                            # NEW: email+password form, OAuth buttons, terms, consent
│   └── disabled/page.tsx                   # Shown when self-signup disabled
├── verify-email/
│   ├── pending/page.tsx                    # Post-signup status, resend action
│   └── page.tsx                            # Token validation (reads ?token=…)
├── waiting-approval/page.tsx               # When admin approval required
├── auth/oauth/[provider]/callback/page.tsx # NEW: dedicated OAuth callback page
├── auth/oauth/error/page.tsx               # OAuth error states (domain restriction, provider error)
├── profile-completion/page.tsx             # First-time OAuth users with incomplete profile
├── forgot-password/page.tsx                # EXTENDED: OAuth recovery option when available
├── reset-password/[token]/page.tsx         # Existing
```

```
apps/web/app/(main)/settings/account/
├── connections/page.tsx                    # NEW: OAuth link management
```

```
apps/web/app/(admin)/oauth-providers/
├── page.tsx                                # From UPD-036 — extended here
└── [provider]/page.tsx                     # Provider detail with test-connectivity
```

## Backend Changes

All core endpoints exist; this feature exposes them via UI and adds minor gaps:
- Confirm `GET /api/v1/accounts/verify-email/{token}` returns a structured response (not a redirect) so the frontend page controls UX.
- Add `GET /api/v1/auth/oauth/link-status` returning the list of providers linked to the current user (already partly exists via `/api/v1/auth/oauth/links`).
- Add a `profile-completion` endpoint if not present: `PATCH /api/v1/accounts/me` with allowlisted fields `locale`, `timezone`, `display_name` accepting changes only when the user's status is `pending_profile_completion`.

## Shared UI Components

- `<SignupForm>` — email+password+name+terms checkbox + password strength meter
- `<PasswordStrengthMeter>` — reused between signup and password reset
- `<OAuthProviderButtons>` — EXISTING, extended with "Continue with …" / "Sign up with …" labels based on context
- `<EmailVerificationStatus>` — polls `/api/v1/accounts/me` to update status in real time
- `<OAuthCallbackHandler>` — manages callback lifecycle: loading → success handoff OR error display
- `<OAuthLinkList>` — renders linked providers with unlink actions and safety rails
- `<ConsentCheckbox>` — AI disclosure + terms + privacy policy links

## Acceptance Criteria

- [ ] `/signup` page renders, accepts valid input, submits to backend
- [ ] Password policy enforced both client and server side
- [ ] Rate limiting per FR-588 verified with synthetic tests
- [ ] `/verify-email/pending` shows state and resend action
- [ ] `/verify-email?token=…` handles success, expired, and re-used token states
- [ ] `/waiting-approval` shows correct state when admin approval enabled
- [ ] `/signup` shows OAuth buttons when providers are enabled
- [ ] Google OAuth signup provisions account and respects domain restrictions
- [ ] GitHub OAuth signup provisions account and respects org restrictions
- [ ] `/auth/oauth/{provider}/callback` handles loading, success, and error states
- [ ] `/settings/account/connections` allows linking and unlinking providers safely
- [ ] First-time OAuth users with incomplete profile see completion form
- [ ] Forgot-password flow offers OAuth recovery when provider is linked
- [ ] All new pages are WCAG AA compliant (axe-core zero AA violations)
- [ ] All new pages fully localized into 6 languages
- [ ] J19 New User Signup journey test passes end-to-end on kind
- [ ] J02 Creator journey extended to cover OAuth signup path
- [ ] Admin OAuth provider page (UPD-036 `/admin/oauth-providers`) has test-connectivity action
