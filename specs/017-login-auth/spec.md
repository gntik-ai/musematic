# Feature Specification: Login and Authentication UI

**Feature Branch**: `017-login-auth`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Login page with email/password, TOTP MFA step, lockout handling, password reset flow, and MFA enrollment dialog."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Email/Password Login (Priority: P1)

A user navigates to the login page and enters their email and password. The system validates the credentials against the backend authentication service. On success, the user receives a token pair and is redirected to the main application dashboard. On failure, the user sees an error message that does not reveal whether the email or password was incorrect. The login form is accessible, keyboard-navigable, and responsive across device sizes.

**Why this priority**: Login is the gateway to the entire application. No other UI feature is usable without authentication. This is the absolute minimum for a functional frontend.

**Independent Test**: Open the login page. Enter valid credentials. Verify redirection to the dashboard. Enter invalid credentials. Verify a generic error message appears. Tab through all form fields. Verify keyboard navigation works. Resize to mobile. Verify the form remains usable.

**Acceptance Scenarios**:

1. **Given** a user on the login page, **When** they enter a valid email and password and submit, **Then** they are authenticated and redirected to the main application within 3 seconds
2. **Given** a user on the login page, **When** they enter incorrect credentials, **Then** an error message appears ("Invalid email or password") without revealing which field was wrong
3. **Given** the login form, **When** the user submits with an empty email or password, **Then** inline validation errors appear before the request is sent to the server
4. **Given** the login form, **When** the user presses Enter in the password field, **Then** the form submits (no need to click the button)
5. **Given** the login page in dark mode, **When** it renders, **Then** all elements use the dark theme tokens with no un-themed elements

---

### User Story 2 — TOTP MFA Verification Step (Priority: P1)

When a user with MFA enrolled submits valid credentials, the backend responds with a challenge indicating MFA is required. The login form transitions to a second step showing a 6-digit TOTP code input. The user enters their code from their authenticator app. On valid code, authentication completes and the user is redirected to the dashboard. On invalid code, an error message appears. The user can also use a recovery code if they have lost access to their authenticator app.

**Why this priority**: MFA verification is inseparable from login — if a user has MFA enrolled, they cannot access the application without completing this step. This must ship alongside the login form.

**Independent Test**: Log in with credentials for an MFA-enrolled user. Verify the MFA code input appears. Enter a valid 6-digit code. Verify authentication completes. Enter an invalid code. Verify an error message appears. Click "Use recovery code". Verify the input switches to accept a recovery code string.

**Acceptance Scenarios**:

1. **Given** valid credentials for an MFA-enrolled user, **When** the login form submits, **Then** a TOTP verification step appears with a 6-digit code input field
2. **Given** the MFA step is displayed, **When** the user enters a valid 6-digit code and submits, **Then** authentication completes and the user is redirected to the dashboard
3. **Given** the MFA step is displayed, **When** the user enters an invalid code, **Then** an error message ("Invalid verification code") appears and the input is cleared for retry
4. **Given** the MFA step, **When** the user clicks "Use a recovery code instead", **Then** the input changes to a single text field accepting a recovery code string
5. **Given** a valid recovery code, **When** submitted, **Then** authentication completes and the user is warned that one recovery code has been consumed

---

### User Story 3 — Account Lockout Feedback (Priority: P1)

When a user's account is locked due to repeated failed login attempts, the login form displays a clear lockout message with the remaining lockout duration. The countdown updates in real time so the user knows when they can retry. While locked, the login button is disabled. When the lockout period expires, the form returns to its normal state.

**Why this priority**: Lockout feedback is inseparable from login — without it, locked-out users see confusing generic errors and flood support with tickets. This must ship alongside login.

**Independent Test**: Attempt login 5 times with wrong credentials. Verify the lockout message appears with a countdown timer. Wait for countdown to reach 0. Verify the form re-enables. Verify the countdown updates every second.

**Acceptance Scenarios**:

1. **Given** a user who has exceeded the maximum failed attempts, **When** the backend returns a lockout error, **Then** the form displays "Account temporarily locked. Try again in X minutes" with a real-time countdown
2. **Given** the lockout countdown is displayed, **When** each second passes, **Then** the countdown timer updates visually without page reload
3. **Given** a locked-out account, **When** the lockout period expires, **Then** the login button re-enables and the lockout message disappears
4. **Given** a locked-out account, **When** the user attempts to submit the form, **Then** the submit button is disabled and the form does not send a request

---

### User Story 4 — Password Reset Flow (Priority: P2)

A user who has forgotten their password clicks a "Forgot password?" link on the login page. They enter their email address. The system sends a password reset email (without revealing whether the email is registered — anti-enumeration). The user clicks the reset link from the email, enters a new password meeting strength requirements, and confirms it. On success, they are redirected to the login page with a success message.

