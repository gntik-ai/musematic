# Feature Specification: Admin Settings Panel

**Feature Branch**: `027-admin-settings-panel`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Admin settings with tabs for users, signup policy, quotas, connectors, email, and security configuration."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — User Management (Priority: P1)

A platform administrator navigates to the admin settings page and selects the "Users" tab. They see a table listing all platform users with columns for name, email, account status (active, pending approval, suspended, blocked), role, last login, and creation date. The table supports searching by name or email, filtering by status, and sorting by any column. For users in "pending approval" status, the admin can approve or reject the account directly from the table. For active users, the admin can suspend or reactivate their account. Each action requires a confirmation dialog before execution. After an action is taken, the table updates to reflect the new status without a full page reload.

**Why this priority**: User management is the most critical administrative function. Without it, administrators cannot control who has access to the platform, approve new signups, or respond to security incidents by suspending compromised accounts.

**Independent Test**: Navigate to admin settings → Users tab. Verify the table loads with all users. Search for a user by email — verify the table filters. Click "Approve" on a pending user — verify the confirmation dialog appears, confirm it, verify the user's status changes to "active" in the table. Suspend an active user — verify status changes to "suspended." Attempt to access admin settings as a non-admin user — verify access denied.

**Acceptance Scenarios**:

1. **Given** an admin viewing the Users tab with 50 users, **When** they search for "john@example.com", **Then** the table filters to show only matching users
2. **Given** a user in "pending approval" status, **When** the admin clicks "Approve" and confirms, **Then** the user's status changes to "active" and the table row updates
3. **Given** a user in "pending approval" status, **When** the admin clicks "Reject" and confirms, **Then** the user's account is blocked and a notification email is sent
4. **Given** an active user, **When** the admin clicks "Suspend" and confirms, **Then** the user's status changes to "suspended" and their active sessions are invalidated
5. **Given** a suspended user, **When** the admin clicks "Reactivate", **Then** the user's status returns to "active"
6. **Given** a non-admin user, **When** they attempt to access the admin settings page, **Then** they are denied access and redirected to the home page

---

### User Story 2 — Signup and Authentication Policy (Priority: P1)

An administrator wants to control how new users join the platform and how existing users authenticate. In the "Signup" tab, they can choose the signup mode: open self-registration (anyone can sign up), invite-only (users must receive an invitation), or admin approval (users sign up but require admin approval before access). They can also toggle whether multi-factor authentication (MFA) is mandatory for all users or optional. When the signup mode or MFA policy changes, existing users are affected according to clear rules: changing to invite-only does not remove existing self-registered users, and enabling mandatory MFA triggers a prompt for users who have not yet enrolled on their next login.

**Why this priority**: Signup policy directly controls the security posture of the platform. Incorrect configuration could allow unauthorized access or lock out legitimate users. This must be immediately available alongside user management.

**Independent Test**: Navigate to Signup tab. Verify current signup mode is displayed. Change signup mode from "open" to "invite-only" — verify the change is saved and the UI reflects the new mode. Toggle MFA enforcement to "required" — verify the change is saved. Navigate away and return — verify the settings persist.

**Acceptance Scenarios**:

1. **Given** an admin on the Signup tab with current mode "open", **When** they select "invite-only" and save, **Then** the signup mode changes and new self-registrations are rejected
2. **Given** an admin on the Signup tab, **When** they enable "require MFA for all users" and save, **Then** users without MFA are prompted to enroll on their next login
3. **Given** the signup mode is "admin approval", **When** a new user signs up, **Then** their account status is "pending approval" and appears in the Users tab for admin review
4. **Given** any signup policy change, **When** the admin saves the change, **Then** a confirmation dialog summarizes the impact on existing users before applying

---

### User Story 3 — Workspace Quotas (Priority: P2)

An administrator wants to set resource limits for workspaces to prevent any single workspace from consuming disproportionate platform resources. In the "Quotas" tab, they can configure default limits that apply to all new workspaces, and optionally override limits for specific workspaces. Configurable quotas include: maximum number of registered agents, maximum concurrent executions, maximum number of sandboxes, monthly token budget (for model API calls), and storage quota (for artifacts and objects). Each limit has a numeric input with the current value displayed. When a workspace approaches a quota (80% usage), the workspace receives a warning notification.

