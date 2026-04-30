# Tenancy and Workspaces

Tenancy pages manage workspace boundaries, membership, quotas, goals, and visibility. Workspace state controls who can collaborate and which agents can be discovered or invoked.

## Common Admin Workflows

### Create a Workspace

Create the workspace with an owner, default quota, and initial visibility policy. Confirm the owner receives the correct role before inviting members.

### Transfer Ownership

Add the new owner first, verify access, then transfer ownership. Keep an audit reason because ownership changes affect policy, cost, and lifecycle responsibility.

### Adjust Workspace Quotas

Review current usage, forecast, and budget alerts. Apply the quota change with a time-bound reason, then watch cost governance alerts for the next billing period.

### Restore an Archived Workspace

Confirm the archive reason, dependency state, and owner. Restore only after verifying data retention and policy requirements.

### Review Visibility Grants

Search by agent FQN pattern and workspace. Remove overly broad grants and prefer explicit grants for regulated agents.

## Workspace Owner Surfaces

Workspace owners use `/workspaces/{id}` and its child pages for workspace-scoped operations: dashboard review, member management, settings, connector setup, quotas, tags, and visibility. Platform admins use `/admin/settings?tab=workspaces` for a global workspace index and `/admin/settings?tab=ibor` for identity-broker connectors.

Rule 47 scope distinction applies: workspace-owner actions can change only the selected workspace, while platform-admin actions can inspect or configure global identity and admin equivalents. Ownership transfer remains server-side 2PA-gated even when initiated from the workspace-owner UI.
