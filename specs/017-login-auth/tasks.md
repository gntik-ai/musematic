# Tasks: Login and Authentication UI

**Input**: Design documents from `specs/017-login-auth/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ui-contracts.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story — each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new dependencies and create foundational files shared by all user stories.

- [X] T001 Install `qrcode.react` and `@types/qrcode.react` in `apps/web/package.json` via `pnpm add qrcode.react @types/qrcode.react`; install shadcn InputOTP via `pnpm dlx shadcn@latest add input-otp` (adds `components/ui/input-otp.tsx`)
- [X] T002 [P] Create `apps/web/lib/schemas/auth-schemas.ts` — Zod schemas: `loginSchema`, `forgotPasswordSchema`, `resetPasswordSchema` (12-char min + uppercase + lowercase + digit + special regex rules matching feature 016), `mfaCodeSchema`, `recoveryCodeSchema`
- [X] T003 [P] Create `apps/web/lib/api/auth.ts` — TypeScript request/response interfaces (`LoginRequest`, `LoginSuccessResponse`, `MfaChallengeResponse`, `LockoutErrorResponse`, `MfaVerifyRequest`, `MfaVerifyResponse`, `PasswordResetRequestBody`, `PasswordResetCompleteRequest`, `PasswordResetCompleteResponse`, `PasswordResetTokenErrorResponse`, `MfaEnrollResponse`, `MfaConfirmRequest`, `MfaConfirmResponse`) and API call functions wrapping `lib/api.ts` from feature 015
- [X] T004 Create `apps/web/app/(auth)/layout.tsx` — minimal centered layout with no app shell: `(auth)` route group renders brand logo, centered card, no sidebar or header

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Custom hooks that all user story components depend on. Must complete before any story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `apps/web/lib/hooks/use-auth-mutations.ts` — 6 TanStack Query `useMutation` hooks: `useLoginMutation`, `useMfaVerifyMutation`, `useForgotPasswordMutation`, `useResetPasswordMutation`, `useMfaEnrollMutation`, `useMfaConfirmMutation`; each uses the matching function from `lib/api/auth.ts` and returns `UseMutationResult<Response, ApiError, Request>`
- [X] T006 [P] Create `apps/web/lib/hooks/use-lockout-countdown.ts` — accepts `{ unlockAt: Date | null; onExpired: () => void }`; runs `setInterval(1000)` in `useEffect`; computes `remainingSeconds = Math.max(0, unlockAt.getTime() - Date.now())`; returns `{ remainingSeconds, remainingFormatted, isExpired }`; calls `onExpired()` when remaining hits 0; cleans up interval on unmount
- [X] T007 [P] Create `apps/web/lib/hooks/use-auth-mutations.test.ts` — unit tests for all 6 mutation hooks using MSW handlers to mock auth API endpoints; verify correct request payloads, success responses, and error handling for each mutation

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Email/Password Login (Priority: P1) 🎯 MVP

**Goal**: Render a login form with email/password fields, inline validation, generic error handling on failure, and redirect to dashboard (or `?redirectTo` deep link) on success.

**Independent Test**: Open `/login`. Submit empty form → inline errors. Submit invalid credentials → "Invalid email or password". Submit valid credentials (non-MFA user) → redirect to dashboard. Press Enter in password field → form submits. Tab through all fields → correct focus order.

- [X] T008 [P] [US1] Create `apps/web/components/features/auth/login-form/LoginForm.tsx` — shadcn `Form`+`FormField`+`Input`+`Button`; email (type=email, autocomplete=email) + password (type=password, autocomplete=current-password) fields; inline `FormMessage` validation; submit calls `useLoginMutation`; shows loading state on submit button; on `INVALID_CREDENTIALS` error displays "Invalid email or password"; on `ACCOUNT_LOCKED` error invokes `onLockout(lockout_seconds)` prop; on MFA challenge invokes `onMfaChallenge(session_token)` prop; on network error displays "Unable to connect to the server…"; Enter in password field submits
- [X] T009 [P] [US1] Create `apps/web/components/features/auth/login-form/LoginForm.test.tsx` — RTL tests: empty submit shows validation errors without firing API; valid submit calls mutation; 401 response shows generic error (not which field); 429 response calls `onLockout`; MFA challenge calls `onMfaChallenge`; Enter in password field submits
- [X] T010 [US1] Create `apps/web/app/(auth)/login/page.tsx` — owns `LoginFlowState` discriminated union (`credentials | mfa_challenge | locked | success`); renders `<LoginForm>` when step=`credentials`; reads `searchParams.get('redirectTo')` (validates starts with `/`); on success calls `useAuthStore().setAuth({ user, accessToken, refreshToken })` then `router.push(redirectTo ?? '/dashboard')`; shows success toast if `searchParams.get('message') === 'password_updated'`; includes "Forgot password?" link to `/forgot-password`

**Checkpoint**: US1 fully functional — users can log in with email/password

---

## Phase 4: User Story 2 — TOTP MFA Verification Step (Priority: P1)

**Goal**: After valid credentials for an MFA-enrolled user, transition to a 6-digit code input step; verify code and complete authentication; support recovery code toggle.

**Independent Test**: Log in with MFA-enrolled test credentials → TOTP step appears. Enter 6-digit code → auto-submits → redirects. Enter invalid code → error, input cleared. Click "Use a recovery code instead" → input changes to text field. Submit valid recovery code → authentication completes + "One recovery code has been used" toast.

- [X] T011 [P] [US2] Create `apps/web/components/features/auth/login-form/MfaChallengeForm.tsx` — renders shadcn `InputOTP` (6 slots, `inputMode="numeric"`) when `useRecoveryCode=false`; auto-submits when all 6 slots filled; renders single `Input` when `useRecoveryCode=true` (no auto-submit); "Use a recovery code instead" / "Use authenticator code" toggle link; submit button disabled while loading; on `INVALID_CODE` error clears input and shows "Invalid verification code"; on success invokes `onSuccess({ user, accessToken, refreshToken, recovery_code_consumed })` prop; "Back to login" link invokes `onBack()` prop; focus moves to input on mount
- [X] T012 [P] [US2] Create `apps/web/components/features/auth/login-form/MfaChallengeForm.test.tsx` — RTL tests: 6-digit complete input auto-submits; paste of 6 digits auto-submits; invalid code clears input and shows error; recovery code toggle switches input type; back link calls `onBack`
- [X] T013 [US2] Wire `MfaChallengeForm` into `apps/web/app/(auth)/login/page.tsx` — when `LoginFlowState.step === 'mfa_challenge'`, render `<MfaChallengeForm sessionToken={state.sessionToken} onSuccess={...} onBack={...} />`; `onSuccess` calls `authStore.setAuth()` + redirect (with `recovery_code_consumed` toast if applicable); `onBack` resets state to `credentials`

**Checkpoint**: US1 + US2 functional — full two-step login works for MFA-enrolled users

---

## Phase 5: User Story 3 — Account Lockout Feedback (Priority: P1)

**Goal**: When the backend returns a lockout error, display a real-time countdown from backend-provided `lockout_seconds`; re-enable the form when the countdown expires.

**Independent Test**: After lockout error response (e.g., mock 429 with `lockout_seconds: 60`): lockout message appears with "Account temporarily locked. Try again in 1:00". Timer counts down every second. Submit button is disabled. At 0, form re-enables and lockout message disappears.

- [X] T014 [P] [US3] Create `apps/web/components/features/auth/login-form/LockoutMessage.tsx` — accepts `{ unlockAt: Date; onExpired: () => void }`; uses `useLockoutCountdown` hook; renders "Account temporarily locked. Try again in [remainingFormatted]"; countdown element has `aria-live="polite"`; container has `role="status"`
- [X] T015 [P] [US3] Create `apps/web/components/features/auth/login-form/LockoutMessage.test.tsx` — RTL tests: renders countdown from `unlockAt`; countdown updates each second (use fake timers); calls `onExpired` when time runs out
- [X] T016 [P] [US3] Create `apps/web/lib/hooks/use-lockout-countdown.test.ts` — unit tests with `vi.useFakeTimers()`: returns correct `remainingSeconds` and `remainingFormatted`; calls `onExpired` exactly once at expiry; cleans up interval on unmount; handles `unlockAt = null` (returns isExpired=true immediately)
- [X] T017 [US3] Wire `LockoutMessage` into `apps/web/app/(auth)/login/page.tsx` — when `LoginFlowState.step === 'locked'`, render `<LockoutMessage unlockAt={state.unlockAt} onExpired={() => setState({ step: 'credentials' })} />`; `LoginForm.onLockout` receives `lockout_seconds`, computes `unlockAt = new Date(Date.now() + lockout_seconds * 1000)`, sets state to `locked`

**Checkpoint**: US1 + US2 + US3 functional — complete login page with lockout handling

---

## Phase 6: User Story 4 — Password Reset Flow (Priority: P2)

**Goal**: "Forgot password?" link leads to an email form with anti-enumeration response; valid reset link leads to a new-password form with per-rule strength indicators; success redirects to login with toast; expired link shows error with "Request a new link" option.

**Independent Test**: Click "Forgot password?" → form with email field. Submit any email → identical "If an account exists…" message. Navigate to reset link → new password form with 5 strength rule indicators. Type weak password → failing rules shown. Type valid password + confirm → submit succeeds → `/login?message=password_updated`. Navigate to expired token → error with "Request a new link" button → navigates to `/forgot-password`.

- [X] T018 [P] [US4] Create `apps/web/components/features/auth/password-reset/ForgotPasswordForm.tsx` — shadcn Form with email `Input`; submit fires `useForgotPasswordMutation`; on any API response (success or error) transitions to confirmation state showing "If an account exists with this email, a reset link has been sent" — identical regardless of email existence; "Back to login" link navigates to `/login`
- [X] T019 [P] [US4] Create `apps/web/components/features/auth/password-reset/ForgotPasswordForm.test.tsx` — RTL tests: invalid email shows inline validation; valid submit shows confirmation on any response (200, 404, 500); confirmation message is identical for all cases
- [X] T020 [US4] Create `apps/web/app/(auth)/forgot-password/page.tsx` — renders `<ForgotPasswordForm />`; minimal page with heading "Forgot your password?"
- [X] T021 [P] [US4] Create `apps/web/components/features/auth/password-reset/ResetPasswordForm.tsx` — shadcn Form with `newPassword` and `confirmPassword` `Input` fields; real-time per-rule strength indicators (5 rules: min 12 chars, uppercase, lowercase, digit, special char) rendered as icon+text list updating as user types; submit button disabled until all rules pass and passwords match; fires `useResetPasswordMutation` with `{ token, new_password }`; on success calls `router.push('/login?message=password_updated')`; on `TOKEN_EXPIRED`/`TOKEN_ALREADY_USED` error renders error message + "Request a new link" button linking to `/forgot-password`
- [X] T022 [P] [US4] Create `apps/web/components/features/auth/password-reset/ResetPasswordForm.test.tsx` — RTL tests: each strength rule shows ✓/✗ independently; submit disabled when rules fail; submit disabled when passwords don't match; success navigates to login with message param; token expired shows error + request-new-link button
- [X] T023 [US4] Create `apps/web/app/(auth)/reset-password/[token]/page.tsx` — reads `params.token` from route; renders `<ResetPasswordForm token={token} />`; handles initial page load with valid vs. invalid token (the form itself handles the error state returned by the API on submit)
- [X] T024 [US4] Update `apps/web/app/(auth)/login/page.tsx` to read `searchParams.get('message') === 'password_updated'` on mount and show a shadcn `toast` notification: "Password updated. Please log in."

**Checkpoint**: US1–US4 functional — full login + password reset flows work

---

## Phase 7: User Story 5 — MFA Enrollment Dialog (Priority: P2)

**Goal**: Post-login dialog for users without MFA prompts them to enroll; shows QR code + secret key, verifies code, displays recovery codes with mandatory acknowledgment; dialog cannot be dismissed without acknowledging; enrollment accessible from user settings.

**Independent Test**: Log in as user with `mfaEnrolled=false` → enrollment dialog appears. QR code and secret key render. Enter valid 6-digit code → recovery codes appear. Close button absent; ESC dismissed → dialog stays open (acknowledgment pulse). Check acknowledgment → "Complete setup" enables → click → dialog closes → `user.mfaEnrolled` becomes `true`. Log out and back in → MFA step now required.

- [X] T025 [P] [US5] Create `apps/web/components/features/auth/mfa-enrollment/QrCodeStep.tsx` — fires `useMfaEnrollMutation` on mount; shows skeleton while loading; renders `<QRCodeSVG value={provisioningUri} size={200} />` from `qrcode.react`; shows secret key in `<code>` tag (monospace, copyable); "Next" button advances to verification step; "Skip for now" button (conditionally shown) closes dialog
- [X] T026 [P] [US5] Create `apps/web/components/features/auth/mfa-enrollment/VerificationStep.tsx` — shadcn `InputOTP` (6 slots); auto-submits when complete; fires `useMfaConfirmMutation`; on success passes `recoveryCodes` to parent state; on error shows "Incorrect code. Please try again." and clears input; "Back" button returns to QR step
- [X] T027 [P] [US5] Create `apps/web/components/features/auth/mfa-enrollment/RecoveryCodesStep.tsx` — displays `recoveryCodes` array in monospace list; "Copy all codes" button copies all codes as newline-separated text and briefly shows "Copied!"; acknowledgment `Checkbox` labeled "I have saved my recovery codes in a safe place"; "Complete setup" `Button` disabled until checkbox checked; on complete calls `onComplete()` prop
- [X] T028 [P] [US5] Create `apps/web/components/features/auth/mfa-enrollment/RecoveryCodesStep.test.tsx` — RTL tests: "Complete setup" disabled until checkbox checked; "Copy all codes" copies text to clipboard; calls `onComplete` after acknowledgment + button click
- [X] T029 [US5] Create `apps/web/components/features/auth/mfa-enrollment/MfaEnrollmentDialog.tsx` — shadcn `Dialog` with `open` controlled prop (no `DialogClose` button, `onInteractOutside` and `onEscapeKeyDown` both call `e.preventDefault()`); manages `MfaEnrollmentStep` state (`qr_display → verification → recovery_codes → complete`); renders the appropriate step component; on `complete` calls `onEnrolled()` prop; on acknowledgment in `RecoveryCodesStep` calls `onEnrolled()`; if user attempts to close during `recovery_codes` step, the acknowledgment checkbox animates with a pulse class
- [X] T030 [US5] Create `apps/web/components/features/auth/mfa-enrollment/MfaEnrollmentDialog.test.tsx` — RTL tests: dialog renders when `open=true`; step transitions from QR → verification on "Next"; step transitions verification → recovery codes on success; dialog cannot be closed during recovery codes step (ESC and outside click both blocked); `onEnrolled` called after acknowledgment + "Complete setup"
- [X] T031 [US5] Modify `apps/web/app/(main)/layout.tsx` — import `MfaEnrollmentDialog`; add `const user = useAuthStore(s => s.user)`; render `{user && !user.mfaEnrolled && <MfaEnrollmentDialog open onEnrolled={() => authStore.setUser({ ...user, mfaEnrolled: true })} />}` after the main page content

**Checkpoint**: All 5 user stories functional — complete login and auth UI

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode, responsive verification, TypeScript/ESLint clean, E2E coverage.

- [ ] T032 [P] Verify and fix keyboard navigation Tab order on all auth pages (`/login`, `/forgot-password`, `/reset-password/[token]`): confirm Tab sequence matches visual order, Enter submits forms, focus moves to code input on MFA step transition; fix any focus traps or missing `aria-label` attributes in `apps/web/components/features/auth/`
- [ ] T033 [P] Verify and fix dark mode rendering on all auth pages and dialogs: toggle `.dark` class in browser, confirm no un-themed elements (white-on-white, missing `text-foreground`, hardcoded colors) in `apps/web/components/features/auth/` and `apps/web/app/(auth)/`
- [ ] T034 [P] Verify and fix responsive layout 320px–2560px: check `/login`, `/forgot-password`, `/reset-password`, and enrollment dialog at 320px, 768px, 1440px, 2560px; ensure no horizontal scrolling, no overlapping elements; fix any Tailwind utility issues
- [ ] T035 [P] Run `tsc --noEmit` from `apps/web/` and fix all TypeScript strict-mode errors in auth components and hooks
- [ ] T036 [P] Run `pnpm lint` from `apps/web/` and fix all ESLint errors in auth components, hooks, and pages
- [X] T037 Write Playwright E2E test in `apps/web/e2e/auth/login.spec.ts` covering: credential login → dashboard redirect, deep link preservation via `?redirectTo`, generic error message on bad credentials, MFA step appears for enrolled user, lockout message after repeated failures
- [X] T038 Write Playwright E2E test in `apps/web/e2e/auth/mfa-enrollment.spec.ts` covering: enrollment dialog appears for user without MFA, QR code renders, verification code entry advances to recovery codes, dialog blocks closure without acknowledgment, enrollment completes and dialog closes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001–T004) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 complete
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (`login/page.tsx` must exist to wire into)
- **US3 (Phase 5)**: Depends on Phase 2 + US1 (`login/page.tsx` must exist to wire into)
- **US4 (Phase 6)**: Depends on Phase 2 only — independent of US1/US2/US3
- **US5 (Phase 7)**: Depends on Phase 2 only — independent of US1–US4 (wires into `(main)/layout.tsx`, not login page)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Foundational complete → start immediately. No US dependencies.
- **US2 (P1)**: Foundational + US1 complete → `MfaChallengeForm` wires into `LoginPage`
- **US3 (P1)**: Foundational + US1 complete → `LockoutMessage` wires into `LoginPage`
- **US4 (P2)**: Foundational complete → independent (own routes, no overlap with US1–US3)
- **US5 (P2)**: Foundational complete → independent (wires into `(main)/layout.tsx`)

### Within Each User Story

- Component files [P] can be written in parallel with their test files [P]
- Login page integration tasks (T010, T013, T017, T024) must follow their component tasks
- MFA enrollment dialog (T029) must follow step components (T025–T027)

### Parallel Opportunities

- T002 and T003 (schemas + API types): different files, run in parallel
- T005 and T006 (mutation hooks + countdown hook): different files, run in parallel
- Within US1: T008 (LoginForm) and T009 (LoginForm tests) in parallel
- Within US2: T011 (MfaChallengeForm) and T012 (tests) in parallel
- Within US3: T014, T015, T016 all in parallel
- Within US4: T018+T019, T021+T022 in parallel pairs; T020+T023 after their forms
- Within US5: T025, T026, T027+T028 in parallel
- US4 (P2) and US5 (P2) can be worked in parallel by two developers after Phase 2 completes
- Phase 8 tasks T032–T036 are all parallel (different concerns)

---

## Parallel Example: Phase 2 + US4 + US5 Concurrent

```bash
# After Phase 2 completes, three workstreams can run in parallel:

# Workstream A — US1+US2+US3 (login page)
Task T008: Create LoginForm.tsx
Task T009: Create LoginForm.test.tsx  # parallel with T008
  → Task T010: Create login/page.tsx
    → Task T011: Create MfaChallengeForm.tsx
    → Task T013: Wire MfaChallengeForm into login/page.tsx
    → Task T014: Create LockoutMessage.tsx
    → Task T017: Wire LockoutMessage into login/page.tsx

# Workstream B — US4 (password reset)
Task T018: Create ForgotPasswordForm.tsx
Task T019: Create ForgotPasswordForm.test.tsx  # parallel with T018
Task T021: Create ResetPasswordForm.tsx
Task T022: Create ResetPasswordForm.test.tsx  # parallel with T021
  → Task T020: Create forgot-password/page.tsx
  → Task T023: Create reset-password/[token]/page.tsx
  → Task T024: Update login/page.tsx for success toast

# Workstream C — US5 (MFA enrollment)
Task T025: Create QrCodeStep.tsx
Task T026: Create VerificationStep.tsx  # parallel with T025
Task T027: Create RecoveryCodesStep.tsx
Task T028: Create RecoveryCodesStep.test.tsx  # parallel with T027
  → Task T029: Create MfaEnrollmentDialog.tsx
  → Task T030: Create MfaEnrollmentDialog.test.tsx
  → Task T031: Modify (main)/layout.tsx
