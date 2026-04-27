# Workspaces

Workspaces owns collaboration boundaries: workspace records, membership, roles, goals, visibility grants, and settings.

Primary entities include workspaces, members, goals, visibility grants, and workspace settings. The REST surface is rooted at `/api/v1/workspaces`. Events are emitted on `workspaces.events` and feed realtime clients and analytics.

The workspace goal ID provides GID correlation across conversations, executions, traces, logs, cost, and audit.
