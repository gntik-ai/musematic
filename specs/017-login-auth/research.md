# Research: Login and Authentication UI

**Feature**: 017-login-auth  
**Date**: 2026-04-11  
**Phase**: 0 — Pre-design research

---

## Decision 1: Route Group — Login Pages Belong in `(auth)`, Not `(main)`

**Decision**: All login and authentication pages live under `app/(auth)/`. This includes: `app/(auth)/login/page.tsx`, `app/(auth)/forgot-password/page.tsx`, `app/(auth)/reset-password/[token]/page.tsx`. The MFA enrollment dialog is an overlay on the `(main)` layout (post-login, not a separate route). The `(auth)/layout.tsx` renders a minimal centered layout with no app shell (sidebar/header absent).

**Rationale**: Feature 015 established the `(auth)` route group for unauthenticated pages specifically to prevent the app shell from rendering during login. The user input mentioned `app/(main)/login-auth/` but that is incorrect — `(main)` wraps the authenticated shell. Login must be `(auth)`.

**Alternatives considered**:
- `app/(main)/login-auth/`: Causes app shell (sidebar, header) to render on login page. Rejected — contradicts the route group architecture from feature 015.
- Single root `app/login/page.tsx` without a route group: Loses layout separation; root layout would need conditional shell rendering. Rejected.

---

## Decision 2: Login Flow State Machine — React State (not Zustand)

**Decision**: Login flow state is managed locally in the `LoginPage` component using `React.useState` with a discriminated union:

```typescript
type LoginFlowState =
  | { step: 'credentials'; error?: string }
  | { step: 'mfa_challenge'; sessionToken: string; error?: string }
  | { step: 'locked'; unlockAt: Date }
  | { step: 'success' }
```

The `sessionToken` from the MFA challenge response is held in this local state (not Zustand) — it is a short-lived in-flight value, not persistent auth state. Once login completes, the auth store (`store/auth-store.ts` from feature 015) is populated with the real access/refresh token pair.

**Rationale**: The login flow is ephemeral UI state scoped to a single page. It does not need to be shared across components or persist. Putting it in Zustand would pollute the global store with transient UI state. React local state is sufficient, simpler, and correctly scoped.

**Alternatives considered**:
- Zustand store for login flow: Unnecessary global state for transient UI. Rejected.
- XState finite state machine: Adds a dependency for a 4-state machine; React useState + discriminated union is sufficient. Rejected.
- URL-based state (search params): Login step state does not belong in the URL — it's not bookmarkable. Rejected.

---

## Decision 3: MFA Code Input — Single Input with Maxlength (not 6 Separate Boxes)

**Decision**: The TOTP 6-digit input is rendered as a **single `<Input type="text" maxLength={6} inputMode="numeric" pattern="\d{6}" />`** from shadcn/ui. On paste, the value is accepted as-is. Auto-submit fires when the input length reaches 6. This is simpler than 6 separate boxes.

**Rationale**: The spec edge case states "pasted 6-digit code is accepted and auto-submits." A single input naturally handles paste. Six separate inputs require complex focus management, paste splitting logic, and backspace handling — significant complexity for no user experience gain on desktop. The `inputMode="numeric"` triggers the numeric keyboard on mobile without restricting paste.

**Alternatives considered**:
- 6 individual digit inputs: Complex focus management, harder to paste correctly, same UX outcome. Rejected.
- shadcn OTP input (InputOTP): This is a valid option — shadcn includes an `InputOTP` component built on `input-otp`. Accepted as an **upgrade option** — prefer `InputOTP` if already installed in the scaffold, fallback to single input.
- `<input type="number">`: Does not support leading zeros and strips them. Rejected.

---

## Decision 4: Lockout Countdown — `useEffect` + `setInterval` (no backend polling)

**Decision**: When the backend returns a lockout error with `lockout_seconds: number`, the frontend computes `unlockAt = new Date(Date.now() + lockout_seconds * 1000)` and stores it in local flow state. A `useEffect` runs a `setInterval` every 1000ms, computing `remaining = Math.max(0, unlockAt - Date.now())` and updating a display string. When remaining reaches 0, the `LoginFlowState` transitions back to `credentials`.

**Rationale**: The spec assumption states "the frontend calculates the countdown display from this value using client-side timers — no polling of the backend during lockout." This matches exactly.

**Alternatives considered**:
- Polling `GET /auth/status` every second: Unnecessary backend load; spec explicitly prohibits this. Rejected.
- Redux-style global timer: Overkill for a single countdown. Rejected.
- CSS animations only: Cannot re-enable the form at expiry without JavaScript. Rejected.

---

## Decision 5: Password Strength Validation — Zod Regex (matches backend rules from feature 016)

**Decision**: Password strength is validated client-side using Zod:
```typescript
const passwordSchema = z.string()
  .min(12, 'Minimum 12 characters')
  .regex(/[A-Z]/, 'At least one uppercase letter')
  .regex(/[a-z]/, 'At least one lowercase letter')
  .regex(/[0-9]/, 'At least one digit')
  .regex(/[^A-Za-z0-9]/, 'At least one special character')
```

This mirrors the backend validation in feature 016 (`accounts` bounded context) exactly.

**Rationale**: The spec assumption states "Password strength requirements match the backend: minimum 12 characters, at least one uppercase, one lowercase, one digit, and one special character." Using Zod inline validators (rather than a library like `zxcvbn`) keeps the dependency count low and exactly mirrors the backend rules.

