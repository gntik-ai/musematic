# Feature Specification: Auth Bounded Context — Authentication, Authorization, and Session Management

**Feature Branch**: `014-auth-bounded-context`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement authentication (email/password with Argon2id), JWT token management (RS256), session management (Redis-backed), MFA (TOTP), lockout/throttling, RBAC engine with 10 roles, purpose-bound authorization, and service account API key management."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Email/Password Login with JWT Issuance (Priority: P1)

A platform user enters their email and password to log in. The system verifies the password against the stored hash, checks whether the account is locked, and if valid, creates a session and issues a JWT token pair (short-lived access token + long-lived refresh token). The access token is used for all subsequent requests. When it expires, the client presents the refresh token to obtain a new access token without re-entering credentials. Users can log out (destroying the current session) or log out of all devices (destroying all sessions).

**Why this priority**: Authentication is the gateway to the entire platform. No other feature can function without users being able to prove their identity. This is the absolute minimum for any user-facing functionality.

**Independent Test**: Register a user with email and password. Call the login endpoint with correct credentials. Verify a JWT access token (short-lived) and refresh token (long-lived) are returned. Call a protected endpoint using the access token. Wait for access token expiration, then use the refresh token to obtain a new access token. Call logout and verify the session is invalidated.

**Acceptance Scenarios**:

1. **Given** a registered user with valid credentials, **When** they submit email and password to the login endpoint, **Then** the system verifies the password hash, creates a session, and returns a JWT pair (access token + refresh token) with correct claims and expiration times
2. **Given** a user with a valid refresh token, **When** the access token has expired and they submit the refresh token to the refresh endpoint, **Then** a new access token is issued without requiring re-authentication
3. **Given** a logged-in user, **When** they call the logout endpoint, **Then** the current session is destroyed and the associated tokens are invalidated
4. **Given** a user logged in on multiple devices, **When** they call the logout-all endpoint, **Then** all sessions for that user are destroyed and all tokens are invalidated
5. **Given** a user submitting incorrect credentials, **When** the password verification fails, **Then** the system returns an authentication error without revealing whether the email or password was wrong

---

### User Story 2 — Account Lockout and Throttling (Priority: P1)

When a user repeatedly fails authentication attempts, the system progressively locks their account to prevent brute-force attacks. After a configurable number of failed attempts (default: 5), the account is locked for a configurable duration (default: 15 minutes). Each failed attempt is recorded with metadata (timestamp, IP, user agent) for audit purposes. Successful authentication resets the failure counter. The system emits events when accounts are locked, enabling operators to detect attack patterns.

**Why this priority**: Lockout is inseparable from login — shipping login without brute-force protection is a security vulnerability. Both must ship together.

**Independent Test**: Attempt login with wrong password 5 times consecutively. Verify the account becomes locked. Attempt login with correct password while locked. Verify it is rejected with a lockout message. Wait for the lockout duration to expire. Verify login works again with correct credentials.

**Acceptance Scenarios**:

1. **Given** a user account with zero failed attempts, **When** they fail authentication 5 times consecutively, **Then** the account is locked for 15 minutes and an event is emitted
2. **Given** a locked account, **When** the user attempts to log in with correct credentials during the lockout period, **Then** the login is rejected with a message indicating the account is temporarily locked
3. **Given** a locked account, **When** the lockout duration expires, **Then** the user can log in successfully with correct credentials and the failure counter is reset
4. **Given** a user who failed 3 times, **When** they successfully authenticate, **Then** the failure counter resets to zero
5. **Given** a failed login attempt, **When** the attempt is recorded, **Then** the timestamp, originating address, and user agent are stored for audit purposes

---

### User Story 3 — Multi-Factor Authentication (TOTP) (Priority: P2)

Users can enable multi-factor authentication for additional security. During enrollment, the system generates a TOTP secret and presents it as both a manual key and a QR code URI compatible with authenticator apps (Google Authenticator, Authy). Recovery codes are also generated for situations where the authenticator device is unavailable. After enrollment, all login attempts require a TOTP code as a second factor. Recovery codes can be used once as an alternative to the TOTP code.

