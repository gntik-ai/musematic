# Feature Specification: Public Signup Flow, OAuth UI Completion, Email Verification UX

**Feature Branch**: `087-public-signup-flow`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "Close the gap between a complete backend signup + OAuth foundation and a UI that today only exposes login. Add a `/signup` page (email+password + OAuth entry points), `/verify-email/pending` post-signup status page, `/verify-email?token=…` token-handling page, `/waiting-approval` page for the FR-016 approval-required flow, dedicated `/auth/oauth/{provider}/callback` page (replacing the current login-redirect-with-fragment pattern), `/settings/account/connections` OAuth link management page, first-time OAuth profile completion form, and a new J19 New User Signup E2E journey. The backend's `/api/v1/accounts/register`, `/verify-email`, `/resend-verification` endpoints + the OAuth `oauth_providers/{github,google}.py` services already exist; this feature is UI + minor backend gap-fillers + E2E coverage."

> **Constitutional anchor:** This feature IS the constitutionally-named **UPD-037** ("Public Signup + OAuth UI") declared in Constitution line 7 (audit-pass roster). Constitutional rules and FRs that bear on this feature: FR-015 (self-signup admin toggle), FR-016 (admin approval), FR-017 (user invitation), FR-020 (email verification), FR-021 (user statuses — `pending_verification` → `pending_approval` → `active` per `accounts/state_machine.py`), FR-448 (OAuth framework), FR-449 (Google), FR-450 (GitHub), FR-510 (AI interaction disclosure consent), FR-488 (WCAG AA — every new page passes axe-core), FR-489 (i18n — every new page across the 6 supported locales), FR-490 (theming — light/dark/system/high-contrast inherited from feature 083), FR-526 (axe-core CI gate — extended to cover the new pages per FR-599), FR-573 (admin session security inherited from feature 086 — relevant to the admin OAuth provider page UPD-037 extends), and FR-586 through FR-599 (Section 110 of the FR document, this feature's primary contract).

> **Scope discipline:** This feature builds on, but does NOT re-implement, the artifacts owned by:
> - **Feature 014 (Auth) + Feature 016 (Accounts)** — `/api/v1/accounts/register`, `/api/v1/accounts/verify-email`, `/api/v1/accounts/resend-verification` endpoints and the `accounts/state_machine.py` state transitions ALREADY exist; UPD-037 calls them from the new UI pages and adds **two minor backend gap-fillers** only (see correction §4).
> - **OAuth backend** (`apps/control-plane/src/platform/auth/services/oauth_providers/{github,google}.py`, `auth/oauth_service.py`, `auth/router_oauth.py`) — the authorize endpoint, callback endpoint with PKCE for Google, state validation, and account-linking logic ALREADY exist; UPD-037 changes the **callback redirect target** from the current `_frontend_login_redirect(request)#oauth_session=…` fragment-on-login pattern (`auth/router_oauth.py:154`) to a dedicated `/auth/oauth/{provider}/callback` page, AND extends the existing `_frontend_*_redirect` helpers to make the target path configurable.
> - **Feature 015 (Next.js scaffold) + Feature 017 (Login UI)** — the existing `(auth)` route group at `apps/web/app/(auth)/` with `login/`, `forgot-password/`, `reset-password/`, `reset-password/[token]/` pages stays unchanged; UPD-037 adds new sibling routes inside `(auth)/` and a single new route under `(main)/settings/account/`.
> - **Existing `<OAuthProviderButtons>`** at `apps/web/components/features/auth/OAuthProviderButtons.tsx` — UPD-037 EXTENDS this component with a `context` prop (`"login" | "signup"`) so the same component renders "Sign up with Google" on `/signup` and "Continue with Google" on `/login` per FR-597 brand-guideline phrasing; the component stays in its current file.
> - **Feature 083 (Accessibility & i18n / `localization/`)** — UPD-037 inherits the next-intl + axe-core CI gate; every new admin string passes through `t()`; the workbench inherits the `localization/` BC's translation drift CI check.
> - **Feature 086 (Admin Workbench)** — the `/admin/oauth-providers` page exists per UPD-036's FR-548 + plan correction §4 (T034 `auth/admin_router.py`); UPD-037 EXTENDS the page with a **test-connectivity action** per FR-595 (the brownfield's "FR-595 OAuth Admin UI Configuration"), adding a `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` endpoint that performs a dry-run authorisation flow and returns the result.
> - **Feature 077 (Notifications)** — UPD-037's "Admin approval granted" notification (User Story 2 acceptance scenario 4) and "Approval rejected" notification reuse feature 077's existing channel routing + the `accounts.events` Kafka topic.
> - **Feature 085 (Extended E2E)** — the J02 Creator and J03 Consumer journeys are extended; the new J19 New User Signup journey is authored using feature 085's E2E harness at `tests/e2e/journeys/`.

