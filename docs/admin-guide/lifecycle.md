# Lifecycle

Lifecycle pages manage state transitions for users, workspaces, agents, model catalog entries, releases, and integrations.

## Common Admin Workflows

### Retire an Agent

Check active workflows, notify owners, set replacement guidance, and retire the revision. Keep the FQN history available for audit.

### Reactivate a User

Confirm the suspension reason is resolved, restore status, require password reset or MFA if needed, and watch for immediate failed login attempts.

### Deprecate a Model

Set deprecation metadata, update fallback chains, notify affected workspaces, and verify executions move to approved alternatives.

### Disable an Integration

Pause delivery, preserve retry state, and document remediation before deleting any configuration.
