# UI Contracts: Login and Authentication UI

**Feature**: 017-login-auth  
**Date**: 2026-04-11  
**Phase**: 1 — Design

These contracts define observable component behavior — what renders, what state transitions occur, and what the user experiences. They are technology-agnostic within the frontend stack.

---

## Contract 1: LoginForm

**Component**: `components/features/auth/login-form/LoginForm.tsx`

**Renders**:
- Email input (type `email`, autocomplete `email`, required)
- Password input (type `password`, autocomplete `current-password`, required)
- "Forgot password?" link → navigates to `/forgot-password`
- Submit button ("Sign in") — disabled while submitting
- Error message area (initially hidden)

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Submit with empty email | Inline validation: "Enter a valid email address" before request |
| Submit with empty password | Inline validation: "Password is required" before request |
| Submit with valid values | Button shows loading state; request fires |
| API returns 401 (invalid credentials) | Error: "Invalid email or password" — generic, does not distinguish field |
| API returns MFA challenge | Parent transitions flow state to `mfa_challenge` step |
| API returns 429 lockout | Parent transitions flow state to `locked` step |
| API returns network error | Error: "Unable to connect to the server. Please check your connection and try again." |
| Press Enter in password field | Form submits |
| Tab navigation | Focus moves: email → password → submit → "Forgot password?" link |

**Accessibility**:
- All inputs have visible labels
- Error messages have `role="alert"` for screen reader announcement
- Submit button `aria-busy="true"` while loading

---

## Contract 2: MfaChallengeForm

**Component**: `components/features/auth/login-form/MfaChallengeForm.tsx`

**Renders**:
- Heading: "Two-factor authentication"
- Description: "Enter the 6-digit code from your authenticator app"
- Code input — `inputMode="numeric"`, `maxLength={6}` OR shadcn `InputOTP` component
- "Use a recovery code instead" toggle link
- Submit button ("Verify") — disabled while submitting or when input < 6 digits
- Error message area
- "Back to login" link

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Input length reaches 6 (non-recovery mode) | Auto-submits verification request |
| Paste of 6-digit code | Code fills input; auto-submit fires |
| Submit with invalid code | Input cleared; error: "Invalid verification code" |
| Toggle "Use a recovery code instead" | Input clears and switches to single text input accepting any string; submit no longer auto-fires |
| Submit valid recovery code | Authentication completes; toast: "One recovery code has been used" |
| Submit valid TOTP code | Authentication completes; redirects to dashboard or `redirectTo` |
| "Back to login" clicked | Parent resets flow state to `credentials` step |

**Accessibility**:
- Focus moves to code input on step transition
- Toggle link has clear `aria-label`

---

## Contract 3: LockoutMessage

**Component**: `components/features/auth/login-form/LockoutMessage.tsx`

**Renders**:
- Message: "Account temporarily locked. Try again in [countdown]"
- Countdown in format `M:SS` (e.g., "4:32") or `Xs` for < 60 seconds
- Submit button remains disabled while lockout is active
- No form inputs visible (or all disabled)

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Each second passes | Countdown updates without page reload |
| Countdown reaches 0 | Parent transitions flow state back to `credentials`; form re-enables |
| User attempts form submission | No request sent; submit remains disabled |

**Accessibility**:
- Countdown has `aria-live="polite"` so screen readers announce updates without interruption
- Lockout message has `role="status"`

---

## Contract 4: ForgotPasswordForm

**Component**: `components/features/auth/password-reset/ForgotPasswordForm.tsx`

**Renders**:
- Heading: "Forgot your password?"
- Description: "Enter your email and we'll send you a reset link"
- Email input (type `email`, required)
- Submit button ("Send reset link") — disabled while submitting
- "Back to login" link
- Confirmation state: "If an account exists with this email, a reset link has been sent"

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Submit with invalid email | Inline validation before request |
| Submit with any valid email | Button shows loading; on API response (any), shows confirmation message |
| Confirmation shown | Form hidden; confirmation message displayed — identical regardless of email registration |
| "Back to login" clicked | Navigate to `/login` |

**Anti-enumeration**: The confirmation message is always identical. The component must NOT change its message or behavior based on whether the email exists.

---

## Contract 5: ResetPasswordForm

**Component**: `components/features/auth/password-reset/ResetPasswordForm.tsx`