**Why this priority**: MFA strengthens security but is an opt-in enhancement. Users can authenticate with email/password alone (US1) while MFA support is being built.

**Independent Test**: Enroll a user in MFA. Verify a TOTP secret and recovery codes are generated. Log in with email/password. Verify the system challenges for a TOTP code. Submit a valid TOTP code. Verify access is granted. Attempt login with an invalid TOTP code. Verify access is denied. Use a recovery code instead of TOTP. Verify it works once and cannot be reused.

**Acceptance Scenarios**:

1. **Given** an authenticated user without MFA, **When** they call the MFA enrollment endpoint, **Then** the system generates a TOTP secret, QR code URI, and a set of single-use recovery codes
2. **Given** a user with MFA enabled, **When** they submit correct email/password, **Then** the system challenges for a TOTP code before issuing tokens
3. **Given** the MFA challenge, **When** the user submits a valid TOTP code from their authenticator app, **Then** authentication succeeds and a session is created
4. **Given** the MFA challenge, **When** the user submits an invalid or expired TOTP code, **Then** authentication is rejected
5. **Given** a user who has lost their authenticator device, **When** they submit a valid recovery code, **Then** authentication succeeds and that recovery code is consumed (cannot be reused)
6. **Given** a user with MFA enabled, **When** they verify MFA enrollment with a valid TOTP code, **Then** MFA is activated and the enrollment is confirmed

---

### User Story 4 — Role-Based Access Control (Priority: P1)

The platform enforces access control through a role hierarchy with 10 predefined roles. Each role grants a specific set of permissions defining what resources can be accessed and what actions can be performed. When a user attempts an action, the RBAC engine checks their role permissions against the requested resource type, action, and scope. Unauthorized actions are rejected with a clear denial reason. Roles can be scoped to specific workspaces, allowing users to hold different roles in different workspaces.

**Why this priority**: Authorization is a security-critical function that must exist alongside authentication. Without RBAC, all authenticated users would have unrestricted access to all resources.

**Independent Test**: Assign a user the "viewer" role in a workspace. Attempt to read a resource (allowed). Attempt to modify a resource (denied with 403). Change the user's role to "editor". Verify the modification now succeeds. Verify a "superadmin" can perform any action.

**Acceptance Scenarios**:

1. **Given** a user with the "viewer" role, **When** they attempt a read action on a resource they can view, **Then** access is granted
2. **Given** a user with the "viewer" role, **When** they attempt a write action, **Then** access is denied with a clear permission error
3. **Given** a user with a workspace-scoped role, **When** they attempt to access a resource in a different workspace, **Then** access is denied
4. **Given** a superadmin user, **When** they attempt any action on any resource, **Then** access is always granted
5. **Given** a permission check request, **When** the RBAC engine evaluates it, **Then** the decision includes the role, resource type, action, scope, and whether it was allowed or denied

---

### User Story 5 — Purpose-Bound Authorization (Priority: P2)

Agents (AI agents, not human users) have a declared purpose that constrains what actions they can perform. When an agent attempts an action, the system checks whether the action aligns with the agent's declared purpose. This prevents agents from performing actions outside their intended scope, even if their role permissions would technically allow it. Purpose-bound checks supplement (not replace) RBAC — both must pass for an action to be authorized.

**Why this priority**: Purpose-bound authorization is an agent-specific security layer. Human users are governed by RBAC alone, so this can be built after core RBAC is in place.

**Independent Test**: Create an agent with purpose "data-analysis". Attempt a data query action (allowed by both RBAC and purpose). Attempt a resource deletion action (allowed by RBAC but outside declared purpose). Verify the deletion is denied with a purpose violation error.

**Acceptance Scenarios**:

1. **Given** an agent with a declared purpose, **When** it attempts an action aligned with its purpose and permitted by RBAC, **Then** the action is authorized
2. **Given** an agent with a declared purpose, **When** it attempts an action not aligned with its purpose (even if RBAC permits it), **Then** the action is denied with a purpose violation error
3. **Given** a human user (not an agent), **When** they attempt an action, **Then** only RBAC is checked (purpose-bound does not apply)
4. **Given** a purpose-bound denial, **When** the denial is recorded, **Then** it includes the agent identity, declared purpose, attempted action, and denial reason

---

### User Story 6 — Service Account API Key Authentication (Priority: P2)

Automated systems and external integrations authenticate via service account API keys instead of email/password. A platform administrator creates a service account with a designated role and generates an API key. The API key is presented as a header in requests. The system validates the key, resolves the associated role, and applies standard RBAC. API keys can be rotated (generating a new key while invalidating the old one) and revoked entirely.

**Why this priority**: Service accounts are needed for system integrations and CI/CD pipelines, but human user authentication (US1) covers the initial launch. Service accounts can be added once the core auth flow is stable.

**Independent Test**: Create a service account with the "service_account" role. Generate an API key. Make a request using the API key header. Verify the request is authenticated and the associated role is applied. Rotate the API key. Verify the old key is rejected and the new key works. Revoke the service account. Verify all requests with that key are rejected.

**Acceptance Scenarios**:

1. **Given** a valid service account API key, **When** it is submitted in the request header, **Then** the system authenticates the request and applies the service account's role
2. **Given** an API key that has been rotated, **When** the old key is used, **Then** authentication fails
3. **Given** a revoked service account, **When** any API key for that account is used, **Then** authentication fails
4. **Given** a service account with a specific role, **When** it makes a request, **Then** standard RBAC permissions for that role are enforced
5. **Given** a platform administrator, **When** they create a service account, **Then** the system generates a unique, securely random API key that is shown once and stored as a hash

---

### Edge Cases

- What happens when a user attempts to log in with an email that doesn't exist? The system returns the same generic "invalid credentials" error to prevent email enumeration.
- What happens when the session store is unavailable? Authentication fails gracefully with a service unavailable error. Users cannot log in until the session store recovers. Existing tokens that have not expired remain valid for stateless verification.
- What happens when a user's MFA enrollment is interrupted (e.g., they enroll but never verify)? The MFA enrollment remains in "pending" state. MFA is not enforced until the user completes verification. Pending enrollments expire after 10 minutes.
- What happens when all recovery codes are used? The user must contact an administrator to reset MFA, or use an administrative MFA reset flow.
- What happens when a service account API key is compromised? The administrator revokes the key. All active sessions for that service account are immediately invalidated.
- What happens when RBAC permissions are changed while a user has an active session? Permission changes take effect on the next request evaluation. Existing sessions continue but permission checks use the updated role definitions.
- What happens when an agent's purpose definition is updated while it has active executions? In-flight executions continue with the original purpose. New executions use the updated purpose.
- What happens when the signing key is rotated? Tokens signed with the old key remain valid until their natural expiration. New tokens are signed with the new key. A grace period supports both keys simultaneously.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST authenticate users via email and password, verifying the password against a securely stored hash
- **FR-002**: System MUST issue a JWT token pair (short-lived access token with 15-minute expiration and long-lived refresh token with 7-day expiration) upon successful authentication
- **FR-003**: System MUST support token refresh, issuing a new access token when a valid refresh token is presented
- **FR-004**: System MUST support single-session logout (current session) and all-session logout (all devices)
- **FR-005**: System MUST track failed authentication attempts per user and lock accounts after a configurable number of consecutive failures (default: 5)
- **FR-006**: System MUST enforce a configurable lockout duration (default: 15 minutes) during which all login attempts are rejected
- **FR-007**: System MUST support TOTP-based multi-factor authentication enrollment, verification, and challenge
- **FR-008**: System MUST generate single-use recovery codes during MFA enrollment as a backup authentication method
- **FR-009**: System MUST enforce a role-based access control model with 10 predefined roles (superadmin, platform_admin, workspace_owner, workspace_admin, creator, operator, viewer, auditor, agent, service_account)
- **FR-010**: System MUST evaluate permissions based on role, resource type, action, and scope (workspace-level scoping)
- **FR-011**: System MUST enforce purpose-bound authorization for agent identities, denying actions that do not align with the agent's declared purpose
- **FR-012**: System MUST support service account authentication via API keys submitted as request headers
- **FR-013**: System MUST support API key rotation (generate new, invalidate old) and revocation
- **FR-014**: System MUST emit domain events for security-relevant actions: successful authentication, account lockout, session revocation, MFA enrollment, permission denials, and API key rotation
- **FR-015**: System MUST record all authentication attempts (success and failure) with timestamp, origin, and user agent for audit purposes
- **FR-016**: System MUST return generic error messages for authentication failures to prevent information disclosure (email enumeration, password guessing)
- **FR-017**: System MUST support concurrent sessions across multiple devices per user
- **FR-018**: System MUST invalidate all sessions for a service account when the account is revoked