**Alternatives considered**:
- `zxcvbn` library: Entropy-based scoring; does not enforce deterministic rules. Backend uses deterministic rules. Rejected.
- Custom regex only: Zod provides structured error messages per rule. Preferred.
- HTML5 `pattern` attribute only: Cannot show per-rule feedback. Rejected.

---

## Decision 6: QR Code Rendering — `qrcode.react` Library

**Decision**: Use `qrcode.react` to render the TOTP provisioning URI as a QR code in the MFA enrollment dialog. The backend returns a `provisioning_uri` (e.g., `otpauth://totp/...`). The frontend renders `<QRCodeSVG value={provisioningUri} size={200} />`. The secret key is always displayed as a text field alongside the QR code for manual entry.

**Rationale**: `qrcode.react` is the standard, well-maintained React QR code library. It renders via SVG (accessible, scalable, no canvas required). The spec assumption states the backend returns a provisioning URI or data URI — `qrcode.react` handles provisioning URIs natively.

**Alternatives considered**:
- `react-qr-code`: Similar alternative; `qrcode.react` is more widely used with better TypeScript types. Accepted either.
- Rendering QR on backend (as image): Extra backend work; frontend can render client-side from the URI. Rejected.
- Canvas-based QR: SVG is more accessible and scalable. Rejected.

---

## Decision 7: Deep Link Preservation — `redirectTo` Search Parameter

**Decision**: When the auth guard in `(main)/layout.tsx` detects an unauthenticated user, it redirects to `/login?redirectTo=/original/path`. After successful login, the login page reads `searchParams.get('redirectTo')` and calls `router.push(redirectTo ?? '/dashboard')`. The `redirectTo` value is validated to start with `/` (relative paths only) to prevent open redirect attacks.

**Rationale**: The spec edge case states "after successful login, the user is redirected to the originally requested page (stored in a URL parameter or session)." URL parameter is simpler than session storage and works across tabs.

**Alternatives considered**:
- `sessionStorage`: Doesn't work if the user opens the login link in a new tab. Rejected.
- `localStorage`: Persists too long; URL param is naturally scoped to the current navigation. Rejected.
- Next.js `useSearchParams`: Used in the login page component to read `redirectTo`.

---

## Decision 8: Form Library — React Hook Form + Zod via shadcn Form Integration

**Decision**: All auth forms (login, forgot-password, reset-password) use `react-hook-form` with `zodResolver` integrated via the `shadcn/ui` Form components (`Form`, `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormMessage`). This is the exact pattern from feature 015 (constitution mandate).

**Rationale**: Constitution mandates React Hook Form + Zod. Feature 015 establishes the shadcn Form integration. No new decision required — consistency with existing scaffold.

**Alternatives considered**: None — constitution-mandated stack.

---

## Decision 9: Token Storage — Access Token in Zustand Memory, Refresh in localStorage

**Decision**: On successful authentication, the login page calls the `useAuthStore` (feature 015) to set `accessToken` (memory only) and `refreshToken` (persisted to localStorage via Zustand persist middleware). This is the existing auth store contract from feature 015. The login page does not manage tokens directly — it calls `authStore.setAuth({ user, accessToken, refreshToken })`.

**Rationale**: The spec assumption states "JWT access tokens are stored in memory (Zustand auth store) — not in localStorage or cookies — consistent with the auth store design from feature 015." Feature 015 already built this store; this feature only calls it.

**Alternatives considered**: None — feature 015 defines the storage contract.

---

## Decision 10: MFA Enrollment — Modal Dialog in `(main)` Layout

**Decision**: The MFA enrollment prompt is rendered as a `shadcn/ui Dialog` (modal) in `app/(main)/layout.tsx`. It checks `authStore.user.mfaEnrolled` after login. If `false` and the backend indicates enrollment is optional (feature flag from user profile), it shows the enrollment dialog. The dialog has three steps: QR display → verification code → recovery codes + acknowledgment. Dialog cannot be dismissed without acknowledging recovery codes (controlled `open` prop).

**Rationale**: The spec states "MFA enrollment dialog appears as a modal overlay on the `(main)` layout." The spec also requires that the dialog prevents closure without acknowledgment (FR-011 + US5 scenario 5).

**Alternatives considered**:
- Separate `/enroll-mfa` route: Would require a separate page load; modal provides a better inline experience. Rejected.
- Client-side interstitial page: More complex routing; modal is standard for post-login flows. Rejected.

---

## Decision 11: API Integration — TanStack Query Mutations for All Auth Actions

**Decision**: All auth API calls (login, MFA verify, password reset request, password reset complete, MFA enroll, MFA confirm) are wrapped in TanStack Query `useMutation` hooks in `lib/hooks/use-auth-mutations.ts`. Mutations use the `api` client from `lib/api.ts` (feature 015). Errors are surfaced via `mutation.error` typed as `ApiError`.

**Rationale**: Constitution mandates TanStack Query v5 for server state. Feature 015 established `lib/hooks/use-api.ts` factory pattern. Auth mutations follow the same pattern for consistency.

**Alternatives considered**:
- Direct `fetch` calls in components: Duplicates loading/error state management. Rejected.
- `useEffect` + `useState` for async: Anti-pattern with TanStack Query in scope. Rejected.
