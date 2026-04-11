# Feature Specification: Accounts Bounded Context — User Registration, Lifecycle, and Invitations

**Feature Branch**: `016-accounts-bounded-context`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement user registration, lifecycle management (pending_verification → pending_approval → active → suspended → blocked → archived), invitations, email verification, and admin approval workflows."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Self-Registration and Email Verification (Priority: P1)

A new user visits the platform and creates an account by providing their email, display name, and password. The system creates the account in a "pending verification" status and sends a verification email containing a time-limited verification link. The user clicks the link to verify their email address. If the platform's signup mode is "open", the account transitions directly to "active". If the signup mode is "admin_approval", the account transitions to "pending approval" and awaits administrator action. The user is notified of their account's current status at each stage.

**Why this priority**: User registration is the entry point to the platform. Without it, no users can be created except through admin actions. This is the foundational flow for all other account operations.

**Independent Test**: Submit a registration request with valid email, display name, and password. Verify the account is created in "pending_verification" status. Simulate clicking the verification link. Verify the account transitions to "active" (in open mode) or "pending_approval" (in admin_approval mode). Attempt to register with an already-used email. Verify duplicate registration is rejected.

**Acceptance Scenarios**:

1. **Given** a platform configured for open signup, **When** a new user submits registration with a valid email, display name, and password, **Then** an account is created in "pending_verification" status and a verification email is dispatched
2. **Given** a user with a pending verification account, **When** they submit the verification token from their email within the validity period, **Then** the account transitions to "active" and the user can log in
3. **Given** a platform configured for admin_approval signup mode, **When** a user completes email verification, **Then** the account transitions to "pending_approval" (not "active") and the user is informed that admin approval is required
4. **Given** a verification token that has expired, **When** the user submits it, **Then** the system rejects it with an appropriate message and offers to resend the verification email
5. **Given** an existing active account with a specific email, **When** a new user attempts to register with the same email, **Then** the registration is rejected without revealing whether the email is already registered (to prevent user enumeration)

---

### User Story 2 — Admin Approval Workflow (Priority: P1)

When the platform is configured with the "admin_approval" signup mode, newly verified accounts require explicit approval from a workspace admin or superadmin before becoming active. Administrators can view a list of pending approval requests, approve or reject them with an optional reason, and be notified when new requests arrive. Approved users are activated and receive a welcome notification. Rejected users are notified with the rejection reason and their account is archived.

**Why this priority**: The approval workflow gates access to the platform. In enterprise environments, this is a compliance requirement — uncontrolled account creation is unacceptable. This must ship alongside registration to provide a complete onboarding flow.

**Independent Test**: Configure the platform for admin_approval mode. Register and verify a new user. Log in as an admin. Verify the pending approval appears in the admin approval queue. Approve the user. Verify the account becomes active. Register and verify another user. Reject them with a reason. Verify the account is archived and the user is notified of the rejection reason.

**Acceptance Scenarios**:

1. **Given** a user with "pending_approval" status, **When** an admin views the approval queue, **Then** the user appears in the list with their email, display name, registration date, and verification date
2. **Given** a pending approval request, **When** an admin approves it, **Then** the account transitions to "active", a default workspace is created for the user, and a welcome notification is dispatched
3. **Given** a pending approval request, **When** an admin rejects it with a reason, **Then** the account transitions to "archived", the user is notified of the rejection reason, and the rejection is recorded in the audit log
4. **Given** multiple pending approvals, **When** an admin views the queue, **Then** requests are sorted by registration date (oldest first) and include total count

---

### User Story 3 — Invitation-Based Registration (Priority: P2)

An administrator or workspace owner invites a new user to join the platform by providing their email address and assigning initial roles. The system generates a time-limited invitation link and sends it to the invitee. The invitee clicks the link, completes their profile (display name, password), and their account is created as "active" immediately — bypassing both email verification and admin approval since the invitation itself serves as pre-authorization. Unused invitations expire after a configurable period and can be revoked by the inviter.

**Why this priority**: Invitations are a critical onboarding path in enterprise environments but the platform can function with self-registration alone. This is an enhancement to the core registration flow.

**Independent Test**: As an admin, create an invitation for a new email address with specific roles. Verify the invitation is created and an email is dispatched. Open the invitation link. Complete the registration form. Verify the account is created with "active" status and the assigned roles. Attempt to use the same invitation link again. Verify it is rejected as already consumed.

**Acceptance Scenarios**:

1. **Given** an admin or workspace owner, **When** they create an invitation with an email and role assignments, **Then** an invitation record is created, a unique time-limited link is generated, and an email is dispatched to the invitee
2. **Given** a valid invitation link, **When** the invitee clicks it and completes their profile, **Then** an account is created with "active" status, the pre-assigned roles are applied, and the invitation is marked as consumed
3. **Given** an invitation that has already been consumed, **When** someone attempts to use the link again, **Then** the system rejects it with a message that the invitation has already been used
4. **Given** an invitation that has expired, **When** the invitee attempts to use it, **Then** the system rejects it with an appropriate message
5. **Given** a pending invitation, **When** the inviter revokes it, **Then** the invitation is invalidated and can no longer be used