### Key Entities

- **UserCredential**: Stores the user's email and password hash. Linked to a user identity. Contains the hashed password and hash algorithm metadata.
- **Session**: Represents an active authenticated session. Contains user reference, device metadata, creation time, expiration, and last activity timestamp. Stored in a fast key-value store for sub-millisecond lookups.
- **MfaEnrollment**: Tracks a user's MFA configuration including the encrypted TOTP secret, enrollment status (pending/active), and encrypted recovery codes.
- **AuthAttempt**: Audit record of each authentication attempt — success or failure — including timestamp, originating address, user agent, and outcome.
- **PasswordResetToken**: Time-limited token for password reset flows. Contains the token hash, expiration, and whether it has been consumed.
- **ServiceAccountCredential**: Links a service account identity to a hashed API key, its associated role, and lifecycle status (active/rotated/revoked).
- **Permission**: Defines an allowed action for a role on a resource type within a scope. Composed as (role, resource_type, action, scope).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete the full login flow (submit credentials, receive tokens) within 2 seconds under normal load
- **SC-002**: Account lockout engages within 1 second of the threshold failure, preventing further login attempts
- **SC-003**: MFA enrollment (from initiation to verification) can be completed in under 60 seconds by a user with an authenticator app ready
- **SC-004**: RBAC permission checks resolve in under 10 milliseconds per request
- **SC-005**: 100% of failed authentication attempts are recorded in the audit log
- **SC-006**: Zero information leakage — authentication error messages are indistinguishable regardless of whether the email exists
- **SC-007**: Service account API key authentication adds less than 5 milliseconds of latency per request compared to JWT authentication
- **SC-008**: Purpose-bound authorization checks add less than 5 milliseconds of latency per request
- **SC-009**: Token refresh succeeds without requiring re-entry of credentials, completing in under 500 milliseconds
- **SC-010**: Automated test suite achieves at least 95% code coverage across all auth components

## Assumptions

- The platform scaffold (feature 013) is in place, including the FastAPI application factory, Pydantic Settings, async SQLAlchemy, Redis client wrapper, JWT middleware, and Kafka event infrastructure
- User profile and account management (name, avatar, preferences) is handled by a separate bounded context (Accounts) — the Auth context only manages credentials and sessions
- Password complexity rules (minimum length, character requirements) follow industry standard defaults: minimum 8 characters, at least one uppercase, one lowercase, one digit
- The 10 RBAC roles are predefined and not user-configurable in this feature. Custom role creation is a future enhancement
- RS256 key pair management (generation, rotation, distribution) is handled at the infrastructure level. The Auth context receives the public/private key pair via configuration
- Rate limiting at the network/infrastructure level (e.g., per-IP throttling) is separate from application-level account lockout. Both operate independently
- The QR code for TOTP enrollment is generated as an `otpauth://` URI that authenticator apps can scan. The system does not render the QR image itself — the frontend handles display
- Service account API keys use a prefix format (e.g., `msk_`) to allow identification of key type without database lookup
