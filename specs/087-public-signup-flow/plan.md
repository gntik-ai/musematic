# Implementation Plan: UPD-037 — Public Signup Flow, OAuth UI Completion, Email Verification UX

**Branch**: `087-public-signup-flow` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-037 closes the gap between a fully-implemented backend (signup endpoints + OAuth flows confirmed on disk) and a UI that today only exposes `/login`. It is a **UI-heavy, backend-light** feature delivered in three convergent tracks:

- **Track A — Backend gap-fillers** (smallest, ~0.5 dev-day): two genuinely-missing pieces confirmed by inventory — (1) the `PATCH /api/v1/accounts/me` endpoint for the FR-596 first-time OAuth profile-completion flow does NOT exist (verified — the accounts router at `apps/control-plane/src/platform/accounts/router.py:61-82` exposes only register, verify-email, resend-verification); (2) the `UserStatus.pending_profile_completion` enum value does NOT exist (verified — `accounts/state_machine.py:6-30` lists 6 states: `pending_verification`, `pending_approval`, `active`, `suspended`, `blocked`, `archived`). Track A also performs the **single-line OAuth callback redirect change**: `auth/router_oauth.py:37-41` `_frontend_login_redirect()` is renamed to `_frontend_oauth_callback_redirect(provider)` returning `{origin}/auth/oauth/{provider}/callback`; ALL four call sites (lines 126, 131, 144, 154 — error + success login flows) are updated; line 149 (`oauth_linked` → `{origin}/profile`) is **preserved unchanged** because that path is the link-management flow from `/settings/account/connections`, not the signup flow.

- **Track B — New UI pages** (largest, ~3 dev-days): 9 new Next.js pages under the existing `(auth)` route group + 1 new page under `(main)/settings/account/` per the spec's key-entity inventory. Reuses the existing `<OAuthProviderButtons>` at `apps/web/components/features/auth/OAuthProviderButtons.tsx` (extended with a `variant` prop per FR-597), the existing `lib/api/auth.ts` OAuth methods (`listOAuthProviders`, `listOAuthLinks`, `authorizeOAuthProvider`, `linkOAuthProvider`, `unlinkOAuthProvider` — confirmed at lines 169-200), and adds 4 new API methods to `lib/api/auth.ts` (`register`, `verifyEmail`, `resendVerification`, `updateProfile`).

- **Track C — E2E coverage** (~1 dev-day): new BC suite at `tests/e2e/suites/signup/` (8 tests) + new J19 New User Signup journey + extension to J02 Creator and J03 Consumer journeys per FR-599. Reuses feature 085's harness at `tests/e2e/journeys/`.

The three tracks converge in Phase 6 for joint validation: J19 + extended J02/J03 + the 8 BC-suite tests run on the kind cluster with the umbrella observability chart from feature 085 already installed.

## Constitutional Anchors

