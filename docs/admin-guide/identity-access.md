# Identity and Access

Identity pages cover users, invitations, OAuth connections, MFA, sessions, and lifecycle actions. Admins can approve pending users, suspend accounts, reset MFA, revoke sessions, and unlock users after lockout.

## Common Admin Workflows

### Bulk-Suspend Users

Filter by workspace, status, or domain. Select the users, choose suspend, enter a reason, and confirm. The platform invalidates active sessions and emits account lifecycle events.

### Force MFA Enrollment

Open the user detail, require MFA on next login, and send the user the standard enrollment instructions. For high-risk accounts, revoke existing sessions after enabling the requirement.

### Revoke All Sessions

Use the session action from the user detail page. This is appropriate after credential exposure, role change, or device loss. The user must authenticate again before continuing.

### Approve Pending Signup

Review the pending approval queue, verify domain and workspace assignment, then approve or reject with a reason. The user remains unable to log in until approval is complete.

### Test OAuth Provider

From OAuth provider settings, use test connectivity before enabling a provider. Failed tests usually point to redirect URI, client secret, org allow-list, or network policy problems.