> **Brownfield-input reconciliations** (full detail captured in planning-input.md and re-verified during the plan phase):
> 1. **Existing OAuth callback redirect target.** The brownfield input describes the current OAuth backend as redirecting to `/login` with a session fragment ("functional but not ideal"). The on-disk verification confirms `auth/router_oauth.py:154` returns `RedirectResponse(url=f"{_frontend_login_redirect(request)}#oauth_session={fragment}")`. **Resolution:** UPD-037 changes the helper `_frontend_login_redirect` (line 37) to a generic `_frontend_oauth_callback_redirect(provider)` that resolves to `/auth/oauth/{provider}/callback` per FR-593 — the existing `_frontend_login_redirect` is renamed to `_frontend_oauth_callback_redirect` and its callers at lines 126, 131, 144, 154 are updated; line 149 (`oauth_linked` redirect to profile) is preserved unchanged because that path is the link-management flow from `/settings/account/connections`, not the signup flow.
> 2. **`(auth)/auth/oauth/...` URL nesting.** The brownfield input layout places `auth/oauth/[provider]/callback/page.tsx` inside the `(auth)` route group. Next.js route groups in parentheses are stripped from the URL path, so the literal `auth/` segment becomes part of the URL: the file at `apps/web/app/(auth)/auth/oauth/[provider]/callback/page.tsx` resolves to URL `/auth/oauth/{provider}/callback` per FR-593. The double-`auth` (route-group `(auth)` + URL segment `auth`) is unusual but matches the FR text and is the established Next.js pattern for shells-with-extra-paths.
> 3. **`/settings/account/connections` location.** The brownfield input places the OAuth link-management page under `(main)/settings/account/connections/`. The on-disk `(main)/settings/` has subdirectories `alerts`, `governance`, `visibility`, `page.tsx` — no `account/` subdirectory exists. **Resolution:** UPD-037 creates the `account/` subdirectory and the `connections/` page; this is the canonical location.
> 4. **Backend gap-fillers.** The brownfield input lists three backend gaps: (a) `GET /api/v1/accounts/verify-email/{token}` should return a structured response (not a redirect) so the frontend page controls UX — verify if the existing `POST /api/v1/accounts/verify-email` endpoint already does this and if it needs a GET counterpart; (b) `GET /api/v1/auth/oauth/link-status` returning the list of providers linked to the current user — the brownfield notes this "already partly exists via `/api/v1/auth/oauth/links`" so reuse, don't duplicate; (c) `PATCH /api/v1/accounts/me` with allowlisted fields `locale`, `timezone`, `display_name` accepting changes only when status=`pending_profile_completion`. The plan phase verifies which of (a) (b) (c) are missing and adds only the genuinely missing endpoints.
> 5. **Status `pending_profile_completion` does not exist.** The brownfield input introduces this as a new user status; the on-disk `accounts/state_machine.py` has only `pending_verification`, `pending_approval`, and `active` (verified). **Resolution:** UPD-037 adds the new `UserStatus.pending_profile_completion` enum value via an Alembic migration in the plan phase; first-time OAuth users land in this state, the profile-completion form (FR-596) accepts the missing fields, and the state transitions to `active`.
> 6. **Signup-rate-limit specifics.** FR-588 specifies 5/hour per-IP and 3/24h per-email; the brownfield input cites "rate limiting per FR-588 verified with synthetic tests". **Resolution:** UPD-037 reuses the existing rate-limit middleware from `common/middleware/rate_limit_middleware.py` (verified per feature 086 inventory) with the FR-588-mandated thresholds configured for the `/api/v1/accounts/register` route; no new middleware.
> 7. **Optional CAPTCHA toggle.** FR-588 mentions hCaptcha or Turnstile as admin-activatable. The brownfield acceptance criteria do not require CAPTCHA in the MVP. **Resolution:** UPD-037 ships the signup form with a CAPTCHA-mount-point (a `<CaptchaWidget>` placeholder component) that is no-op when no CAPTCHA provider is configured; the actual CAPTCHA integration (hCaptcha or Turnstile) is an additive follow-up — not in scope for this feature.
> 8. **First-time OAuth profile completion endpoint.** The brownfield input proposes `PATCH /api/v1/accounts/me` for the profile completion. UPD-037 adds this endpoint **only if it does not already exist** (the plan phase verifies). The endpoint accepts `locale`, `timezone`, `display_name` ONLY when the user's status is `pending_profile_completion`; it transitions the status to `active` on success.
> 9. **Email verification — GET vs POST.** Today the link in the verification email needs to be clickable. A POST-only endpoint cannot be triggered by a click. **Resolution:** the verification flow uses `GET /verify-email?token=…` on the frontend (Next.js page); the page calls the existing `POST /api/v1/accounts/verify-email` with the token in the request body — the user-clicks-link path goes through the frontend page first, NOT directly to the backend. This is documented in FR-589 ("the page validates the token and transitions the account").
> 10. **`<OAuthProviderButtons>` extension.** The existing component at `apps/web/components/features/auth/OAuthProviderButtons.tsx` is reused, NOT replaced. UPD-037 adds a `context` prop with two values: `"login"` (renders "Continue with {provider}") and `"signup"` (renders "Sign up with {provider}") per FR-597. The component's existing test file at `OAuthProviderButtons.test.tsx` is extended with the new prop's coverage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Email + Password Signup on Self-Service Platform (Priority: P1)