**Why this priority**: Password reset is essential for self-service account recovery but the application can function without it temporarily — admins can reset passwords manually. It complements login but is not a blocker for initial use.

**Independent Test**: Click "Forgot password?" on the login page. Enter an email. Verify the confirmation message appears (identical regardless of email existence). Navigate to the reset link. Enter a new password. Verify strength validation appears for weak passwords. Submit a valid new password. Verify redirection to login with a success toast.

**Acceptance Scenarios**:

1. **Given** the login page, **When** the user clicks "Forgot password?", **Then** a form appears asking for their email address
2. **Given** the password reset request form, **When** the user submits any email address, **Then** a confirmation message ("If an account exists with this email, a reset link has been sent") appears — identical regardless of whether the email is registered
3. **Given** a valid password reset link, **When** the user navigates to it, **Then** a form appears with "New password" and "Confirm password" fields
4. **Given** the new password form, **When** the user enters a password that does not meet strength requirements, **Then** inline validation shows specific feedback (minimum length, complexity requirements)
5. **Given** a valid new password, **When** the user submits the reset form, **Then** the password is updated, and they are redirected to the login page with a success message ("Password updated. Please log in.")
6. **Given** an expired or already-used reset link, **When** the user navigates to it, **Then** an error message appears with an option to request a new reset link

---

### User Story 5 — MFA Enrollment Dialog (Priority: P2)

After logging in, a user who does not yet have MFA enrolled sees an MFA enrollment prompt (optionally skippable if MFA is not mandatory). The enrollment flow shows a QR code that the user scans with their authenticator app, asks them to verify by entering a 6-digit code, and upon success displays recovery codes. The user must acknowledge the recovery codes before completing enrollment. MFA enrollment is also accessible from user settings for users who skipped the initial prompt.

**Why this priority**: MFA enrollment is important for security posture but users can access the application without it if MFA is not enforced. It enhances the login experience but is not a prerequisite for initial functionality.

**Independent Test**: Log in as a user without MFA. Verify the enrollment prompt appears. Scan the QR code with an authenticator. Enter the 6-digit verification code. Verify recovery codes are displayed. Acknowledge recovery codes. Verify enrollment is complete. Log out and log back in — verify MFA step is now required.

**Acceptance Scenarios**:

1. **Given** a user without MFA enrolled who just logged in, **When** the dashboard loads, **Then** an MFA enrollment dialog appears with an option to enroll now or skip (if MFA is not mandatory)
2. **Given** the MFA enrollment dialog, **When** the user chooses to enroll, **Then** a QR code is displayed along with a text-based secret key for manual entry
3. **Given** the QR code is displayed, **When** the user enters a valid 6-digit code from their authenticator, **Then** enrollment is confirmed and recovery codes are displayed
4. **Given** recovery codes are displayed, **When** the user clicks "I have saved my recovery codes", **Then** enrollment completes and the dialog closes
5. **Given** recovery codes are displayed, **When** the user attempts to close the dialog without acknowledging, **Then** the dialog prevents closure and highlights the acknowledgment requirement
6. **Given** a user who previously skipped MFA enrollment, **When** they access their user settings, **Then** they can initiate MFA enrollment from the settings page

---

### Edge Cases