---

### User Story 4 — Admin Account Lifecycle Management (Priority: P1)

Administrators need to manage user accounts throughout their lifecycle. This includes suspending a user (temporarily disabling their access), reactivating a suspended user, blocking a user (permanently disabling access pending investigation), archiving a user (soft-deleting their account), resetting a user's MFA enrollment, resetting a user's password (triggering a forced password change on next login), and unlocking a locked-out account. Every lifecycle action is recorded in the audit log and triggers an appropriate event for downstream systems.

**Why this priority**: Account lifecycle management is an operational necessity that must exist from day one. Support teams need the ability to intervene in user accounts for security incidents, compliance, and support requests.

**Independent Test**: Create an active user. Suspend them. Verify they cannot log in. Reactivate them. Verify they can log in again. Block the user. Verify they cannot log in and cannot be reactivated without explicit unblock. Archive the user. Verify their data is soft-deleted. Reset a user's MFA. Verify their MFA enrollment is cleared.

**Acceptance Scenarios**:

1. **Given** an active user, **When** an admin suspends them with a reason, **Then** the user's status changes to "suspended", their active sessions are invalidated, and a lifecycle event is emitted
2. **Given** a suspended user, **When** an admin reactivates them, **Then** the user's status changes to "active" and they can log in again
3. **Given** an active user, **When** an admin blocks them with a reason, **Then** the user's status changes to "blocked", their sessions are invalidated, and the block reason is recorded
4. **Given** a blocked user, **When** an admin unblocks them, **Then** the user's status changes to "active"
5. **Given** any non-archived user, **When** an admin archives them, **Then** the user's status changes to "archived", their data is soft-deleted, all sessions are invalidated, and the account is no longer discoverable in user lists
6. **Given** a user with MFA enrolled, **When** an admin resets their MFA, **Then** the user's MFA enrollment is cleared and they must re-enroll on next login if MFA is required
7. **Given** a user, **When** an admin triggers a password reset, **Then** a password reset is initiated (either via reset link or forced change on next login) and the user is notified
8. **Given** a locked-out user (from failed login attempts), **When** an admin unlocks them, **Then** the lockout counter is cleared and the user can attempt login immediately

---

### User Story 5 — Default Workspace Provisioning on Activation (Priority: P2)

When a user account transitions to "active" status (whether through self-registration, admin approval, or invitation), the system automatically creates a default personal workspace for the user. The user is assigned the "workspace_admin" role within this workspace. This ensures every active user has at least one workspace to operate in. The workspace creation is communicated to the workspace bounded context via an event, not through direct database access.

**Why this priority**: Workspace provisioning is essential for usability but depends on the workspace bounded context being available. The accounts context emits the activation event; workspace creation can be handled asynchronously. The platform functions (for admin tasks at least) even if workspace provisioning is deferred.

**Independent Test**: Activate a new user account. Verify an event is emitted requesting default workspace creation. Verify the event contains the user's ID, email, and display name. Verify the workspace bounded context (or a mock listener) receives the event and creates a workspace.

**Acceptance Scenarios**:

1. **Given** a user account transitioning to "active", **When** the activation is processed, **Then** a workspace provisioning event is emitted with the user's ID, email, and display name
2. **Given** an invitation with pre-assigned workspace membership, **When** the invited user's account is activated, **Then** the user is added to the specified workspace(s) instead of creating a new default workspace
3. **Given** a user being reactivated from "suspended" status, **When** reactivation is processed, **Then** no new workspace is created (their existing workspaces remain intact)

---

### Edge Cases