An anonymous visitor wants to try the platform. The platform is configured for self-signup (FR-015 enabled), email verification is required (FR-020), admin approval is NOT required (FR-016 disabled). The visitor clicks "Sign up" from the login page, enters email + display name + password, accepts terms + AI disclosure consent (FR-510), and submits. The backend's existing `/api/v1/accounts/register` endpoint creates the account in `pending_verification` status. The user is redirected to `/verify-email/pending` showing the email address used and a resend button. The verification email arrives within 60 seconds with a localized body per FR-489. Clicking the link loads `/verify-email?token=…` which validates the token, transitions the account to `active`, and auto-redirects to `/login` with a success banner. The user logs in successfully.

**Why this priority**: Without `/signup`, the platform is closed to new users — the backend has the API but the UI has no entry point. P1 because (a) FR-015 + FR-586 are the canonical self-service signup contracts; (b) every customer wanting to onboard new users self-service is blocked; (c) the existing backend endpoints prove the design works — UPD-037 is the UI-completion that exposes them.

**Independent Test**: On a freshly-installed platform with self-signup enabled and admin approval disabled, navigate to `/login` and verify a "Sign up" link is visible and reachable; click → land on `/signup`; fill the form (email valid RFC 5322, display name, password ≥ 12 chars + uppercase + lowercase + digit + special, accept terms + AI disclosure); submit. Verify (a) the request `POST /api/v1/accounts/register` is sent with the form payload; (b) the response is 202 (anti-enumeration neutral response per feature 016); (c) the UI redirects to `/verify-email/pending` showing the email used; (d) the verification email arrives within 60 seconds with a localized body matching the user's `Accept-Language`; (e) clicking the email link opens `/verify-email?token=…` in the browser; (f) the page calls `POST /api/v1/accounts/verify-email` and on success renders the success state then auto-redirects to `/login` after 3 seconds; (g) login with the registered credentials succeeds; (h) the user lands on `/home` (the regular post-login destination).

**Acceptance Scenarios**:

1. **Given** self-signup is enabled (`FEATURE_SIGNUP_ENABLED=true` per FR-584) AND admin approval is NOT required (`FEATURE_SIGNUP_REQUIRES_APPROVAL=false`), **When** a visitor opens `/login`, **Then** a clearly-labelled "Sign up" link is visible (FR-586 "the page shall be reachable from the login page and vice versa").
2. **Given** the signup form, **When** the visitor enters a malformed email, **Then** client-side validation surfaces the error inline before submit; on submit, the server-side validation also rejects with a structured error per FR-583.
3. **Given** a valid form submission, **When** `POST /api/v1/accounts/register` returns 202, **Then** the UI redirects to `/verify-email/pending` and shows the email used + a "Resend verification" button.
4. **Given** the user clicks the email link with a valid token, **When** `/verify-email?token=…` loads, **Then** the page calls `POST /api/v1/accounts/verify-email` with the token and on success renders "Email verified — redirecting to login…" then auto-redirects to `/login` after 3 seconds.
5. **Given** the verification token is expired, **When** the page validates, **Then** a clear "Verification link expired" error renders with a "Resend verification" form per FR-589.
6. **Given** the verification token is already used (double-click scenario), **When** the page validates, **Then** the page treats it as success (idempotent) — the user clicked the link twice, the second click should not error.
7. **Given** self-signup is DISABLED via `FEATURE_SIGNUP_ENABLED=false`, **When** the visitor navigates to `/signup`, **Then** the page renders a clear "Signups are currently disabled" message with administrator contact link, NOT a 404 per FR-586's last sentence.

---

### User Story 2 - Signup on Platform with Admin Approval Required (Priority: P1)

An anonymous visitor signs up on a platform configured to require admin approval (FR-016 enabled). After email verification, the user MUST land on `/waiting-approval` (NOT `/login`); the page shows the current status, an estimated review time, and a contact-administrator link. Attempts to log in before approval are refused with a clear error redirecting back to `/waiting-approval`. When the admin approves via the admin workbench (`/admin/users` from feature 086), the user receives a notification via every configured channel (per feature 077) and can then log in.

**Why this priority**: Approval-required is the canonical enterprise-deployment configuration — without UPD-037, the UI does not surface the approval state and users do not know what to do post-verification. P1 because (a) FR-016 is the canonical approval contract; (b) every enterprise-tenant deployment uses approval mode; (c) the audit-trail integrity depends on the approval state being correctly surfaced.

**Independent Test**: On a platform configured with `FEATURE_SIGNUP_REQUIRES_APPROVAL=true`, sign up + verify email; verify (a) post-verification, the user lands on `/waiting-approval` (NOT `/login`); (b) the page shows the user's current status (`pending_approval`), an estimated review time (configurable per tenant — read from `platform_settings`), and a contact-administrator link; (c) attempts to log in before approval return a clear error per the existing `accounts/state_machine.py` rejection AND the UI routes back to `/waiting-approval`; (d) admin approval via `/admin/users/{id}` (feature 086) transitions the state to `active`; (e) the user receives an "Approval granted — you can now log in" notification on their configured channel; (f) login post-approval succeeds.