**Why this priority**: Quotas protect the platform from resource exhaustion and enable fair multi-tenant usage. They are important but not as immediately critical as user access control (US1-US2).

**Independent Test**: Navigate to Quotas tab. Verify default quota values are displayed. Change the "max agents" default to 50 — verify the change saves. Select a specific workspace override — verify you can set a custom agent limit of 100 for that workspace. Navigate away and return — verify values persist.

**Acceptance Scenarios**:

1. **Given** an admin on the Quotas tab, **When** they view the default quotas, **Then** they see current limits for agents, executions, sandboxes, tokens, and storage with numeric inputs
2. **Given** the admin changes the default "max concurrent executions" to 20 and saves, **When** a new workspace is created, **Then** the new workspace inherits the 20-execution limit
3. **Given** the admin selects a workspace for override, **When** they set a custom storage quota of 50 GB and save, **Then** that workspace's limit changes to 50 GB while others retain the default
4. **Given** a workspace at 80% of its agent quota, **When** the threshold is crossed, **Then** the workspace receives a warning notification visible to workspace admins

---

### User Story 4 — Connector Configuration (Priority: P2)

An administrator wants to control which connector types (Slack, Telegram, Webhook, Email) are available across the platform. In the "Connectors" tab, they see each connector type listed with its name, description, and a toggle to enable or disable it globally. Disabling a connector type prevents any workspace from creating new instances of that type but does not affect existing instances (they continue to function but display a "type disabled" warning). The admin can also set global defaults for connector configuration, such as the maximum payload size and default retry settings.

**Why this priority**: Connector configuration is a governance concern — administrators need to control which external channels are available. However, individual connector instances are managed at the workspace level (feature 025), making this a secondary priority.

**Independent Test**: Navigate to Connectors tab. Verify all 4 connector types are listed with enabled toggles. Disable the "Email" connector type — verify the toggle reflects the change. Attempt to create an email connector instance in a workspace — verify creation is rejected. Re-enable "Email" — verify new instances can be created again.

**Acceptance Scenarios**:

1. **Given** an admin on the Connectors tab, **When** they view the list, **Then** they see all available connector types with name, description, and an enabled/disabled toggle
2. **Given** an enabled connector type, **When** the admin disables it, **Then** no new connector instances of that type can be created in any workspace
3. **Given** a disabled connector type with existing instances, **When** the admin disables it, **Then** existing instances continue functioning with a visible "type disabled" warning
4. **Given** a disabled connector type, **When** the admin re-enables it, **Then** new instances can be created and existing instances' warnings are removed
5. **Given** the admin changes global default settings (max payload size), **When** a new connector instance is created, **Then** it inherits the updated defaults

---

### User Story 5 — Email Delivery Configuration (Priority: P3)

An administrator wants to configure how the platform sends outbound notification emails (account verification, password reset, approval notifications, alerts). In the "Email" tab, they can enter SMTP server settings (host, port, username, password, encryption mode) or select a cloud email service (SES) with its credentials. A "Send Test Email" button allows the admin to verify the configuration by sending a test email to a specified address. The current delivery status (configured/not configured, last successful delivery timestamp) is displayed.

**Why this priority**: Email delivery is essential for account lifecycle (verification, password reset) but is a one-time configuration task. The platform can function with limited email capability (or a default local relay) while this is being set up.

**Independent Test**: Navigate to Email tab. Enter SMTP host/port/credentials. Click "Send Test Email" — verify a test email is received at the specified address. Save the configuration. Navigate away and return — verify the settings persist. Verify the credential values are masked (never shown as plaintext).

**Acceptance Scenarios**:

1. **Given** an admin on the Email tab, **When** they view the form, **Then** they see fields for SMTP or SES configuration with the current settings (credentials masked)
2. **Given** valid SMTP settings, **When** the admin clicks "Send Test Email" with a recipient address, **Then** a test email is sent and the admin sees a success or failure message within 10 seconds
3. **Given** an admin enters new SMTP credentials and saves, **When** they return to the tab later, **Then** the host and port are visible but the password field shows a masked placeholder
4. **Given** an admin switches from SMTP to SES, **When** they save the new configuration, **Then** the platform uses SES for subsequent email delivery

---

### User Story 6 — Security Settings (Priority: P3)