- What happens when a user attempts to register with the "invite_only" signup mode and no invitation? The registration endpoint returns an error indicating that self-registration is not available and an invitation is required.
- What happens when an admin tries to approve an already-active user? The action is rejected with a message that the user is already active. No status change occurs.
- What happens when a user requests email re-verification while already verified? The system ignores the request and informs the user that their email is already verified.
- What happens when the email dispatch service is unavailable? The registration succeeds (account is created in pending_verification), but the verification email is queued for retry. The user can request a resend later.
- What happens when an invitation is created for an email that already has an active account? The invitation is rejected with a message that the email is already registered.
- What happens when multiple admins attempt to approve/reject the same user simultaneously? The first action succeeds; the second receives a conflict error indicating the request has already been processed.
- What happens when an archived user's email is used for a new registration? The system treats it as a new registration — the archived account remains as a historical record with a different internal identifier linkage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support three configurable signup modes: "open" (self-registration allowed, no approval needed), "invite_only" (registration only via invitation links), and "admin_approval" (self-registration allowed but admin approval required)
- **FR-002**: System MUST create user accounts in "pending_verification" status upon self-registration and dispatch a verification email with a time-limited token (default: 24 hours)
- **FR-003**: System MUST transition accounts from "pending_verification" to "active" (open mode) or "pending_approval" (admin_approval mode) upon successful email verification
- **FR-004**: System MUST support email verification token resend with rate limiting (maximum 3 resends per hour)
- **FR-005**: System MUST provide an admin approval queue showing pending accounts with registration metadata, sortable by date
- **FR-006**: System MUST allow admins to approve (transition to "active") or reject (transition to "archived") pending approval requests, with optional reason text
- **FR-007**: System MUST support invitation creation by admins and workspace owners, including email, optional message, pre-assigned roles, and optional workspace membership
- **FR-008**: System MUST generate unique, time-limited invitation tokens (default: 7 days) that can be revoked by the creator
- **FR-009**: Invitation-based registration MUST bypass email verification and admin approval, creating accounts directly in "active" status
- **FR-010**: System MUST enforce the full account lifecycle state machine: pending_verification → pending_approval → active ↔ suspended → blocked → archived (with valid transitions only)
- **FR-011**: System MUST support admin lifecycle actions: suspend, reactivate, block, unblock, archive, reset MFA, reset password, and unlock (clear lockout)
- **FR-012**: All lifecycle transitions MUST invalidate active user sessions when the target status prevents login (suspended, blocked, archived)
- **FR-013**: System MUST emit events for all lifecycle transitions, registration completions, email verifications, invitation acceptances, and admin actions
- **FR-014**: System MUST prevent user enumeration — registration and verification responses must not reveal whether a specific email is already registered
- **FR-015**: System MUST emit a workspace provisioning event when a user account transitions to "active" for the first time
- **FR-016**: System MUST record all admin actions (approvals, rejections, suspensions, etc.) with the acting admin's identity, timestamp, reason, and target user for audit purposes
- **FR-017**: System MUST validate registration data: email format, password strength (minimum 12 characters, at least one uppercase, one lowercase, one digit, one special character), display name length (2–100 characters)

### Key Entities

- **User**: Represents a registered user account. Key attributes: unique identifier, email (unique), display name, status (lifecycle state), signup source (self-registration or invitation), creation timestamp, verification timestamp, activation timestamp.
- **UserStatus**: Enumeration of lifecycle states: pending_verification, pending_approval, active, suspended, blocked, archived. Defines valid transitions between states.
- **EmailVerification**: A time-limited token linked to a user account for verifying email ownership. Key attributes: token (unique), user reference, expiration timestamp, consumed flag.
- **Invitation**: A pre-authorization for a new user to join the platform. Key attributes: unique token, inviter reference, invitee email, pre-assigned roles, optional workspace memberships, expiration timestamp, status (pending, consumed, expired, revoked).
- **ApprovalRequest**: An admin review record for accounts in "pending_approval" status. Key attributes: user reference, request timestamp, reviewer reference (admin who acted), decision (approved/rejected), decision timestamp, reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users complete self-registration (submit form to receiving verification email) within 10 seconds of form submission
- **SC-002**: Email verification link click transitions the account status within 2 seconds
- **SC-003**: Admin approval or rejection of a pending account completes within 2 seconds
- **SC-004**: Invitation-based registration (link click to active account) completes within 15 seconds including profile completion
- **SC-005**: All lifecycle transitions emit events that downstream consumers receive within 5 seconds
- **SC-006**: Account status changes are reflected in login behavior immediately — a suspended or blocked user's next authentication attempt is rejected
- **SC-007**: The system prevents 100% of user enumeration attempts through registration and verification endpoints
- **SC-008**: Admin actions are recorded with complete audit metadata (actor, target, action, reason, timestamp) for 100% of operations
- **SC-009**: Invitation tokens cannot be reused after consumption or expiration — 0% acceptance rate for invalid tokens
- **SC-010**: Account lifecycle state machine enforces only valid transitions — 0% of invalid state transitions succeed

## Assumptions

- The auth bounded context (feature 014) is available and provides password hashing (Argon2id), JWT issuance, session management (Redis), MFA enrollment, lockout management, and RBAC checks. The accounts context delegates authentication to auth — it does not implement password hashing or JWT directly.
- Email dispatch is handled by the notifications bounded context. The accounts context emits events or calls an internal notification service interface to request email sending — it does not send emails directly.
- The workspace bounded context listens for the user activation event and handles default workspace creation. The accounts context emits the event only — cross-boundary database access is prohibited.
- Password strength validation rules follow NIST SP 800-63B guidelines (minimum 12 characters with complexity requirements). These rules are consistent with the auth context's password policy.
- The signup mode ("open", "invite_only", "admin_approval") is a platform-level configuration setting, not per-workspace. Changing the signup mode affects all future registrations but does not retroactively change existing accounts.
- "Archived" is a soft-delete — user data is retained for audit and compliance purposes but the account is functionally removed from all user-facing lists and cannot be re-activated. A new registration with the same email is treated as a new account.
- The MFA reset and password reset admin actions invoke the auth context's corresponding service interfaces — the accounts context orchestrates the lifecycle but delegates the actual credential operations to auth.