```

---

## Implementation Strategy

### MVP First (US1 Only — Working Login)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T007)
3. Complete Phase 3: US1 (T008–T010)
4. **STOP and VALIDATE**: Users can log in with email/password
5. Demo-ready at this point — all other stories are additive

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. + US1 (T008–T010) → Working login → **MVP**
3. + US2 (T011–T013) → MFA-enrolled users can log in
4. + US3 (T014–T017) → Locked accounts handled gracefully
5. + US4 (T018–T024) → Self-service password reset
6. + US5 (T025–T031) → MFA enrollment for new users
7. Phase 8 → Production-ready (a11y, dark mode, responsive, TypeScript clean)

### Parallel Team Strategy (2 Developers)

- **Dev A**: Phase 1 → Phase 2 (shared) → US1 → US2 → US3
- **Dev B**: Phase 1 → Phase 2 (shared) → US4 + US5 (parallel, different routes)
- Both merge for Phase 8

---

## Notes

- [P] tasks operate on different files and have no dependencies on incomplete tasks
- Each user story phase ends with a wiring task that integrates the story's components
- US2 and US3 both wire into `login/page.tsx` — sequence them (US2 first, then US3) or merge as a single wiring step
- US4 and US5 have no overlap with the login page — can be fully parallel after Phase 2
- Verify quickstart.md test scenarios after each story phase checkpoint
- Commit after each phase or logical group
