# Data Model: Login and Authentication UI

**Feature**: 017-login-auth  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## TypeScript Types

### Login Flow State (Local Component State)

```typescript
// app/(auth)/login/_types.ts

/** Discriminated union representing the multi-step login flow */
export type LoginFlowState =
  | { step: 'credentials'; error?: string }
  | { step: 'mfa_challenge'; sessionToken: string; error?: string }
  | { step: 'locked'; unlockAt: Date }
  | { step: 'success' };

/** Login form field values */
export interface LoginFormValues {
  email: string;
  password: string;
}

/** MFA challenge form values */
export interface MfaChallengeFormValues {
  code: string;               // 6-digit TOTP code
  useRecoveryCode: boolean;
}
```

### Password Reset State (Local Component State)

```typescript
// app/(auth)/forgot-password/_types.ts

/** Forgot password form */
export interface ForgotPasswordFormValues {
  email: string;
}

// app/(auth)/reset-password/_types.ts

/** Password reset completion form */
export interface ResetPasswordFormValues {
  newPassword: string;
  confirmPassword: string;
}

/** State for the password reset page */
export type ResetPasswordState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success' }
  | { status: 'link_expired' };
```

### MFA Enrollment State (Local Component State)

```typescript
// components/features/auth/mfa-enrollment/_types.ts

/** Multi-step enrollment dialog state */
export type MfaEnrollmentStep =
  | 'qr_display'
  | 'verification'
  | 'recovery_codes'
  | 'complete';

export interface MfaEnrollmentState {
  step: MfaEnrollmentStep;
  provisioningUri: string;       // otpauth://totp/... URI from backend
  secretKey: string;             // Plain text secret for manual entry
  recoveryCodes: string[];       // Shown after verification
  recoveryCodesAcknowledged: boolean;
  error?: string;
}
```

### Lockout State (Derived from Login Flow State)

```typescript
// Computed from LoginFlowState when step === 'locked'
export interface LockoutDisplayState {
  remainingSeconds: number;
  remainingFormatted: string;    // e.g., "4:32" or "45s"
  isExpired: boolean;
}
```

---

## API Request / Response Types

### Login

```typescript
// lib/api/auth.ts

export interface LoginRequest {
  email: string;
  password: string;
}

/** Returned on successful credential validation when MFA is NOT required */
export interface LoginSuccessResponse {
  access_token: string;
  refresh_token: string;
  user: AuthUser;
}

/** Returned when MFA verification is required */
export interface MfaChallengeResponse {
  mfa_required: true;
  session_token: string;       // Short-lived token for the MFA step
}

export type LoginResponse = LoginSuccessResponse | MfaChallengeResponse;

/** Lockout error response body (HTTP 429) */
export interface LockoutErrorResponse {
  code: 'ACCOUNT_LOCKED';
  lockout_seconds: number;     // Frontend derives unlockAt from this
}

/** Generic auth error (HTTP 401) */
export interface AuthErrorResponse {
  code: 'INVALID_CREDENTIALS';
  message: string;
}
```

### MFA Verification

```typescript
export interface MfaVerifyRequest {
  session_token: string;
  code: string;
  use_recovery_code?: boolean;
}

export interface MfaVerifyResponse {
  access_token: string;
  refresh_token: string;
  user: AuthUser;
  recovery_code_consumed?: boolean;  // true if a recovery code was used
}
```

### Password Reset

```typescript
export interface PasswordResetRequestBody {
  email: string;
}

// Always returns 202 (anti-enumeration — no meaningful response body)

export interface PasswordResetCompleteRequest {
  token: string;               // From URL path param
  new_password: string;
}

export interface PasswordResetCompleteResponse {
  success: true;
}

/** Returned when reset token is expired or already used (HTTP 400) */
export interface PasswordResetTokenErrorResponse {
  code: 'TOKEN_EXPIRED' | 'TOKEN_ALREADY_USED';
}
```

### MFA Enrollment

```typescript
export interface MfaEnrollResponse {
  provisioning_uri: string;    // otpauth://totp/...
  secret_key: string;          // Base32 secret for manual entry
}

export interface MfaConfirmRequest {
  code: string;                // 6-digit verification code
}

export interface MfaConfirmResponse {
  recovery_codes: string[];    // Array of one-time recovery codes
}
```