- What happens when the user's session token expires during login? The form remains usable — login does not require an existing session. If the token refresh fails during post-login navigation, the user is redirected back to login.
- What happens when the backend is unreachable during login? An error message ("Unable to connect to the server. Please check your connection and try again.") appears. The form remains interactive so the user can retry.
- What happens when the user pastes a 6-digit MFA code? The paste is accepted and auto-submits if all 6 digits are present.
- What happens when the user navigates directly to a protected page without being logged in? The authentication guard redirects to login. After successful login, the user is redirected to the originally requested page (stored in a URL parameter or session).
- What happens when the QR code fails to load during MFA enrollment? A fallback text-based secret key is always shown alongside the QR code, so manual entry is always possible.
- What happens when the user closes the browser during MFA enrollment? Enrollment is not complete until verification. The user can restart enrollment on next login.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Application MUST provide a login form with email and password fields, a submit button, and a "Forgot password?" link
- **FR-002**: Login form MUST validate email format and non-empty password before submitting to the server
- **FR-003**: On successful authentication (no MFA), the system MUST store the token pair securely and redirect the user to the dashboard or their originally requested page
- **FR-004**: On failed authentication, the system MUST show a generic error message that does not distinguish between incorrect email and incorrect password
- **FR-005**: When the backend indicates MFA is required, the login flow MUST transition to a 6-digit TOTP code input step without requiring the user to re-enter credentials
- **FR-006**: MFA verification MUST support both TOTP codes and recovery codes, with a toggle to switch between them
- **FR-007**: When the backend returns a lockout error, the login form MUST display the remaining lockout duration as a real-time countdown and disable the submit button
- **FR-008**: Application MUST provide a password reset request flow that accepts an email and shows an anti-enumeration confirmation message
- **FR-009**: Application MUST provide a password reset completion form with new password, confirm password, and inline strength validation
- **FR-010**: Password reset links MUST show an appropriate error when expired or already used, with an option to request a new link
- **FR-011**: Application MUST provide an MFA enrollment flow showing a QR code, verification code input, and recovery code display with mandatory acknowledgment
- **FR-012**: MFA enrollment MUST be presented as a post-login dialog for users without MFA, with an option to skip if MFA is not mandatory
- **FR-013**: All login and authentication UI elements MUST support keyboard navigation and screen reader accessibility
- **FR-014**: All login and authentication UI elements MUST render correctly in both light and dark modes
- **FR-015**: All login and authentication UI elements MUST be responsive from 320px to 2560px viewport width
- **FR-016**: After login redirection, the authentication state (user profile, tokens) MUST be available to all application components via the client state store
- **FR-017**: The login page MUST display the brand theme (logo, colors, typography) consistent with the application design system

### Key Entities

- **LoginForm**: The primary credential input — email, password, submit action, error state, loading state.
- **MfaChallenge**: The second authentication step — TOTP code input, recovery code toggle, verification action.
- **LockoutState**: The lockout feedback — locked status, remaining duration, countdown timer.
- **PasswordResetRequest**: The "forgot password" flow — email input, confirmation message.
- **PasswordResetCompletion**: The reset link landing — new password, confirm password, strength validation.
- **MfaEnrollment**: The setup flow — QR code display, secret key fallback, verification code, recovery codes, acknowledgment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users complete the login flow (enter credentials to reaching the dashboard) in under 5 seconds for non-MFA accounts and under 15 seconds for MFA accounts
- **SC-002**: Lockout countdown updates every second with no visible lag or flicker
- **SC-003**: The MFA enrollment flow (QR scan to recovery code acknowledgment) completes in under 60 seconds
- **SC-004**: Password reset flow (request to new password set) is completable in under 3 minutes
- **SC-005**: 100% of login and authentication UI elements are keyboard-navigable without requiring a mouse
- **SC-006**: 100% of login and authentication UI elements render correctly in dark mode with no un-themed elements
- **SC-007**: Login form loads and is interactive within 2 seconds on standard broadband connections
- **SC-008**: Error messages for failed login, lockout, and expired reset links are clear enough that users do not need to contact support to understand the issue
- **SC-009**: The login page renders correctly on viewports from 320px (mobile) to 2560px (ultrawide) with no horizontal scrolling or overlapping elements
- **SC-010**: After successful login, the user's previous navigation intent (deep link) is preserved and they reach the originally requested page

## Assumptions

- The backend authentication API (feature 014 — auth bounded context) is available and provides endpoints for login (`POST /login`), MFA verification (`POST /mfa/verify`), MFA enrollment (`POST /mfa/enroll`, `POST /mfa/confirm`), token refresh (`POST /refresh`), and password reset (endpoint to be determined — assumed `POST /password-reset/request` and `POST /password-reset/complete`)
- The frontend scaffold (feature 015 — Next.js App Scaffold) is available with: the `(auth)` route group layout, the API client (`lib/api.ts`) with JWT injection and token refresh, the auth Zustand store (`store/auth-store.ts`), the theme system (dark mode via CSS custom properties), and the form library integration
- JWT access tokens are stored in memory (Zustand auth store) — not in localStorage or cookies — consistent with the auth store design from feature 015 (only refresh token is persisted to localStorage). This means a page refresh requires a silent token refresh using the persisted refresh token.
- Password strength requirements match the backend: minimum 12 characters, at least one uppercase, one lowercase, one digit, and one special character — consistent with the accounts bounded context (feature 016)
- The MFA enrollment QR code is generated by the backend and returned as a data URI or provisioning URI that the frontend renders using a QR code library. The backend handles secret generation — the frontend only displays it.
- The lockout duration is returned by the backend in the error response (in seconds). The frontend calculates the countdown display from this value using client-side timers — no polling of the backend during lockout.
- "Forgot password?" and password reset completion pages live under the `(auth)` route group (no app shell — same as the login page).
- MFA enrollment dialog appears as a modal overlay on the `(main)` layout (after successful login, not on the login page itself).