This plan is bounded by the following Constitution articles. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-037 declared** | Constitution line 7 (audit-pass roster) | The whole feature |
| **Rule 35 — Email enumeration prohibited** | Constitution lines 222-224 | The existing anti-enumeration responses at `accounts/service.py:97` (register) and `:182` (resend) are the canonical contract. UPD-037's `/forgot-password` OAuth-recovery CTA (User Story 5) HIDES itself when no email is detected to preserve anti-enumeration (T030 + T060) |
| **Rule 45 — Every backend capability has a UI surface** | Constitution lines 258-262 | UPD-037 IS this rule's MVP for the signup + OAuth surfaces — the backend has been complete; UPD-037 ships the UI |
| **FR-015 — Self-signup admin toggle** | FR doc | T013 reads the `FEATURE_SIGNUP_ENABLED` flag (FR-584) on `/signup/page.tsx` SSR and renders `/signup/disabled/page.tsx` when false |
| **FR-016 — Admin approval** | FR doc | T021 routes the user to `/waiting-approval` after verification when approval mode is on |
| **FR-020 — Email verification** | FR doc | T020 implements the full flow with the existing 24h-TTL token from `accounts/service.py:111` |
| **FR-021 — User statuses** | FR doc | T002 + T003 add `pending_profile_completion` to the `UserStatus` enum + `state_machine.py` transitions |
| **FR-448, FR-449, FR-450 — OAuth framework + Google + GitHub** | FR doc | OAuth backend is complete; T012 + T040-T042 wire the UI |
| **FR-510 — AI interaction disclosure consent** | FR doc | T015's `<ConsentCheckbox>` shipped on the signup form |
| **FR-488 (WCAG AA), FR-489 (i18n), FR-490 (theming)** | feature 083 / UPD-030 contracts | Workbench inherits the next-intl + axe-core CI gate; T056 adds strings to the catalog at `apps/web/messages/{en,es,de,fr,it,zh-CN}.json` (note: the on-disk catalog also has `ja.json` from feature 083 — see plan correction §1) |
| **FR-526 — axe-core CI gate** | feature 085 / UPD-035 contract | J19 + extended J02/J03 add the new pages to the existing axe-core scan (T071) |
| **FR-583 — Structured error responses** | FR doc | Every new error path returns `{error_code, message, suggested_action, correlation_id}` — adopted from feature 086's pattern |
| **FR-586 through FR-599** | FR doc lines 2169-2208 | The whole feature — every task cites the FR it serves |

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12+ (control plane — for the 2 backend gap-fillers + the OAuth callback redirect rename), TypeScript 5.x strict (frontend — for the 10 new pages + 4 new shared components + 4 new API methods). No Go in this feature. |
| **Primary Dependencies (existing — reused)** | Python: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async (existing `User` model at `accounts/models.py:41-73` + `EmailVerification` model + `UserCredential` from feature 014), Alembic 1.13+, the existing argon2-cffi for password hashing (feature 014), the existing httpx clients for Google/GitHub OAuth (`oauth_providers/{google,github}.py`). Frontend: Next.js 14+ App Router, React 18+, shadcn/ui (existing primitives — Button, Input, Form, Label, Alert, AlertDialog, Sheet, Toast), Tailwind 3.4+, TanStack Query v5, React Hook Form 7.x + Zod 3.x, next-intl (feature 083's wiring), Lucide React. |
| **Primary Dependencies (NEW in 087)** | None. Every dependency is already installed via prior features. The CAPTCHA placeholder (`<CaptchaWidget>`) is a no-op component — the actual hCaptcha or Turnstile integration is an additive follow-up, not in scope (per spec correction §7). |
| **Storage** | PostgreSQL — 1 NEW Alembic migration `apps/control-plane/migrations/versions/066_pending_profile_completion.py` adds the `pending_profile_completion` enum value to the `userstatus` PostgreSQL enum (a tiny ALTER TYPE migration; no new tables). No new Redis keys. No new Kafka topics. The existing `accounts.events` topic from feature 016 is reused for the new events `user.profile_completed` (emitted on FR-596 form submit). |
| **Testing** | pytest 8.x + pytest-asyncio for the 2 backend gap-fillers (T002-T005); Vitest + React Testing Library for the new 4 shared components (T029-T032); Playwright for J19 E2E (uses feature 085's harness at `tests/e2e/journeys/`); the existing `axe-playwright-python` from feature 085 for accessibility scans. |
| **Target Platform** | The signup flow runs on every supported deployment topology (kind for E2E, k3s, managed Kubernetes — GKE/EKS/AKS); the workbench UI runs in any modern browser at desktop OR mobile viewport (no FR-582-style mobile restriction — signup MUST work on mobile). |
| **Project Type** | UI feature with minor backend adjustments. No new BC. UPD-037 owns the new `(auth)/signup`, `(auth)/verify-email`, `(auth)/waiting-approval`, `(auth)/auth`, `(auth)/profile-completion` page directories + the new `(main)/settings/account/connections` page + the 4 new shared components + 4 new API methods + 2 backend gap-fillers + 1 Alembic migration. |
| **Performance Goals** | New visitor completes signup → verify → first login in ≤ 3 minutes (SC-001 — excluding email delivery time). Verification email arrives in ≤ 60 s (FR-589 implicit). The OAuth callback page transitions to `/home` (or `/profile-completion`) in ≤ 2 s after the backend's redirect lands. |
| **Constraints** | Constitution Rule 35 (anti-enumeration — every server response on signup / forgot-password / OAuth is byte-equivalent for known vs unknown emails); FR-588 stricter rate limiting (5/hour per-IP, 3/24h per-email — uses the existing `common/middleware/rate_limit_middleware.py`); FR-587 server-side password validation is the AUTHORITATIVE check (client-side is UX-only); FR-593 OAuth tokens NEVER appear in URL query strings (auth material via secure fragment, consumed via `history.replaceState`); FR-594 unlink-blocked-when-only-method safety rail. |
| **Scale / Scope** | Track A: 1 Alembic migration + 1 new endpoint (PATCH /me) + 4 modified lines in `auth/router_oauth.py`. Track B: 10 new pages + 4 new shared components + 4 new API methods + 1 modified component (`<OAuthProviderButtons>` gains a `variant` prop) + i18n strings for the 6 catalogs. Track C: 1 new BC suite directory + 8 BC-suite tests + 1 new J19 journey + extensions to J02 + J03. |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing BC boundaries | ✅ Pass | UPD-037 modifies only the accounts BC (1 endpoint addition + 1 enum value) and the auth BC (4-line redirect-helper rename); the existing `service.py` business logic is untouched. The frontend additions are entirely in new directories under `(auth)/` and `(main)/settings/account/`. |
| Rule 35 — email enumeration prohibited | ✅ Pass | The existing anti-enumeration responses at `accounts/service.py:97` (register: returns `RegisterResponse()` for both new and existing emails) and `accounts/service.py:182` (resend: returns neutral message even if email not found) are the canonical contract; UPD-037 INHERITS them. The new `/forgot-password` OAuth-recovery CTA hides itself when no email is detected (T060) — the absence of the CTA is the only signal, NOT a registration-status leak. |
| Rule 45 — every backend capability has a UI surface | ✅ Pass | UPD-037 IS the realization of this rule for signup + OAuth — the backend was complete; UPD-037 closes the UI gap. |
| FR-583 — structured error responses | ✅ Pass | T040 + T050 adopt the `{error_code, message, suggested_action, correlation_id}` shape from feature 086's existing `require_admin` / `require_superadmin` dependency pattern. |
| FR-587 — server-side password validation authoritative | ✅ Pass | T013 client-side validation uses Zod schema for fast feedback ONLY; the server's existing validation at `accounts/schemas.py:36-49` (RegisterRequest) is the authoritative gate. |
| FR-588 — rate limiting | ✅ Pass | T002 confirms the rate-limit-middleware policies for `/api/v1/accounts/register` (5/hour per-IP, 3/24h per-email); T065's E2E test verifies the 429 + Retry-After response. |
| FR-489 + Constitution rule 38 — translation drift | ✅ Pass | T056 adds the new strings to all 6 (or 7 — see plan correction §1) catalog files; the existing CI translation-drift check from feature 083 fails the build if any catalog falls out of sync. |
| FR-526 — axe-core CI gate | ✅ Pass | T071 + T072 ensure J19 + extended J02/J03 axe-core scan covers every new page; the existing CI gate from feature 085 / UPD-035 is reused. |
| FR-593 — OAuth tokens not in URL query strings | ✅ Pass | T040's `<OAuthCallbackHandler>` consumes the auth material from `window.location.hash`, parses it, then immediately calls `history.replaceState(null, '', window.location.pathname)` to clear the fragment from browser history. |
| FR-594 — unlink safety rail | ✅ Pass | T034's `<OAuthLinkList>` disables the unlink button when the provider is the only auth method; T059 backend gap-filler is NOT needed here because the existing unlink endpoint at `auth/router_oauth.py` already enforces the rule (verified — see plan research R3). |

**Verdict: gate passes. No declared variances. UPD-037 is fully constitutional given the backend's existing anti-enumeration discipline.**

## Project Structure

### Documentation (this feature)

```text
specs/087-public-signup-flow/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
apps/control-plane/src/platform/accounts/
├── router.py                                # MODIFY (add `PATCH /me` endpoint per FR-596)
├── service.py                               # MODIFY (add `update_profile()` method handling pending_profile_completion → active transition)
├── schemas.py                               # MODIFY (add `ProfileUpdateRequest` and `ProfileUpdateResponse`)
├── state_machine.py                         # MODIFY (add `pending_profile_completion → active` transition; new state lives between `pending_verification` and `active` for OAuth-only path)
└── models.py                                # MODIFY (extend `UserStatus` enum at lines 15-21 with `pending_profile_completion`)

apps/control-plane/src/platform/auth/
├── router_oauth.py                          # MODIFY (rename `_frontend_login_redirect` at lines 37-41 → `_frontend_oauth_callback_redirect(provider)`; update 4 call sites at lines 126, 131, 144, 154; PRESERVE line 149's `_frontend_profile_redirect` unchanged)
├── oauth_service.py                         # MODIFY (the `_auto_provision_user()` at line 354 sets `pending_profile_completion` if external profile lacks `locale` OR `timezone` OR `display_name`; otherwise sets `active` per FR-596)
└── services/oauth_providers/                # NO CHANGE (Google + GitHub provider logic untouched)

apps/control-plane/src/platform/admin/
└── auth/admin_router.py                     # MODIFY (add `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` endpoint per FR-595 — the test-connectivity action; uses the existing oauth provider's `get_auth_url()` to construct a dry-run URL and asserts it 200s)

apps/control-plane/migrations/versions/
└── 066_pending_profile_completion.py        # NEW (Alembic — adds `pending_profile_completion` to `userstatus` PostgreSQL enum)

apps/web/app/(auth)/
├── layout.tsx                               # NO CHANGE (existing auth shell)
├── login/page.tsx                           # MODIFY (add prominent "Sign up" link; pass `variant="login"` to `<OAuthProviderButtons>`)
├── signup/
│   ├── page.tsx                             # NEW (FR-586 — email + password + display name + AI disclosure consent + terms; OAuth buttons via `<OAuthProviderButtons variant="signup">`)
│   └── disabled/page.tsx                    # NEW (rendered when `FEATURE_SIGNUP_ENABLED=false` per FR-586's last sentence)
├── verify-email/
│   ├── page.tsx                             # NEW (FR-589 — token validation; success → /login or /waiting-approval; expired → resend form; re-used → success idempotent)
│   └── pending/page.tsx                     # NEW (FR-590 — post-signup status + resend action; polls `GET /api/v1/accounts/me` for status updates)
├── waiting-approval/page.tsx                # NEW (FR-591 — admin approval pending; status + estimated review time + administrator contact)
├── auth/oauth/[provider]/callback/page.tsx  # NEW (FR-593 — dedicated OAuth callback handler; loading + error + success states)
├── auth/oauth/error/page.tsx                # NEW (FR-449 + FR-450 — OAuth error states: domain restriction, org restriction, expired state, provider error)
├── profile-completion/page.tsx              # NEW (FR-596 — first-time OAuth profile completion form; locale + timezone + display name)
├── forgot-password/page.tsx                 # MODIFY (add OAuth recovery CTA when applicable per FR-598; the absence of the CTA when no email is registered preserves anti-enumeration per Constitution Rule 35)
└── reset-password/[token]/page.tsx          # NO CHANGE

apps/web/app/(main)/
└── settings/account/connections/page.tsx    # NEW (FR-594 — OAuth link management with `<OAuthLinkList>`)

apps/web/components/features/auth/
├── OAuthProviderButtons.tsx                 # MODIFY (add `variant: "login" | "signup"` prop per FR-597; existing component at apps/web/components/features/auth/OAuthProviderButtons.tsx — line 67 currently renders "Continue with {provider.display_name}", new variant renders "Sign up with {provider.display_name}" when variant="signup")
├── OAuthProviderButtons.test.tsx            # MODIFY (add coverage for the new `variant` prop)
├── SignupForm.tsx                           # NEW (email + password + display name + RHF/Zod validation + password strength meter + consent checkboxes)
├── PasswordStrengthMeter.tsx                # NEW (reusable — used by signup AND password reset; visual indicator for FR-587 client-side validation)
├── EmailVerificationStatus.tsx              # NEW (polls `GET /api/v1/accounts/me` for status updates per FR-590; renders the current status badge)
├── OAuthCallbackHandler.tsx                 # NEW (consumes the auth-material fragment; calls `history.replaceState` to clear from browser history per FR-593; renders loading / success / error states)
├── OAuthLinkList.tsx                        # NEW (renders linked providers with linked-since date + unlink action; unlink BLOCKED when provider is the only auth method per FR-594)
├── ConsentCheckbox.tsx                      # NEW (AI disclosure + terms + privacy policy links per FR-510)
└── CaptchaWidget.tsx                        # NEW (placeholder — no-op when no CAPTCHA provider is configured; the actual integration is follow-up per plan correction §7)

apps/web/lib/api/
└── auth.ts                                  # MODIFY (add 4 new methods: register, verifyEmail, resendVerification, updateProfile)

apps/web/messages/
├── en.json                                  # MODIFY (add the new auth strings — currently the file is empty `{}` per the inventory)
├── es.json                                  # MODIFY
├── de.json                                  # MODIFY
├── fr.json                                  # MODIFY
├── it.json                                  # MODIFY
├── zh-CN.json                               # MODIFY
└── ja.json                                  # MODIFY (note: 7 locales on disk — see plan correction §1)

tests/e2e/journeys/
├── test_j02_creator_to_publication.py       # MODIFY (extend per FR-599 — optionally use OAuth signup path)
├── test_j03_consumer_discovery_execution.py # MODIFY (extend per FR-599)
└── test_j19_new_user_signup.py              # NEW (the new J19 journey covering all 5 user stories)

tests/e2e/suites/
└── signup/                                  # NEW directory
    ├── __init__.py                          # NEW
    ├── test_signup_email_password.py        # NEW (US1 happy path)
    ├── test_signup_with_approval_required.py # NEW (US2)
    ├── test_signup_oauth_google.py          # NEW (US3 — Google domain restriction)
    ├── test_signup_oauth_github.py          # NEW (US3 — GitHub org restriction)
    ├── test_oauth_link_management.py        # NEW (US4)
    ├── test_oauth_recovery.py               # NEW (US5)
    ├── test_email_enumeration_resistance.py # NEW (Constitution Rule 35 verification)
    └── test_rate_limiting.py                # NEW (FR-588 — 5/hour per-IP + 3/24h per-email)
```

**Structure Decision**: UPD-037 follows the established Next.js + FastAPI + Alembic conventions. The new `(auth)` route-group sub-paths land alongside the existing `login/`, `forgot-password/`, `reset-password/` directories. The new `(main)/settings/account/connections/` lands as a new sub-path of the existing settings tree. The 4 new shared components live alongside the existing `OAuthProviderButtons.tsx` at `apps/web/components/features/auth/`. The 2 backend gap-fillers (PATCH /me + new enum value) are minimal additions to the existing accounts BC. The OAuth callback redirect rename is a 4-line modification to `auth/router_oauth.py`. No new BC. No new database tables. No new Kafka topics (the existing `accounts.events` topic is reused for `user.profile_completed`). No new Redis key namespaces.

## Brownfield-Input Reconciliations

These are corrections from spec to plan. Each is an artifact-level discrepancy between the brownfield input and the on-disk codebase.

1. **Locale count: 7 catalogs on disk, brownfield says 6.** The brownfield input writes "all new pages fully localized into 6 languages" and references feature 083's "6 supported locales". The on-disk inventory of `apps/web/messages/` confirms **7 catalog files**: `en.json`, `es.json`, `de.json`, `fr.json`, `it.json`, `zh-CN.json`, AND `ja.json` (Japanese — extra locale beyond the 6 declared in feature 083). **Resolution:** UPD-037 adds the new auth strings to ALL 7 catalogs to maintain the existing 7-catalog discipline; if `ja.json` was added by feature 083 as an out-of-scope addition, UPD-037 follows suit (NOT removing it would break the existing translation-drift CI check). The plan and tasks consistently target 7 locales.

2. **`OAuthProviderAdminPanel` component exists but is NOT routed.** The brownfield input writes "Admin OAuth configuration UI is partially covered by UPD-036's `/admin/oauth-providers` page". The on-disk inventory confirms `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx` exists with a complete form (enabled toggle, client_id, client_secret_ref, redirect_uri, scopes, domain_restrictions, org_restrictions, group_role_mapping, default_role, require_mfa) BUT the `/admin/oauth-providers/page.tsx` page that ROUTES this component does NOT exist on disk yet. **Resolution:** Feature 086 (UPD-036 task T034 `auth/admin_router.py` + T084 Identity & Access pages) is the canonical owner of routing this component into the admin workbench. UPD-037's contribution is ONLY the **test-connectivity button** addition to the existing component (T010) AND the backing endpoint `POST /api/v1/admin/oauth-providers/{provider}/test-connectivity` (T009). Sequencing: UPD-037 lands AFTER UPD-036 so the admin workbench's `/admin/oauth-providers` page exists by the time UPD-037 adds the test-connectivity action.

3. **Brownfield's `_frontend_login_redirect` rename has FOUR call sites, not one.** The brownfield input describes the change as "the OAuth callback backend response includes sufficient fragment data" implying a localized change. The on-disk inventory at `auth/router_oauth.py` shows `_frontend_login_redirect()` is called at lines 126 (error redirect), 131 (invalid_oauth_callback error), 144 (provider error), and 154 (success login flow). **Resolution:** UPD-037's T006 updates ALL four call sites to use the new `_frontend_oauth_callback_redirect(provider)` helper — the new dedicated callback page at `/auth/oauth/{provider}/callback` handles BOTH error and success states (the page's `<OAuthCallbackHandler>` reads `?error=…` query parameters AND the `#oauth_session=…` fragment per FR-593). Line 149's `_frontend_profile_redirect()` for the `oauth_linked` link-management redirect is **preserved unchanged** — that path is feature 086's `/settings/account/connections` flow, not the signup flow.

4. **No `PATCH /api/v1/accounts/me` endpoint exists** (verified — `accounts/router.py:61-82` has only register / verify-email / resend-verification). The brownfield input flagged this as a "may need addition" — confirmed missing. **Resolution:** T002 + T003 + T004 add the endpoint with allowlisted fields `locale`, `timezone`, `display_name`; the endpoint accepts changes ONLY when the user's status is `pending_profile_completion` (returns 403 otherwise) and on success transitions the status to `active` and emits the new `user.profile_completed` event on the existing `accounts.events` Kafka topic.

5. **`pending_profile_completion` enum value is genuinely missing** (verified — `accounts/models.py:15-21` lists 6 values: `pending_verification`, `pending_approval`, `active`, `suspended`, `blocked`, `archived`; `state_machine.py:6-30` has 6 transition rows). **Resolution:** T002 (Alembic migration 066) extends the PostgreSQL `userstatus` enum with `pending_profile_completion`; T003 modifies `models.py` and `state_machine.py` to add the new value + the `pending_profile_completion → active` transition. The state lives in the OAuth-only path: a first-time OAuth user with incomplete external profile is provisioned in `pending_profile_completion`; the profile-completion form transitions to `active`.

6. **Existing `<OAuthProviderButtons>` has NO props** (verified — current implementation at line 67 hardcodes "Continue with {provider.display_name}"). The brownfield input writes "EXTENDED with `Continue with …` / `Sign up with …` labels based on context". **Resolution:** T029 adds a `variant: "login" | "signup"` prop (defaulting to `"login"` for backwards compatibility); the existing label "Continue with X" is the `"login"` variant; the new label "Sign up with X" is the `"signup"` variant. The existing test file at `OAuthProviderButtons.test.tsx` is extended with the new prop's coverage (T030).

7. **`apps/web/lib/api/auth.ts` has OAuth methods but NO signup methods** (verified — lines 169-200 expose `listOAuthProviders`, `listOAuthLinks`, `authorizeOAuthProvider`, `linkOAuthProvider`, `unlinkOAuthProvider`; signup flow is backend-only today). **Resolution:** T037-T040 add 4 new API methods: `register(payload)`, `verifyEmail(token)`, `resendVerification(email)`, `updateProfile(payload)`. The signatures match the backend schemas (`RegisterRequest`, `VerifyEmailRequest`, `ResendVerificationRequest`, the new `ProfileUpdateRequest` from T004). Reuses the existing `lib/api.ts` `createApiClient(baseUrl).post / patch` pattern from feature 015 + the JWT-injection middleware from `lib/api.ts:70-100`.

8. **`(main)/settings/page.tsx` is a minimal stub** (verified — renders only "Settings" title and placeholder text). The brownfield input does not specify how the new `connections` sub-path integrates with the existing settings layout. **Resolution:** UPD-037 does NOT modify the existing settings layout; it adds `(main)/settings/account/connections/page.tsx` as a sub-route that uses the standard `(main)` layout's navigation patterns. The existing settings page stub is left for feature 086's settings-page work (UPD-036 T086 absorbs feature 027's settings panel; UPD-037's `connections` page is a sibling sub-route, not nested under `/admin/settings`).

9. **`tests/e2e/suites/signup/` does NOT exist on disk.** The brownfield input proposes 8 BC-suite tests under this directory. **Resolution:** T067-T075 create the directory + the 8 tests using feature 085's `tests/e2e/journeys/conftest.py` fixtures (the per-test isolation pattern + the `kafka_consumer` fixture for verifying `accounts.events` emissions + the `db` fixture for direct PostgreSQL assertions). The directory is integrated into `tests/e2e/Makefile`'s `e2e-test` target automatically (per feature 071's existing convention — pytest auto-discovers suite subdirectories).

10. **CAPTCHA is out of scope per spec correction §7.** Brownfield acceptance criteria do not require CAPTCHA; FR-588 mentions it as admin-activatable. **Resolution:** UPD-037 ships `<CaptchaWidget>` (T035) as a no-op component with a documented integration interface (`onTokenChange` callback); when no provider is configured, the widget renders nothing and `onTokenChange` is never called; the form's `register` mutation submits without a CAPTCHA token and the backend accepts (FR-588's CAPTCHA is `optional`). The actual hCaptcha or Turnstile integration is a follow-up (likely UPD-038 or later).

11. **The OAuth `oauth_session` fragment is base64URL-encoded JSON** (verified — `auth/router_oauth.py:51-55` `_oauth_session_fragment()` encodes payload as base64URL). The brownfield input writes "auth material via secure fragment" without specifying the encoding. **Resolution:** T040's `<OAuthCallbackHandler>` uses the existing `decodeOAuthSessionFragment()` helper from `apps/web/lib/api/auth.ts:98-115` (verified) — the helper already decodes the base64URL → JSON pattern; UPD-037 reuses it AS-IS.

12. **MFA-required path on OAuth callback is already handled** (verified — `oauth_service.py:414-438` returns `{"mfa_required": True, "session_token": challenge.mfa_token, "user": user_payload}` when the provider requires MFA and the user is enrolled). The brownfield input does not enumerate this; the spec edge-cases mention it implicitly. **Resolution:** T040's `<OAuthCallbackHandler>` checks `isOAuthCallbackMfaResponse(decoded)` (existing helper in `lib/api/auth.ts`) and routes to the MFA-challenge UI from feature 017 (the existing MFA flow); on success it then completes the session establishment.

## Phase 0 — Research and Design Decisions

### R1. Why a dedicated OAuth callback page (FR-593) instead of the existing `/login#fragment` pattern?

Two competing patterns:
1. **Existing `/login#fragment` pattern** (`auth/router_oauth.py:154`): the backend redirects to `/login` with `#oauth_session=…`; the login page reads the fragment and completes the session.
2. **Dedicated `/auth/oauth/{provider}/callback` page** (FR-593): a separate page handles the callback exclusively.

**Decision**: Dedicated page. Reasons: (a) the login page today has dual semantics (regular login form + OAuth callback handler) which is fragile when extending either path; (b) FR-593 explicitly requires this separation — "without exposing tokens in browser history"; (c) the dedicated page can render its own loading + error UI without polluting the login page; (d) error paths (domain restriction, expired state) get a clean error page (`/auth/oauth/error`) rather than a query-string-decorated login page.

### R2. Why server-side check on `pending_profile_completion` instead of client-side?

The first-time OAuth user lands on `/profile-completion` if their external profile lacks required fields (locale, timezone, display name). Two patterns:
1. **Client-side check**: `<OAuthCallbackHandler>` inspects the user object and routes to `/profile-completion` or `/home` based on missing fields.
2. **Server-side check**: the backend's `_auto_provision_user()` at `oauth_service.py:354` sets the user's status to `pending_profile_completion` if any required field is missing; the redirect target is `/profile-completion` regardless of client logic.

**Decision**: Server-side. Reasons: (a) the status is the authoritative source of truth (a malicious client could fake the user object to bypass profile completion); (b) the server has all the data; (c) the `pending_profile_completion → active` transition is a state-machine event that produces an audit chain entry; (d) the `PATCH /api/v1/accounts/me` endpoint can return 403 if the user is not in `pending_profile_completion` — defence in depth.

### R3. Does the existing OAuth unlink endpoint already enforce the FR-594 safety rail?

Inventory verified the unlink endpoint exists at `auth/router_oauth.py` (lines 100-110, `DELETE /api/v1/auth/oauth/{provider}/link`). The question is: does it BLOCK the unlink when the provider is the only auth method?

**Decision**: Verified by reading the existing endpoint logic (and the `oauth_service.py` unlink implementation): the existing logic checks if the user has a local password OR another linked provider before allowing unlink; if neither, it raises an error. **UPD-037 does NOT modify the unlink endpoint** — the safety rail is already enforced. T034's `<OAuthLinkList>` UI also disables the unlink button (UX) but the API enforcement is the authoritative gate.

### R4. Verification email link behaviour: GET vs POST

The verification email contains a clickable link. A POST endpoint cannot be triggered by clicking a link (browsers issue GET on link clicks).

**Decision** (also documented in spec correction §9): the email link points to the **frontend** URL `/verify-email?token=…` (Next.js page). The page reads the token from the query string AND calls the **backend** `POST /api/v1/accounts/verify-email` with the token in the request body (existing endpoint at `accounts/router.py:69-74`). This pattern preserves the backend's POST-only API while supporting the click-from-email UX. The backend endpoint accepts the token in the body (`VerifyEmailRequest` at `accounts/schemas.py:52-53`).

### R5. `/forgot-password` OAuth-recovery CTA — anti-enumeration design

User Story 5 requires the forgot-password page to surface "Sign in with Google" when the user's email has a linked OAuth provider. The risk: this CTA leaks the email's registration status (an attacker could probe for emails by entering them and observing whether the OAuth CTA appears).

**Decision**: The CTA is rendered ONLY when the backend's `GET /api/v1/auth/oauth/link-status?email={email}` returns a non-empty list — but the response shape is **identical** for unregistered emails (returns an empty list AND HTTP 200) per Constitution Rule 35. The frontend never makes a separate "does this email exist" check. T060 implements this — the CTA's visibility is purely a function of the link-status response, which is anti-enumeration-safe by backend contract.

### R6. Rate-limit configuration for `/api/v1/accounts/register`

FR-588 mandates 5 attempts/hour per-IP and 3 attempts/24h per-email. The existing `common/middleware/rate_limit_middleware.py` (verified per inventory) uses a `RateLimiterService` with policies resolved per-route; the FR-588 thresholds may not currently be configured.

**Decision**: T002's verification step confirms the current policy configuration; if the FR-588 thresholds are not configured, T005 adds them via the existing policy-configuration mechanism (NO middleware changes needed). The verification step is a one-line check via the admin API or the in-process `RateLimiterService.resolve_anonymous_policy("register")` method.

### R7. `<OAuthCallbackHandler>` retry behaviour

Spec edge-case "Network failure during OAuth callback" requires the callback page to offer retry. Two retry strategies:
1. **Retry the same callback URL**: re-issues the GET to `/auth/oauth/{provider}/callback?code=…&state=…` — but the state token is single-use (verified at `oauth_service.py:241`), so this would fail with a "state already consumed" error.
2. **Retry the entire OAuth flow**: redirect back to `/signup` (or `/login` based on intent) and let the user click the OAuth button again.

**Decision**: Strategy #2. The retry button on `/auth/oauth/error?reason=network_failure` redirects to `/signup` (or `/login` based on a query-param `intent`). This is simpler and aligns with the OAuth provider's expectations (state tokens are designed to be single-use).

### R8. `<EmailVerificationStatus>` polling cadence

FR-590's resend page polls `GET /api/v1/accounts/me` for status updates. Two cadences:
1. **High-frequency (1s)**: low latency on status changes but high server load.
2. **Low-frequency (5-10s)**: lower load, slight latency.

**Decision**: 5s polling with backoff to 30s after 60s of no status change. The page shows a manual "Refresh status" button for impatient users. The backend's `GET /api/v1/accounts/me` is a small endpoint (returns the user record) and the rate-limit middleware easily handles this cadence per anonymous principal.

### R9. Profile-completion form: required fields

FR-596 requires "locale, timezone, display name preference" — implementation question: which fields are MANDATORY vs OPTIONAL? Different OAuth providers populate different external profiles (Google has display name + locale; GitHub has display name only; locale is rarely populated).

**Decision**: **All three fields mandatory**, but with sensible defaults:
- `locale` defaults to the browser's `navigator.language` or `Accept-Language`
- `timezone` defaults to `Intl.DateTimeFormat().resolvedOptions().timeZone`
- `display_name` defaults to the OAuth provider's `display_name` (or email local-part if not provided)

The user reviews the defaults and edits if needed; submit is enabled even with the defaults. The form takes ≤ 30 seconds for the typical user (per spec edge-case).

### R10. CSRF protection on `/signup` POST

The brownfield's "Security Notes" section says "CSRF protection is mandatory on the signup POST". The existing `lib/api.ts` JWT-injection pattern works for authenticated routes; the signup POST is unauthenticated.

**Decision**: Next.js's built-in CSRF protection uses the SameSite cookie attribute on session cookies (Strict by default in feature 015). For unauthenticated POST endpoints, the platform relies on:
- The backend's existing rate-limit middleware (5/hour per-IP) to throttle abuse
- The backend's anti-enumeration response shape (no information leak even if abused)
- A one-time CSRF token embedded in the server-rendered signup page (added by T015) — the form's POST includes the token and the backend validates it via the existing CSRF middleware

The CSRF token is generated server-side by Next.js Server Components (using the existing pattern from feature 014's auth flow) and embedded as a hidden form field.

## Phase 1 — Design

### Track A — Backend Gap-Fillers

```
1. Alembic migration 066_pending_profile_completion.py
     │
     ├── ALTER TYPE userstatus ADD VALUE 'pending_profile_completion';
     ├── (no rollback — PostgreSQL enums are append-only;
     │    rollback strategy is to leave the value in place harmlessly)
     └── runs via the existing `make migrate` flow

2. accounts/models.py:
     class UserStatus(str, Enum):
         pending_verification = "pending_verification"
         pending_approval = "pending_approval"
         pending_profile_completion = "pending_profile_completion"  # NEW
         active = "active"
         suspended = "suspended"
         blocked = "blocked"
         archived = "archived"

3. accounts/state_machine.py adds the row:
     UserStatus.pending_profile_completion: {UserStatus.active}

4. accounts/router.py adds:
     @router.patch("/me", response_model=ProfileUpdateResponse)
     async def update_profile(
         request: ProfileUpdateRequest,
         service: AccountsService = Depends(...),
         current_user: dict = Depends(get_current_user),
     ) -> ProfileUpdateResponse:
         # service.update_profile() validates status=pending_profile_completion
         # transitions to active on success; emits user.profile_completed event
         return await service.update_profile(current_user["sub"], request)

5. auth/router_oauth.py:
     # BEFORE (line 37-41):
     def _frontend_login_redirect(request: Request) -> str:
         origin = request.headers.get("origin", "")
         return f"{origin}/login"

     # AFTER:
     def _frontend_oauth_callback_redirect(request: Request, provider: str) -> str:
         origin = request.headers.get("origin", "")
         return f"{origin}/auth/oauth/{provider}/callback"

     # All four call sites at lines 126, 131, 144, 154 updated:
     #   url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={error}"
     #   url=f"{_frontend_oauth_callback_redirect(request, provider)}?error=invalid_oauth_callback"
     #   url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={exc.code.lower()}"
     #   url=f"{_frontend_oauth_callback_redirect(request, provider)}#oauth_session={fragment}"
     # Line 149 (link-management redirect) is PRESERVED unchanged.

6. auth/oauth_service.py `_auto_provision_user()` (line 354):
     # Existing: creates user with status=active (if no approval) or pending_approval
     # Modified: if external profile lacks locale OR timezone OR display_name:
     #   set status=pending_profile_completion
     # Else: keep existing status logic (pending_approval or active)
```

### Track B — UI Architecture

```
                 ┌────────────────────────────────────────────┐
                 │ Anonymous visitor on /signup                │
                 └─────────────────┬──────────────────────────┘
                                   │
                                   ├── click "Sign up" with email+password
                                   │     │
                                   │     └─── POST /api/v1/accounts/register
                                   │               │
                                   │               └─── 202 Accepted (anti-enum)
                                   │                     │
                                   │                     └─── redirect to /verify-email/pending
                                   │                           │
                                   │                           └── poll /me until email_verified_at IS NOT NULL
                                   │                                 │
                                   │                                 └── (separate flow: user clicks email link)
                                   │                                       │
                                   │                                       └── /verify-email?token=...
                                   │                                             │
                                   │                                             └── POST /api/v1/accounts/verify-email
                                   │                                                   │
                                   │                                                   ├── if approval_required: → /waiting-approval
                                   │                                                   └── else: → /login (success banner)
                                   │
                                   └── click "Sign up with Google" or "Sign up with GitHub"
                                         │
                                         └── window.location = authorize_url (existing OAuthProviderButtons.tsx flow)
                                               │
                                               └── (Google/GitHub OAuth flow)
                                                     │
                                                     └── BACKEND callback at GET /api/v1/auth/oauth/{provider}/callback
                                                           │
                                                           └── redirects to /auth/oauth/{provider}/callback (NEW per FR-593)
                                                                 │
                                                                 └── <OAuthCallbackHandler> at /auth/oauth/[provider]/callback/page.tsx
                                                                       │
                                                                       ├── reads #oauth_session=... fragment
                                                                       ├── calls history.replaceState(null, '', pathname) to clear fragment
                                                                       ├── if MFA required: → MFA challenge UI (feature 017)
                                                                       ├── if user.status=pending_profile_completion: → /profile-completion
                                                                       ├── if approval_required: → /waiting-approval
                                                                       └── else: → /home (login complete)
```

### Track B — `<OAuthProviderButtons>` Extension (canonical signature)

```typescript
// apps/web/components/features/auth/OAuthProviderButtons.tsx — MODIFIED

interface Props {
  variant?: "login" | "signup";  // NEW prop; default "login" for backwards compat
}

export function OAuthProviderButtons({ variant = "login" }: Props = {}) {
  const { providers } = useOAuthProviders();
  const labelPrefix = variant === "signup" ? "Sign up with" : "Continue with";

  return (
    <>
      {providers.filter(p => p.enabled).map(provider => (
        <Button onClick={() => authorizeMutation.mutateAsync(provider.provider_type)}>
          <ProviderIcon provider={provider.provider_type} />
          {`${labelPrefix} ${provider.display_name}`}
        </Button>
      ))}
    </>
  );
}
```

The existing test file at `OAuthProviderButtons.test.tsx` is extended with a test for the new `variant="signup"` prop rendering "Sign up with Google" instead of "Continue with Google".

### Track B — `<OAuthCallbackHandler>` Architecture (canonical sketch)

```typescript
// apps/web/components/features/auth/OAuthCallbackHandler.tsx — NEW

"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { decodeOAuthSessionFragment, isOAuthCallbackMfaResponse } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth-store";

export function OAuthCallbackHandler({ provider }: { provider: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [state, setState] = useState<"loading" | "error" | "success">("loading");
  const [error, setError] = useState<string | null>(null);
  const setAuth = useAuthStore(s => s.setAuth);

  useEffect(() => {
    // Check for ?error=... query param (set by backend on failure paths)
    const errorCode = params.get("error");
    if (errorCode) {
      setError(errorCode);
      setState("error");
      return;
    }

    // Read auth material from #oauth_session=... fragment
    const fragment = window.location.hash.slice(1);
    const params2 = new URLSearchParams(fragment);
    const session = params2.get("oauth_session");
    if (!session) {
      setError("missing_session");
      setState("error");
      return;
    }

    // Decode + clear from history
    const decoded = decodeOAuthSessionFragment(session);
    history.replaceState(null, "", window.location.pathname);

    // MFA required path
    if (isOAuthCallbackMfaResponse(decoded)) {
      router.push(`/login/mfa?session_token=${decoded.session_token}`);
      return;
    }

    // Establish session
    setAuth({
      accessToken: decoded.token_pair.access_token,
      refreshToken: decoded.token_pair.refresh_token,
      user: decoded.user,
    });

    // Route to next step based on user status
    if (decoded.user.status === "pending_profile_completion") {
      router.push("/profile-completion");
    } else if (decoded.user.status === "pending_approval") {
      router.push("/waiting-approval");
    } else {
      router.push("/home");
    }
    setState("success");
  }, [params, router, setAuth]);

  if (state === "loading") return <LoadingSpinner />;
  if (state === "error") return <OAuthErrorCard error={error} provider={provider} />;
  return <SuccessTransition />;
}
```

## Phase 2 — Implementation Order

| Phase | Goal | Tasks (T-numbers indicative; final list in tasks.md) | Wave | Parallelizable |
|---|---|---|---|---|
| **0. Setup** | Alembic migration 066, audit existing endpoints | T001-T002 | W12.0 | yes |
| **1. Track A — Backend gap-fillers** | `pending_profile_completion` enum + state-machine row + `PATCH /me` endpoint + OAuth callback redirect rename + admin test-connectivity endpoint | T003-T011 | W12A.1 | sequential |
| **2. Track B — Shared components** | 4 new shared components + `<OAuthProviderButtons>` extension + 4 new API methods | T012-T040 | W12B.1 | mostly parallel |
| **3. Track B — Auth pages (US1 + US2 + US3)** | `/signup`, `/signup/disabled`, `/verify-email`, `/verify-email/pending`, `/waiting-approval`, `/auth/oauth/[provider]/callback`, `/auth/oauth/error`, `/profile-completion` | T041-T056 | W12B.2 | mostly parallel |
| **4. Track B — Settings + forgot-password extension (US4 + US5)** | `/settings/account/connections` + `/forgot-password` extension | T057-T062 | W12B.3 | parallel |
| **5. Track B — i18n** | Add new strings to all 7 locale catalogs | T063-T064 | W12B.4 | yes (per-locale parallel) |
| **6. Track C — E2E coverage** | New `tests/e2e/suites/signup/` + J19 + J02/J03 extensions | T065-T080 | W12C.1 | mostly parallel |
| **7. Polish + docs** | Operator README + admin OAuth UI test-connectivity wiring + CLAUDE.md update | T081-T087 | W12D | yes |

### Wave layout

UPD-037 lands in **Wave 12** (post-UPD-036). Sub-divisions:

- **Wave 12.0 — Setup**: T001-T002; ~0.25 dev-day; one dev.
- **Wave 12A — Backend gap-fillers**: T003-T011; ~0.75 dev-day; one dev.
- **Wave 12B — UI**: T012-T064; ~3 dev-days; one dev (parallel sub-tasks within phases).
- **Wave 12C — E2E**: T065-T080; ~1 dev-day; one dev.
- **Wave 12D — Polish**: T081-T087; ~0.5 dev-day; one dev.

**Total: ~5.5 dev-days.** With two devs (one on Track A + Track C, one on Track B), wall-clock is **~3.5 days**. The brownfield input's 4-day estimate is achievable but the inventory-confirmed 2 backend gap-fillers + the comprehensive E2E coverage (8 BC tests + J19 + 2 extended journeys) push the realistic estimate to ~5.5 dev-days.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **OAuth callback URL change breaks existing OAuth provider configs at Google/GitHub** | High (the redirect URI registered at the OAuth provider's console MUST be updated to the new callback path) | High — OAuth flow fails with "redirect_uri_mismatch" | The OAuth provider config's `redirect_uri` is stored in the platform's database (per `OAuthProviderCreate` schema at `oauth_service.py:168`); UPD-037 does NOT change the BACKEND callback URL (`/api/v1/auth/oauth/{provider}/callback` stays the same); only the FRONTEND redirect target after the backend processes the callback changes. Google/GitHub still POST/GET to the SAME backend URL — no provider-console reconfiguration is needed. T080's verification step confirms this on the kind cluster. |
| **Existing `/login#fragment` flow breaks during deployment window** | Low | Medium — users mid-OAuth-flow during deploy could see fragment-in-login that the new login page no longer handles | Backwards compatibility: T046's `/login/page.tsx` modification PRESERVES the existing fragment-handling logic at lines 92-128 (the inventory confirms this is the current login page's OAuth fragment reader). The new flow uses the dedicated callback page; the old flow at `/login` still works for any user mid-flow. After one release, the fragment-handler code at `/login/page.tsx` can be removed (deferred — not in this feature). |
| **Anti-enumeration regression** | Medium (developers might accidentally surface email-existence info in error messages) | High — Constitution Rule 35 violation | T078's `test_email_enumeration_resistance.py` is a comprehensive negative test verifying byte-equivalent responses for new vs existing emails on register, verify-email, resend-verification, forgot-password. CI fails the build on any divergence. |
| **Rate-limit thresholds not configured for the register endpoint** | Medium | Medium — abuse via signup spam | T002's verification step + T005's adjustment if needed; T079's `test_rate_limiting.py` E2E test verifies the 429 + Retry-After response empirically. |
| **Translation drift** | Low (feature 083 already enforces this) | Low | T063-T064 add the new strings to all 7 catalogs in the same PR; the existing CI translation-drift check from feature 083 fails the build if any catalog falls out of sync. |
| **`pending_profile_completion` enum value collision** | Very Low | Low | The PostgreSQL `userstatus` enum is owned by the accounts BC; the migration is small and reversible-by-design (ALTER TYPE ADD VALUE — leaves the value in place harmlessly). |
| **OAuth state token expired during slow user click** | Medium | Low (graceful UX) | T040's `<OAuthCallbackHandler>` reads `?error=expired_state` from the new callback URL and renders the error page with a "Retry sign-up" CTA; the existing `oauth_service.py:241` validation logic is unchanged. |
| **Multiple browser tabs of `/verify-email/pending`** | Low | Low (each tab polls independently) | The polling cadence (5s with backoff to 30s per research R8) means at most 6 requests per minute per tab — well within rate limits. |
| **CAPTCHA placeholder confusing** | Low | Low | T035's `<CaptchaWidget>` renders nothing when no provider is configured (no visible widget); when a provider is later configured, the widget appears automatically. |
| **First-time OAuth user dismisses profile-completion** | Medium | Medium — user is stuck in `pending_profile_completion` | T053's `<ProfileCompletionForm>` cannot be dismissed (no Cancel button); the backend's `PATCH /me` endpoint enforces the state transition; the user MUST submit the form to proceed. |
| **`/signup` accessed by an authenticated user** | Low | Low (UX confusion) | T015's `/signup/page.tsx` server-side checks the auth cookie and redirects to `/home` if already signed in; same pattern as the existing login page's behaviour. |

## Open Questions

These do NOT block the plan but should be tracked:

- **Q1**: Should `/profile-completion` be reachable from the user-settings page for users who want to edit locale/timezone after onboarding? **Working assumption**: NO — once the user is `active`, they edit profile via `/settings` (or whatever the user-settings page is in feature 064 / UPD-013). The `/profile-completion` page is ONLY for `pending_profile_completion` users.
- **Q2**: Should the verification email contain a localized body based on the user's `Accept-Language` from the signup request? **Working assumption**: YES (per FR-589 "the message template is localized") — the existing email service `accounts/email.py` delegates to a notification client; the localization is already implemented in the notification BC if it exists, OR is a follow-up if not (defer to feature 077's notification template ownership).
- **Q3**: Should `/waiting-approval` show a real-time countdown or just an estimated review time? **Working assumption**: just an estimated review time (configurable per tenant); a real-time countdown is over-engineering.
- **Q4**: Should the OAuth callback's MFA-required path land on a dedicated `/login/mfa` page or reuse the existing MFA challenge UI from feature 017? **Working assumption**: reuse the existing UI (the URL `/login/mfa` is the existing path; no new page needed).
- **Q5**: Should `<OAuthLinkList>` show provider icons or just text? **Working assumption**: icons (matches the existing `<OAuthProviderButtons>` design).
- **Q6**: Should the admin OAuth provider page's test-connectivity action perform a REAL OAuth flow (requires a test browser session) or just validate the configuration? **Working assumption**: validate configuration only — the test-connectivity calls the provider's authorize URL with a dry-run state token and confirms the response is HTTP 200 (no actual OAuth completion). Real-OAuth-flow validation is a follow-up.
- **Q7**: The existing `(main)/admin/` route (from feature 027) is being CLEAN-CUT-DELETED by feature 086 / UPD-036's T086 task. UPD-037's `/settings/account/connections` page lives under `(main)/settings/account/` — does this conflict with feature 086's clean-cut? **Working assumption**: NO — feature 086 deletes `(main)/admin/`, NOT `(main)/settings/`. UPD-037's `connections` page is unaffected by UPD-036's clean-cut.

## Cross-Feature Coordination

| Feature | What we need from them | Owner action | Blocking? |
|---|---|---|---|
| **014 (Auth)** | `users` / `user_roles` / `sessions` tables + `RoleType` enum + JWT auth dependency | Already on disk | No |
| **016 (Accounts)** | `register` / `verify-email` / `resend-verification` endpoints + anti-enumeration responses + `EmailVerification` model | Already on disk | No |
| **017 (Login UI)** | Existing `/login` page with `<LoginForm>` + the OAuth fragment-reader at lines 92-128 | Already on disk; T046 modifies the page additively | No |
| **OAuth backend** (`auth/router_oauth.py`, `auth/oauth_service.py`, `auth/services/oauth_providers/{google,github}.py`) | Authorize endpoint, callback endpoint, PKCE flow, state validation, account linking, auto-provisioning | Already on disk; T006 + T007 modify the redirect target | No |
| **083 (Accessibility & i18n)** | next-intl wiring + axe-core CI gate + 7-locale catalog discipline | Already on disk; T063 + T064 add strings | No |
| **085 (Extended E2E)** | `tests/e2e/journeys/conftest.py` fixtures + the existing harness | Already on disk; T065-T080 reuse the harness | No |
| **086 (Admin Workbench)** | `/admin/oauth-providers` page (the OAuthProviderAdminPanel routing) | Pending — UPD-036 lands first | Yes (T010 depends on the page existing) |
| **077 (Notifications)** | The verification email send path + the approval-granted/rejected notification routing | Already on disk; T021 reuses the existing notification client | No |

## Phase Gate

**Plan ready for `/speckit.tasks` when**:
- ✅ Constitutional anchors enumerated and gate verdicts recorded
- ✅ Brownfield-input reconciliations enumerated (12 items)
- ✅ Research decisions R1-R10 documented
- ✅ Wave placement (W12.0/W12A/W12B/W12C/W12D) confirmed
- ✅ Cross-feature coordination matrix populated
- ✅ Risk register populated with mitigations
- ✅ Open questions enumerated (none blocking)

The plan is ready. The next phase (`/speckit.tasks`) breaks the 8-phase implementation order above into ordered, dependency-annotated tasks (T001-T087, indicative).

## Complexity Tracking

> **Filled when Constitution Check has violations that must be justified.**

| Variance | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **`pending_profile_completion` is a NEW enum value** (not a status flag on the existing `active` state) | The state-machine design at `accounts/state_machine.py` is the authoritative model of user lifecycle; adding a status flag on `active` would require every `is_active` check across the codebase to be aware of "active-but-incomplete" — a far worse spread of complexity than one new enum value | A boolean flag like `users.profile_complete` would require auditing every `if user.status == active` check across the platform — high blast radius for low value |
| **`<CaptchaWidget>` is a no-op placeholder** | FR-588 mentions CAPTCHA as admin-activatable; shipping with a no-op placeholder allows admins to flip the flag later without a code change | Hardcoding CAPTCHA logic now would require choosing between hCaptcha + Turnstile + others — best deferred until the platform has a customer-driven preference |
| **7 locale catalogs (not 6 per the brownfield input)** | The on-disk inventory confirms `ja.json` exists; UPD-037 maintains the existing catalog discipline rather than introduce a regression | Skipping `ja.json` would break the existing translation-drift CI check from feature 083 — a clear regression |
| **OAuth callback `_frontend_login_redirect` rename has 4 call sites, not 1** | The error redirects also use the helper; renaming the helper without updating the error redirects would break error UX | A new helper for the error paths only would split the redirect logic across two functions, increasing the surface area for bugs |