An administrator wants to configure platform-wide security policies. In the "Security" tab, they can set: password policy (minimum length, required character types, password expiry period), session duration (how long a user session remains valid before requiring re-authentication), and account lockout settings (maximum failed login attempts before lockout, lockout duration). Changes to security settings apply to new authentication events — existing active sessions are not immediately invalidated (they expire naturally based on their original duration).

**Why this priority**: Security settings are important but typically configured once during initial platform setup and rarely changed afterward. The platform ships with secure defaults from the authentication feature (feature 014), making this a lower-urgency configuration UI.

**Independent Test**: Navigate to Security tab. Change minimum password length from 12 to 16 — verify the change saves. Attempt a new user registration with a 14-character password — verify it is rejected. Change session duration to 1 hour — verify new logins expire after 1 hour. Change lockout attempts to 3 — verify a user is locked after 3 failed attempts.

**Acceptance Scenarios**:

1. **Given** an admin on the Security tab, **When** they view the form, **Then** they see current values for password policy, session duration, and lockout settings
2. **Given** the admin changes minimum password length to 16 and saves, **When** a user attempts to set a 14-character password, **Then** the password is rejected with an error message explaining the requirement
3. **Given** the admin changes session duration to 1 hour and saves, **When** a user logs in after the change, **Then** their session expires after 1 hour
4. **Given** the admin changes max failed attempts to 3 and saves, **When** a user fails login 3 times, **Then** their account is locked for the configured lockout duration
5. **Given** a security setting change, **When** the admin saves, **Then** existing active sessions are NOT invalidated — the change applies only to new authentication events

---

### Edge Cases

- What happens when the admin disables the only remaining signup mode? The system prevents disabling all modes — at least "invite-only" must remain enabled as a fallback, since the platform needs a mechanism for user onboarding.
- What happens when a quota is set below a workspace's current usage? The workspace is allowed to continue using existing resources but cannot create new ones until usage drops below the new limit. A warning is displayed to the workspace admin indicating they are over quota.
- What happens when the email delivery configuration is invalid but saved? The configuration is saved but marked as "unverified." The "Send Test Email" function shows an error. The system falls back to the previous working configuration (or default local relay) until the admin fixes it.
- What happens when the admin changes security settings while users are logged in? Existing sessions continue with their original settings. The new settings apply only to subsequent authentication events. A banner on the Security tab informs the admin of this behavior.
- What happens when two admins edit the same settings simultaneously? The last save wins. The form shows a "settings changed by another admin" warning if the underlying data changed since the form was loaded. The admin can reload to see the latest values before saving their own changes.
- What happens when the admin suspends themselves? The system prevents an admin from suspending their own account. The action button is disabled on the admin's own row with a tooltip explaining "You cannot suspend your own account."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a tabbed interface with six tabs: Users, Signup, Quotas, Connectors, Email, and Security
- **FR-002**: The system MUST restrict access to the admin settings page to users with the platform administrator role
- **FR-003**: The Users tab MUST display a searchable, sortable, filterable table of all platform users with columns for name, email, status, role, last login, and creation date
- **FR-004**: The Users tab MUST support inline actions: approve, reject, suspend, reactivate — each with a confirmation dialog
- **FR-005**: The Users tab actions MUST update the table row immediately after confirmation without requiring a full page reload
- **FR-006**: The system MUST prevent an admin from suspending their own account
- **FR-007**: The Signup tab MUST allow selection of signup mode: open self-registration, invite-only, or admin approval
- **FR-008**: The Signup tab MUST allow toggling MFA enforcement between optional and required for all users
- **FR-009**: The Signup tab MUST display a confirmation dialog summarizing the impact on existing users before applying policy changes
- **FR-010**: The Quotas tab MUST display configurable default limits for agents, concurrent executions, sandboxes, monthly tokens, and storage
- **FR-011**: The Quotas tab MUST support per-workspace quota overrides
- **FR-012**: The Connectors tab MUST display all connector types with a global enable/disable toggle per type
- **FR-013**: Disabling a connector type MUST prevent new instance creation while allowing existing instances to continue operating
- **FR-014**: The Email tab MUST support SMTP and SES configuration with appropriate fields for each mode
- **FR-015**: The Email tab MUST provide a "Send Test Email" function that verifies the configuration by delivering a test message
- **FR-016**: The Email tab MUST mask credential values in the form (never display plaintext passwords or secret keys)
- **FR-017**: The Security tab MUST allow configuration of password policy (minimum length, character requirements, expiry), session duration, and account lockout (max attempts, lockout duration)
- **FR-018**: Security setting changes MUST apply only to new authentication events — existing sessions are not retroactively invalidated
- **FR-019**: All settings forms MUST validate input before submission and display clear error messages for invalid values
- **FR-020**: All settings changes MUST persist across page navigations and browser refreshes
- **FR-021**: The system MUST display a stale-data warning if another admin modifies settings while the form is open
- **FR-022**: The system MUST be fully keyboard navigable and compatible with screen readers
- **FR-023**: The system MUST render correctly in both light and dark color modes
- **FR-024**: The system MUST be responsive across desktop (1024px+) and mobile (320px+) screen widths