**Acceptance Scenarios**:

1. **Given** approval is required AND a user has just verified their email, **When** the verification page transitions, **Then** the post-verification redirect is `/waiting-approval` per the FR-589 contract for approval-required deployments.
2. **Given** a user is in `pending_approval` status, **When** they attempt to log in, **Then** the login is refused with a clear "Your account is awaiting approval" error AND the UI routes back to `/waiting-approval`.
3. **Given** the admin approves the user via `/admin/users/{id}` (feature 086), **When** the approval is committed, **Then** the user receives a notification via every configured channel and an audit chain entry records the approval.
4. **Given** the admin REJECTS the user (per the existing 8 lifecycle actions from feature 016), **When** the rejection is committed, **Then** the user receives a notification with the rejection reason; the user's state transitions to `rejected` (terminal — they cannot retry signup with the same email without admin intervention).

---

### User Story 3 - Signup via Google OAuth (Priority: P1)

A user clicks "Sign up with Google" on the signup page. Their Google Workspace domain is on the allowed list (FR-449). The Google OAuth flow completes, the dedicated callback page at `/auth/oauth/google/callback` handles the loading state, the backend auto-provisions the account, and if the user's external profile is missing platform-required fields (locale, timezone, display name preference) per FR-596, a one-time profile completion form renders before the user is granted full access. The audit chain records `signup_source=oauth_google`.

**Why this priority**: OAuth signup is the canonical low-friction onboarding flow for the Google Workspace customer segment. P1 because (a) FR-592 + FR-449 are the canonical contracts; (b) the OAuth backend is fully implemented (verified) — UPD-037 is the UI-completion that exposes it; (c) without the dedicated callback page, the OAuth flow lands on `/login` with a session fragment which is fragile UX (the existing pattern at `auth/router_oauth.py:154`).

**Independent Test**: On a platform with Google OAuth enabled and a domain restriction allowing `@example.com`, navigate to `/signup`; click "Sign up with Google"; complete the Google OAuth flow with a `@example.com` email; verify (a) the redirect lands on `/auth/oauth/google/callback` (NOT on `/login`); (b) the page renders a loading state while it processes the callback; (c) on success, the page transitions to `/profile-completion` if the user's external profile is missing required fields, ELSE directly to `/home`; (d) the audit chain has a `signup_source=oauth_google` entry; (e) the same flow with a `@unauthorized.com` email lands on `/auth/oauth/error?reason=domain_not_permitted` with a clear error and administrator contact.

**Acceptance Scenarios**:

1. **Given** Google OAuth is enabled with domain restrictions, **When** the user clicks "Sign up with Google", **Then** the redirect to Google's authorize URL includes the correct scope (`openid email profile`) and a state token per the existing `oauth_service.py` pattern.
2. **Given** the user completes the Google flow with an authorised email, **When** Google redirects back, **Then** the redirect lands on `/auth/oauth/google/callback` (NOT `/login`) per FR-593 + plan correction §1.
3. **Given** the callback page receives the auth material via the secure fragment, **When** the page processes it, **Then** the session is established without exposing tokens in browser history (the fragment is consumed and replaced via `history.replaceState`).
4. **Given** the user's domain is NOT on the allowed list, **When** the backend's domain check fires, **Then** the user is redirected to `/auth/oauth/error?reason=domain_not_permitted` with a clear error and administrator contact link.
5. **Given** the user is first-time and their external profile is missing locale or timezone, **When** the callback completes, **Then** `/profile-completion` renders with a form for the missing fields; on submit, the user's status transitions from `pending_profile_completion` to `active` and the user proceeds to `/home`.
6. **Given** the user's external profile is complete, **When** the callback completes, **Then** the user proceeds directly to `/home` without the profile-completion form.
7. **Given** the same flow but for GitHub, **When** the OAuth completes, **Then** GitHub's organisation restriction (FR-450) is honoured exactly as the Google domain restriction is; the audit chain records `signup_source=oauth_github`.

---

### User Story 4 - User Links Additional OAuth Provider from Settings (Priority: P2)

An existing local-password user wants to add GitHub OAuth for convenience. They navigate to `/settings/account/connections` (a NEW page introduced by UPD-037), click "Link GitHub", complete the OAuth flow, and see GitHub appear in the linked-providers list. Linking emits an audit entry. Unlinking is BLOCKED if the provider is the only authentication method available (no local password) per FR-594 — the safety rail prevents the user from locking themselves out.

**Why this priority**: Link-management is the canonical flow for "I already have an account; let me add OAuth as a convenience". P2 because (a) FR-594 is the canonical contract; (b) it's not on the onboarding hot path; (c) the API surface (linking, unlinking) ALREADY exists per the brownfield input — UPD-037 only adds the UI.