---

## Zod Validation Schemas

```typescript
// lib/schemas/auth-schemas.ts

import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

export const forgotPasswordSchema = z.object({
  email: z.string().email('Enter a valid email address'),
});

export const resetPasswordSchema = z.object({
  newPassword: z
    .string()
    .min(12, 'Minimum 12 characters')
    .regex(/[A-Z]/, 'At least one uppercase letter')
    .regex(/[a-z]/, 'At least one lowercase letter')
    .regex(/[0-9]/, 'At least one digit')
    .regex(/[^A-Za-z0-9]/, 'At least one special character'),
  confirmPassword: z.string(),
}).refine(
  (data) => data.newPassword === data.confirmPassword,
  { message: 'Passwords do not match', path: ['confirmPassword'] },
);

export const mfaCodeSchema = z.object({
  code: z.string().regex(/^\d{6}$/, 'Enter a 6-digit code'),
  useRecoveryCode: z.boolean().default(false),
});

export const recoveryCodeSchema = z.object({
  code: z.string().min(1, 'Recovery code is required'),
  useRecoveryCode: z.literal(true),
});

export const mfaInputSchema = z.discriminatedUnion('useRecoveryCode', [
  mfaCodeSchema,
  recoveryCodeSchema,
]);
```

---

## Component Tree

```text
app/(auth)/
├── layout.tsx                          # Minimal centered layout (no app shell)
├── login/
│   └── page.tsx                        # LoginPage — orchestrates flow state
└── forgot-password/
│   └── page.tsx                        # ForgotPasswordPage
└── reset-password/
    └── [token]/
        └── page.tsx                    # ResetPasswordPage

components/features/auth/
├── login-form/
│   ├── LoginForm.tsx                   # Credentials step (email + password)
│   ├── MfaChallengeForm.tsx            # 6-digit code input (step 2)
│   └── LockoutMessage.tsx              # Countdown display
├── password-reset/
│   ├── ForgotPasswordForm.tsx          # Email input + anti-enum confirmation
│   └── ResetPasswordForm.tsx           # New password + confirm + strength
└── mfa-enrollment/
    ├── MfaEnrollmentDialog.tsx         # Dialog wrapper (controls open state)
    ├── QrCodeStep.tsx                  # QR code + secret key display
    ├── VerificationStep.tsx            # 6-digit code verify
    └── RecoveryCodesStep.tsx           # Display + acknowledgment

lib/hooks/
├── use-auth-mutations.ts               # TanStack Query mutations for all auth actions
└── use-lockout-countdown.ts            # setInterval-based countdown hook
```

---

## Hook Interfaces

### `use-lockout-countdown.ts`

```typescript
interface UseLockoutCountdownOptions {
  unlockAt: Date | null;
  onExpired: () => void;
}

interface UseLockoutCountdownResult {
  remainingSeconds: number;
  remainingFormatted: string;    // "M:SS" format
  isExpired: boolean;
}

function useLockoutCountdown(options: UseLockoutCountdownOptions): UseLockoutCountdownResult
```

### `use-auth-mutations.ts`

```typescript
function useLoginMutation(): UseMutationResult<LoginResponse, ApiError, LoginRequest>
function useMfaVerifyMutation(): UseMutationResult<MfaVerifyResponse, ApiError, MfaVerifyRequest>
function useForgotPasswordMutation(): UseMutationResult<void, ApiError, PasswordResetRequestBody>
function useResetPasswordMutation(): UseMutationResult<PasswordResetCompleteResponse, ApiError, PasswordResetCompleteRequest>
function useMfaEnrollMutation(): UseMutationResult<MfaEnrollResponse, ApiError, void>
function useMfaConfirmMutation(): UseMutationResult<MfaConfirmResponse, ApiError, MfaConfirmRequest>
```

---

## Auth Store Integration (feature 015)

The login page calls these auth store actions (already defined in feature 015):

```typescript
// store/auth-store.ts (feature 015 — not modified)
interface AuthStoreActions {
  setAuth: (payload: { user: AuthUser; accessToken: string; refreshToken: string }) => void;
  clearAuth: () => void;
}

// AuthUser shape (already defined in feature 015)
interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  roles: RoleType[];
  mfaEnrolled: boolean;
  workspaceId: string;
}
```