### Key Entities

- **PlatformSettings**: Top-level container for all admin-configurable settings. Contains signup policy, MFA enforcement, default quotas, security policy, and email delivery configuration.
- **SignupPolicy**: Signup mode (open, invite-only, admin-approval) and MFA enforcement flag (optional or required). Changes have documented impact on existing users.
- **DefaultQuotas**: Default resource limits applied to new workspaces — max agents, max concurrent executions, max sandboxes, monthly token budget, storage quota (in GB).
- **WorkspaceQuotaOverride**: Per-workspace override of one or more default quota values. Null fields inherit the default.
- **ConnectorTypeConfig**: Global configuration for a connector type — enabled/disabled flag and default settings (max payload size, default retry count).
- **EmailDeliveryConfig**: Email service configuration — mode (SMTP or SES), SMTP fields (host, port, username, encrypted password reference, encryption mode), SES fields (region, access key reference, secret key reference), verification status, last successful delivery timestamp.
- **SecurityPolicy**: Password requirements (minimum length, required character types, expiry days), session duration (in minutes), and lockout settings (max failed attempts, lockout duration in minutes).
- **UserAdminView**: Read-only projection of a user for the admin table — ID, name, email, account status, role, last login timestamp, creation timestamp, available actions based on current status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The admin settings page loads with the default tab visible within 2 seconds of navigation
- **SC-002**: Tab switching displays the new tab's content within 500 milliseconds
- **SC-003**: User table searches filter results within 300 milliseconds of typing
- **SC-004**: User management actions (approve, suspend, reactivate) complete and update the table within 2 seconds of confirmation
- **SC-005**: Settings changes (signup, quotas, connectors, email, security) save and confirm within 3 seconds of form submission
- **SC-006**: The "Send Test Email" function returns a success or failure result within 10 seconds
- **SC-007**: All forms prevent submission of invalid data — 100% of invalid inputs produce a clear error message before submission
- **SC-008**: The admin settings panel renders correctly on screen widths from 320px to 2560px without horizontal scrolling
- **SC-009**: All interactive elements are reachable via keyboard navigation with visible focus indicators
- **SC-010**: Dark mode and light mode both pass visual contrast requirements (WCAG AA)
- **SC-011**: Test coverage of the admin settings panel feature is at least 95%

## Assumptions

- The user is authenticated and has the platform administrator role. Non-admin access is denied at the page level (route guard), not per-tab.
- The backend API endpoints for user management (feature 016 — accounts BC), authentication policy (feature 014 — auth BC), workspace quotas (feature 018 — workspaces BC), connector types (feature 025 — connectors BC), email delivery configuration, and security settings are available or will be created as part of BFF endpoints.
- The DataTable shared component (feature 015 scaffold) supports server-side search, filtering, sorting, and pagination. Column definitions are passed as props.
- The existing sidebar navigation (feature 015 scaffold) includes an "Admin" or "Settings" link visible only to platform administrator roles via RBAC-filtered sidebar items.
- Credential masking for the Email tab follows the same vault reference pattern as connector credentials (feature 025) — the backend stores encrypted references, the frontend displays masked placeholders, and actual values are never sent in GET responses.
- Default quota values and security policy defaults are established during initial platform setup. The admin settings panel displays and modifies existing values — it does not set initial values from scratch.
- The stale-data detection for concurrent editing uses a version number or `updated_at` timestamp returned by the backend. The frontend compares its loaded version against the server's current version before saving.
- Quota warning notifications (80% threshold) are handled by the backend — the admin settings panel only configures the limits, not the notification mechanism.