**Renders**:
- Heading: "Set new password"
- New password input (type `password`) with strength indicators
- Confirm password input (type `password`)
- Submit button ("Update password") — disabled while submitting or validation fails
- Inline strength feedback (per-rule indicators):
  - ✓/✗ Minimum 12 characters
  - ✓/✗ Uppercase letter
  - ✓/✗ Lowercase letter
  - ✓/✗ One digit
  - ✓/✗ Special character

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| New password typed | Strength indicators update in real time |
| Password does not meet all rules | Submit disabled; indicators show which rules fail |
| Confirm password does not match | Inline error: "Passwords do not match" |
| Submit with valid passwords | Button shows loading state |
| API success | Navigate to `/login?message=password_updated`; login page shows: "Password updated. Please log in." |
| API returns TOKEN_EXPIRED or TOKEN_ALREADY_USED | Error state with message and "Request a new link" button |

---

## Contract 6: MfaEnrollmentDialog

**Component**: `components/features/auth/mfa-enrollment/MfaEnrollmentDialog.tsx`

**Renders**: A modal `Dialog` (shadcn/ui) with 3 steps — QR display, verification, recovery codes.

**Dialog open/close rules**:
- Opens automatically after login if `user.mfaEnrolled === false`
- Cannot be dismissed (no close button, overlay click disabled) until enrollment is complete OR user skips (if skip allowed)
- After recovery codes acknowledged → enrollment complete → dialog closes → user reaches dashboard

---

## Contract 7: QrCodeStep

**Component**: `components/features/auth/mfa-enrollment/QrCodeStep.tsx`

**Renders**:
- Heading: "Set up authenticator"
- Instructions: "Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)"
- QR code SVG (rendered via `qrcode.react` from provisioning URI)
- Fallback text: "Can't scan? Enter this code manually:" + secret key in monospace
- "Next" button → advances to verification step
- "Skip for now" button (if MFA is not mandatory) → closes dialog

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Dialog opens | `useMfaEnrollMutation` fires immediately to fetch provisioning URI |
| Provisioning URI loading | QR area shows skeleton loader |
| Provisioning URI loaded | QR code and secret key render |
| "Next" clicked | Step transitions to `verification` |
| "Skip for now" clicked | Dialog closes; user reaches dashboard without MFA |

---

## Contract 8: VerificationStep

**Component**: `components/features/auth/mfa-enrollment/VerificationStep.tsx`

**Renders**:
- Heading: "Verify setup"
- Instructions: "Enter the 6-digit code from your authenticator app to confirm setup"
- Code input (`inputMode="numeric"`, maxLength=6)
- "Verify" button — disabled while loading
- "Back" button → returns to QR step
- Error area

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| 6-digit code entered | Auto-submits OR user presses "Verify" |
| API success | Step transitions to `recovery_codes` |
| API error (invalid code) | Error: "Incorrect code. Please try again." Input cleared. |

---

## Contract 9: RecoveryCodesStep

**Component**: `components/features/auth/mfa-enrollment/RecoveryCodesStep.tsx`

**Renders**:
- Heading: "Save your recovery codes"
- Warning: "Store these codes somewhere safe. Each code can only be used once."
- Recovery codes list (monospace, copyable)
- "Copy all codes" button
- Acknowledgment checkbox: "I have saved my recovery codes in a safe place"
- "Complete setup" button — disabled until acknowledgment checkbox is checked

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| "Copy all codes" clicked | Codes copied to clipboard; button shows "Copied!" briefly |
| Acknowledgment unchecked + "Complete setup" clicked | Button remains disabled; checkbox highlights |
| Acknowledgment checked | "Complete setup" button enables |
| "Complete setup" clicked | `user.mfaEnrolled` updated in auth store; dialog closes |
| User attempts to close dialog (if OS provides escape) | Dialog stays open; acknowledgment checkbox animates (pulse) to indicate requirement |

---

## Contract 10: Authentication Guard (existing — used by this feature)

**Location**: `app/(main)/layout.tsx` (feature 015)

**Behavior additions for this feature**:

| Trigger | Outcome |
|---------|---------|
| Unauthenticated user navigates to protected route | Redirect to `/login?redirectTo=<original_path>` |
| Authenticated user with `mfaEnrolled === false` | Render `MfaEnrollmentDialog` overlaid on the page |
| Authenticated user with `mfaEnrolled === true` | Normal page render; no enrollment dialog |

---

## Contract 11: Login Success Notification on Password Reset

**Location**: `app/(auth)/login/page.tsx`

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Page loads with `?message=password_updated` | Toast notification: "Password updated. Please log in." |

---

## Contract 12: Recovery Code Warning Toast

**Location**: After `useMfaVerifyMutation` success with `recovery_code_consumed: true`

**Behavior**:

| Trigger | Outcome |
|---------|---------|
| Recovery code successfully used | After redirect: toast "One recovery code has been used. Consider generating new codes in settings." |