**Independent Test**: As an authenticated user with a local password, navigate to `/settings/account/connections`; verify (a) the page lists currently linked providers with the linked-since date; (b) clicking "Link GitHub" initiates the OAuth flow with a link-intent state token (per the existing `oauth_service.py` link logic); (c) on callback completion, the redirect goes to `/settings/account/connections?message=oauth_linked` (the existing `_frontend_profile_redirect` per `auth/router_oauth.py:149` — preserved per plan correction §1); (d) the page re-renders with GitHub in the list; (e) attempting to link a provider already linked to ANOTHER platform user is REJECTED with a clear error to prevent account takeover; (f) attempting to unlink the only authentication method is REJECTED with a clear "you must keep at least one authentication method" error.

**Acceptance Scenarios**:

1. **Given** a user with a local password and Google linked, **When** they open `/settings/account/connections`, **Then** the page lists Google with linked-since date AND a "Link GitHub" button.
2. **Given** the user clicks "Link GitHub", **When** OAuth completes, **Then** GitHub appears in the linked-providers list and an audit chain entry records `oauth.link.linked` per FR-594 last sentence.
3. **Given** a user has Google + GitHub linked AND a local password, **When** they unlink Google, **Then** the unlink succeeds (they retain GitHub + local password as auth methods); audit chain records `oauth.link.unlinked`.
4. **Given** a user has ONLY Google linked (no local password, no GitHub), **When** they attempt to unlink Google, **Then** the unlink is REJECTED with "you must keep at least one authentication method — set a local password or link another provider first".
5. **Given** Google is already linked to user A, **When** user B attempts to link the same Google identity, **Then** the link is REJECTED with "this Google account is already linked to another user" per FR-594's account-takeover safety rail.

---

### User Story 5 - Account Recovery via Linked OAuth (Priority: P3)

A user has forgotten their password but has Google linked. They click "Forgot password?" on the login page; the forgot-password page detects that the entered email has a linked OAuth provider and offers "Sign in with Google to recover access" as an alternative path. After completing OAuth, the user is logged in; the UI prompts them to optionally set a new local password (NOT required — OAuth-only login remains valid).

**Why this priority**: OAuth-recovery reduces support burden for lost-password tickets. P3 because (a) the existing forgot-password flow (feature 016 + 017) already handles the canonical email-based reset path; (b) OAuth-recovery is an additive convenience; (c) it depends on the user having previously linked OAuth — the lift is small.

**Independent Test**: On a platform where user U has Google linked AND a local password, simulate "user forgot password": from `/login`, click "Forgot password?"; on `/forgot-password`, enter U's email; verify (a) the page detects the linked provider (via `GET /api/v1/auth/oauth/link-status` per the brownfield gap-filler if needed); (b) the page renders the "Sign in with Google to recover access" CTA alongside the existing email-reset flow; (c) clicking Google completes OAuth; (d) the user is logged in; (e) a one-time prompt offers "Set a new local password" — the prompt is dismissible (not required); (f) the audit chain records `password_reset_via_oauth_recovery`.

**Acceptance Scenarios**:

1. **Given** the user has any OAuth provider linked, **When** they enter their email on `/forgot-password`, **Then** the page renders the OAuth recovery CTA alongside the existing email-reset flow per FR-598.
2. **Given** the user completes the OAuth recovery flow, **When** the session is established, **Then** the UI prompts for an optional new local password — dismissible.
3. **Given** the user dismisses the password prompt, **When** they continue, **Then** OAuth-only login remains valid; the user is NOT forced to set a local password.
4. **Given** the user enters an email with NO linked OAuth provider, **When** they click "Forgot password?", **Then** the page falls back to the existing email-reset flow with no OAuth CTA visible (anti-enumeration: the absence of the CTA is the only signal — the page DOES NOT confirm or deny the email's existence per the spec edge-case below).

---

### Edge Cases

- **Self-signup disabled (FR-015)**: `/signup` renders a clear "Signups are currently disabled" message with an administrator contact link, NOT a 404, per FR-586's last sentence. The login page's "Sign up" link is also hidden.
- **Expired verification token**: `/verify-email?token=…` shows clear "Verification link expired" error AND surfaces a resend form (rate-limited per FR-588) per FR-589.
- **Already-verified token (double-click)**: page treats it as success (idempotent) — clicking the email link twice should not produce an error per spec User Story 1 acceptance scenario 6.
- **Verification email never arrives (transient SMTP failure)**: the user can resend from `/verify-email/pending` per FR-590; resend rate limit (per-email 3/24h per FR-588) prevents abuse.
- **OAuth callback with expired state token**: callback page shows "OAuth session expired — please retry" error with retry button.
- **OAuth callback with an account already linked to a different local user (account takeover attempt)**: clear error message; account takeover is prevented at the backend level (existing `oauth_service.py` logic).
- **Domain-restricted OAuth signup from outside allowed domain**: `/auth/oauth/error?reason=domain_not_permitted` with a clear "Your domain {domain} is not permitted" message and administrator contact link per FR-449 + spec User Story 3 acceptance scenario 4.
- **Org-restricted GitHub OAuth signup from outside allowed orgs**: same pattern — `/auth/oauth/error?reason=org_not_permitted` per FR-450.
- **User attempts signup with an email already registered**: the server returns a NEUTRAL "If this is a new email, you will receive a verification" response (anti-enumeration per feature 016); if the user owns the email they can use the forgot-password flow.
- **Signup rate limit exceeded**: 429 response with `Retry-After` header per FR-588; the UI surfaces a clear countdown ("You can try again in N minutes") — the existing rate-limit middleware already returns the standard headers.
- **Network failure during OAuth callback**: callback page detects the failure and offers retry; the partial state from the OAuth provider is discarded server-side after a short timeout.
- **CAPTCHA required but not configured**: per plan correction §7, the `<CaptchaWidget>` is a no-op when no provider is configured; the form submits without a CAPTCHA token.
- **First-time OAuth user dismisses the profile-completion form**: the user CANNOT dismiss it — `pending_profile_completion` is a required state; the form's submit button is the only way out. The form is short (locale + timezone + display name; ≤ 30 seconds to complete).
- **User unlinks the only provider (no local password set)**: the unlink is BLOCKED at the backend per FR-594's safety rail; the UI also disables the unlink button to make the rule visible.
- **Forgot-password flow for a non-existent email**: anti-enumeration response — the page always shows "If this email is registered, you will receive a reset link"; the OAuth-recovery CTA is hidden when no email is detected (so the page does not leak the email's registration status).
- **OAuth provider returns a `error=access_denied`**: callback page renders "Sign-up cancelled — you denied access to your {provider} account" with a back-to-signup button.
- **`/profile-completion` accessed by a user NOT in `pending_profile_completion` state**: the page redirects to `/home` (anyone with `active` status doesn't need the form).
- **Signup form submission while offline (PWA / offline mode)**: the form refuses submission with a "You are offline — please reconnect" error.

## Requirements *(mandatory)*

### Functional Requirements (canonical citations from `docs/functional-requirements-revised-v6.md`)

**Section 110 — Public Signup, Account Activation, and OAuth UI** (FR-586 through FR-599):

- **FR-586**: Public signup page at `/signup` reachable from `/login` and vice versa; email + display name + password + AI disclosure consent + terms; clear "Signups are currently disabled" message when `FEATURE_SIGNUP_ENABLED=false`, NOT a 404.
- **FR-587**: Password policy enforcement client-side (fast feedback) AND server-side (authoritative); client rejects must NOT be the gate.
- **FR-588**: Stricter rate limiting on signup endpoint — per-IP 5/hour, per-email 3/24h, optional CAPTCHA (hCaptcha or Turnstile), 429 response with `Retry-After`.
- **FR-589**: Email verification with time-bounded single-use token (default 24h); link routes to `/verify-email?token=…`; expired or used tokens show clear error + "resend verification" action.
- **FR-590**: `/verify-email/pending` page after signup; resend action (rate-limited per FR-588); resend invalidates the previous token; user cannot log in until verification completes.
- **FR-591**: `/waiting-approval` page when admin approval is required (FR-016); shows status + estimated review time + administrator contact; user receives email notification on approve/reject; cannot log in until approved.
- **FR-592**: "Sign up with Google" / "Sign up with GitHub" buttons on `/signup`; OAuth-provisioned users follow same approval / MFA / domain restrictions as local users; unauthorised domain/org → clear error + administrator contact.
- **FR-593**: Dedicated `/auth/oauth/{provider}/callback` page with loading + error + success states; auth material via secure fragment (NOT query string); session establishment WITHOUT exposing tokens in browser history.
- **FR-594**: `/settings/account/connections` page for OAuth link management; view linked + link new + unlink; unlink BLOCKED if provider is the only authentication method.
- **FR-595**: Admin OAuth provider configuration (`/admin/oauth-providers` from feature 086) extended with: enable/disable, client ID, client secret (write-only), authorised redirect URI, domain/org restrictions, group-to-role mapping, **test-connectivity button** that performs dry-run authorisation.
- **FR-596**: First-time OAuth login profile completion when external profile lacks platform-required fields (locale, timezone, display name).
- **FR-597**: Login page OAuth provider buttons above or alongside email/password form; brand-compliant labels ("Continue with Google", "Continue with GitHub"); hidden when no provider enabled.
- **FR-598**: Forgot-password flow offers OAuth as recovery path when any provider is linked; after OAuth auth, user can set new local password (not required).
- **FR-599**: E2E coverage extends J02 Creator + J03 Consumer journeys + adds J19 New User Signup journey covering local signup, Google OAuth signup, GitHub OAuth signup.

### Key Entities

- **`/signup` page** (NEW at `apps/web/app/(auth)/signup/page.tsx`) — email + password signup form per FR-586; renders OAuth buttons via `<OAuthProviderButtons context="signup">`; CAPTCHA mount-point; AI disclosure + terms consent.
- **`/signup/disabled` page** (NEW at `apps/web/app/(auth)/signup/disabled/page.tsx`) — shown when `FEATURE_SIGNUP_ENABLED=false`; clear message + administrator contact link.
- **`/verify-email/pending` page** (NEW at `apps/web/app/(auth)/verify-email/pending/page.tsx`) — post-signup status page per FR-590; resend action; polls `/api/v1/accounts/me` for status updates.
- **`/verify-email` page** (NEW at `apps/web/app/(auth)/verify-email/page.tsx`) — token validation per FR-589; success / expired / re-used token states.
- **`/waiting-approval` page** (NEW at `apps/web/app/(auth)/waiting-approval/page.tsx`) — admin approval pending per FR-591; status + estimated review time + contact link.
- **`/auth/oauth/[provider]/callback` page** (NEW at `apps/web/app/(auth)/auth/oauth/[provider]/callback/page.tsx`) — dedicated OAuth callback page per FR-593; loading + error + success states.
- **`/auth/oauth/error` page** (NEW at `apps/web/app/(auth)/auth/oauth/error/page.tsx`) — OAuth error states (domain restriction, org restriction, provider error, expired state).
- **`/profile-completion` page** (NEW at `apps/web/app/(auth)/profile-completion/page.tsx`) — first-time OAuth profile completion per FR-596.
- **`/settings/account/connections` page** (NEW at `apps/web/app/(main)/settings/account/connections/page.tsx`) — OAuth link management per FR-594.
- **Extended `/login` page** — adds prominent signup link per FR-586; `<OAuthProviderButtons context="login">`.
- **Extended `/forgot-password` page** — adds OAuth recovery option when applicable per FR-598.
- **Shared UI components** (`apps/web/components/features/auth/`): `<SignupForm>`, `<PasswordStrengthMeter>`, `<EmailVerificationStatus>`, `<OAuthCallbackHandler>`, `<OAuthLinkList>`, `<ConsentCheckbox>`, `<CaptchaWidget>` — all NEW; `<OAuthProviderButtons>` extended with `context` prop.
- **Backend changes** (small gap-fillers): (a) extend `auth/router_oauth.py:37` `_frontend_login_redirect` → `_frontend_oauth_callback_redirect(provider)` returning `/auth/oauth/{provider}/callback`; (b) add `GET /api/v1/auth/oauth/link-status` if not already exposed via `/api/v1/auth/oauth/links` (plan-phase verification); (c) add `PATCH /api/v1/accounts/me` for profile completion if not already present; (d) add `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` per FR-595.
- **Status enum addition** (`apps/control-plane/src/platform/accounts/state_machine.py` + Alembic migration): `UserStatus.pending_profile_completion` per plan correction §5; first-time OAuth users with incomplete external profile land in this state; profile-completion form transitions to `active`.
- **Localization** — every new admin string passes through next-intl's `t()` per FR-489; the catalog files at `apps/web/messages/{en,es,fr,de,it,zh}/auth.json` (or equivalent) gain the new keys.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new visitor can complete email + password signup → email verification → first login on a self-service platform in ≤ 3 minutes (excluding email delivery time) with zero documentation lookups; the verification email arrives within 60 seconds (FR-589 implicit).
- **SC-002**: `/signup` validates email format + password strength (≥ 12 chars + uppercase + lowercase + digit + special) client-side AND server-side; client-side rejection of weak passwords does NOT bypass server-side validation per FR-587.
- **SC-003**: Signup endpoint rate-limit thresholds match FR-588 exactly: 5 attempts per hour per IP, 3 attempts per 24h per email; rate-limit responses return HTTP 429 with `Retry-After` header.
- **SC-004**: `/verify-email/pending` shows the email used + a Resend Verification button; resend is rate-limited per FR-588; resend invalidates the previous token.
- **SC-005**: `/verify-email?token=…` handles all three token states correctly: success (transitions to `active` or `pending_approval`), expired (clear error + resend form), re-used (idempotent — treated as success).
- **SC-006**: `/waiting-approval` shows correct state when admin approval is enabled; attempting to log in pre-approval is refused with a clear error AND routes back to `/waiting-approval`.
- **SC-007**: `/signup` shows OAuth provider buttons when providers are enabled; the buttons are hidden when no provider is enabled per FR-597.
- **SC-008**: Google OAuth signup auto-provisions an account; the domain restriction is honoured (unauthorised domains → `/auth/oauth/error?reason=domain_not_permitted`); the audit chain records `signup_source=oauth_google`.
- **SC-009**: GitHub OAuth signup auto-provisions an account; the org restriction is honoured (unauthorised orgs → `/auth/oauth/error?reason=org_not_permitted`); the audit chain records `signup_source=oauth_github`.
- **SC-010**: `/auth/oauth/{provider}/callback` handles loading, success, and error states; auth material is consumed via secure fragment and replaced via `history.replaceState` so tokens are NOT exposed in browser history per FR-593.
- **SC-011**: `/settings/account/connections` allows linking and unlinking providers; unlink is BLOCKED when the provider is the only authentication method per FR-594.
- **SC-012**: First-time OAuth users with incomplete external profile (missing locale, timezone, or display name) see the `/profile-completion` form before granting full access; the form transitions the status from `pending_profile_completion` to `active` on submit per FR-596.
- **SC-013**: The forgot-password flow surfaces the OAuth recovery CTA when any provider is linked to the entered email; the absence of the CTA does NOT leak the email's registration status (anti-enumeration preserved) per FR-598 + spec edge-case.
- **SC-014**: All new pages pass axe-core AA scan with zero violations on every visited page (extends J19 + J02/J03 axe scans per FR-526 + the existing CI gate from feature 083).
- **SC-015**: All new pages are fully translated into the 6 supported locales; the constitution rule 38 translation drift CI check (owned by feature 083) passes.
- **SC-016**: J19 New User Signup E2E journey passes end-to-end on the kind cluster covering: local signup → email verification → admin approval (when enabled) → first login → workspace onboarding; Google OAuth signup → domain restriction check → auto-provisioning → first login; GitHub OAuth signup → org restriction check → auto-provisioning → first login.
- **SC-017**: J02 Creator and J03 Consumer journeys are extended to cover OAuth signup paths per FR-599; both pass on the kind cluster.
- **SC-018**: The admin OAuth provider page (`/admin/oauth-providers` from feature 086) gains a working test-connectivity action per FR-595; clicking it performs a dry-run authorisation flow and returns success/failure with diagnostic detail.
- **SC-019**: The OAuth callback redirect target change (per plan correction §1) is the ONLY change to `auth/router_oauth.py` that affects existing flows; the link-management redirect at line 149 (`oauth_linked` → profile) is preserved unchanged.
- **SC-020**: Anti-enumeration is preserved across the entire signup surface: signup with an already-registered email returns a neutral 202 response (per feature 016); forgot-password with an unregistered email returns the same neutral response as a registered email (per feature 016); the forgot-password OAuth recovery CTA hides itself when no email is detected (per spec edge-case).

## Assumptions

- **Feature 014 (Auth) + Feature 016 (Accounts) + Feature 017 (Login UI) are in place.** The `/api/v1/accounts/register`, `/api/v1/accounts/verify-email`, `/api/v1/accounts/resend-verification` endpoints work; the existing `(auth)` route group has `login`, `forgot-password`, `reset-password` pages; the `accounts/state_machine.py` transitions are correct.
- **OAuth backend (`auth/oauth_service.py`, `auth/router_oauth.py`, `auth/services/oauth_providers/{github,google}.py`) is fully implemented.** The authorize endpoint, callback endpoint with PKCE for Google, state validation, and account-linking logic work; UPD-037 only changes the callback redirect target.
- **Feature 077 (Notifications) ships with the channel-routing for approval / rejection notifications.** The "Approval granted" / "Approval rejected" notifications (User Story 2) reuse feature 077's existing outbound delivery surface.
- **Feature 083 (Accessibility & i18n) ships the next-intl wiring + axe-core CI gate + 6-locale catalog.** UPD-037 inherits these; every new admin string passes through `t()`.
- **Feature 084 (Log aggregation) ships the structured-logging contract.** UPD-037 inherits structlog redaction patterns so signup-related log lines never include passwords or tokens.
- **Feature 085 (Extended E2E) ships the J02 + J03 + J18 journey harness at `tests/e2e/journeys/`.** UPD-037 extends J02 + J03 and adds J19 reusing the harness's fixtures.
- **Feature 086 (Admin Workbench) ships `/admin/oauth-providers` page from FR-548.** UPD-037 extends the page with the test-connectivity action; the page itself is owned by feature 086.
- **Feature 016 (Accounts) ships the per-email and per-IP rate-limiting logic for signup.** UPD-037 reuses the existing `common/middleware/rate_limit_middleware.py` (verified per feature 086 inventory) with the FR-588-mandated thresholds; no new middleware.
- **Out of scope:**
  - **CAPTCHA provider integration (hCaptcha or Turnstile).** UPD-037 ships the form with a `<CaptchaWidget>` placeholder that is no-op when no provider is configured; the actual integration is an additive follow-up per plan correction §7.
  - **OAuth providers beyond Google + GitHub.** FR-449 + FR-450 enumerate Google + GitHub; additional providers (Microsoft / Apple / Okta) are follow-up features.
  - **Passwordless / WebAuthn / passkey signup.** Out of scope; the platform's signup is email + password OR OAuth.
  - **Multilingual README (FR-600 / FR-601).** Section 111 of the FR document is a separate feature (UPD-038 if assigned) — not in scope for UPD-037 despite being in the same FR-document section.
  - **Admin-side bulk invitation flow.** Feature 016's `/api/v1/accounts/invitations` endpoint exists and is exposed via the admin workbench; the user-side acceptance of an invitation lands on the existing invitation acceptance page; UPD-037 does NOT change the invitation flow.
  - **First-time profile completion for non-OAuth users.** Local-signup users provide their display name during signup; they do NOT need a profile-completion step; the `pending_profile_completion` state is OAuth-only.
  - **Account merging.** If a user signs up locally with email X, then OAuth-signs-up with the same email X via Google, the second flow is REJECTED at the backend per the existing `oauth_service.py` logic. Account merging (linking the OAuth identity to the existing local account) is the existing `/settings/account/connections` flow (User Story 4).
