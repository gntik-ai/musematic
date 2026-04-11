# Quickstart: Login and Authentication UI

**Feature**: 017-login-auth  
**Date**: 2026-04-11

## Prerequisites

- Feature 015 (Next.js App Scaffold) must be complete — the scaffold provides the API client, auth store, route groups, and shadcn/ui setup.
- Feature 014 (Auth Bounded Context) backend must be running on `http://localhost:8000` (or configured via `NEXT_PUBLIC_API_URL`).
- `apps/web/` directory exists with all scaffold files.

## Install New Dependencies

```bash
cd apps/web
pnpm add qrcode.react
pnpm add -D @types/qrcode.react
```

If `input-otp` is not already installed (shadcn InputOTP):
```bash
pnpm dlx shadcn@latest add input-otp
```

## Run the Dev Server

```bash
cd apps/web
pnpm dev
```

Navigate to `http://localhost:3000/login`.

## Verify: Basic Login Form

1. Open `http://localhost:3000/login`
2. Verify the page renders with email input, password input, "Sign in" button, and "Forgot password?" link
3. Submit with empty fields — verify inline validation errors appear
4. Submit with valid test credentials — verify redirect to dashboard

## Verify: MFA Step

1. Log in with credentials for an MFA-enrolled test user
2. Verify the credential form transitions to the TOTP step
3. Enter a 6-digit code — verify it auto-submits when 6 digits are entered
4. Verify authentication completes and redirects to dashboard
5. Click "Use a recovery code instead" — verify the input changes to a text field

## Verify: Lockout Countdown

1. Submit incorrect credentials 5 times
2. Verify the lockout message appears with a countdown timer in `M:SS` format
3. Verify the submit button is disabled
4. Verify the timer counts down every second (watch for 2-3 seconds)
5. (Optional, with short test lockout): Verify the form re-enables when the timer reaches 0

## Verify: Dark Mode

```bash
# In browser dev tools console:
document.documentElement.classList.add('dark')
```

Verify all login page elements (inputs, labels, buttons, error messages, links) use dark theme tokens with no un-themed elements (white text on white background, etc.).

## Verify: Forgot Password Flow

1. Click "Forgot password?" on the login page
2. Enter any email address (registered or not)
3. Verify the confirmation message appears: "If an account exists with this email, a reset link has been sent"
4. Verify the message is identical regardless of whether the email is registered

## Verify: Reset Password Page

```bash
# Generate a test reset token from the backend (or use the backend API directly)
curl -X POST http://localhost:8000/api/v1/password-reset/request \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

1. Navigate to the reset link from the email (or manually construct `/reset-password/<token>`)
2. Verify both "New password" and "Confirm password" fields render
3. Type a weak password — verify per-rule strength indicators appear
4. Type a valid password — verify all strength indicators show ✓
5. Type a mismatched confirm password — verify inline error
6. Submit a valid password — verify redirect to `/login?message=password_updated`
7. Verify the success toast appears on the login page

## Verify: Expired Reset Link

1. Navigate to `/reset-password/invalid-or-expired-token`
2. Verify an error message appears with a "Request a new link" button
3. Click "Request a new link" — verify redirect to `/forgot-password`

## Verify: Deep Link Preservation

1. While logged out, navigate to `http://localhost:3000/some/protected/page`
2. Verify redirect to `/login?redirectTo=/some/protected/page`
3. Log in successfully
4. Verify redirect to `/some/protected/page` (not the default dashboard)

## Verify: MFA Enrollment Dialog

1. Log in as a test user without MFA enrolled
2. Verify the MFA enrollment dialog appears on the dashboard
3. Verify a QR code and secret key are displayed
4. Enter the code from your authenticator — verify transition to recovery codes step
5. Verify 8-10 recovery codes are displayed
6. Try to click "Complete setup" without checking the acknowledgment checkbox — verify button is disabled
7. Check the acknowledgment checkbox — verify "Complete setup" enables
8. Click "Complete setup" — verify dialog closes
9. Log out and log back in — verify the MFA step is now required

## Run Tests

```bash
cd apps/web

# Unit + component tests
pnpm test

# With coverage
pnpm test:coverage

# E2E (requires dev server running)
pnpm test:e2e
```

## Key Test Files

```text
apps/web/
├── components/features/auth/login-form/
│   ├── LoginForm.test.tsx              # Credential validation, error display
│   ├── MfaChallengeForm.test.tsx       # Code input, auto-submit, recovery toggle
│   └── LockoutMessage.test.tsx         # Countdown timer, form disable
├── components/features/auth/password-reset/
│   ├── ForgotPasswordForm.test.tsx     # Anti-enumeration, form reset
│   └── ResetPasswordForm.test.tsx      # Strength validation, token error
├── components/features/auth/mfa-enrollment/
│   ├── MfaEnrollmentDialog.test.tsx    # Step transitions, close prevention
│   └── RecoveryCodesStep.test.tsx      # Acknowledgment requirement
└── lib/hooks/
    ├── use-auth-mutations.test.ts      # Mutation hooks with MSW
    └── use-lockout-countdown.test.ts   # Timer logic
```
