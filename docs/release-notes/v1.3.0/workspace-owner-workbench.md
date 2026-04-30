# Workspace Owner Workbench

The workspace-owner workbench adds scoped pages for owners and admin equivalents for platform operators. The change is additive and does not break existing `/api/v1` contracts.

## Added

- Workspace pages for dashboard, members, settings, connectors, connector detail, quotas, tags, and visibility.
- Workspace summary, ownership-transfer, connector test-connectivity, IBOR diagnostic/sync/history, and 2PA challenge APIs.
- Foundational two-person approval primitive for reusable destructive-operation gates.
- Workspace audit events for member changes, ownership transfer, settings changes, and connector lifecycle changes.
- Dry-run connectivity methods for Slack, Telegram, email, and webhook connectors.

## Operator Notes

Ownership transfer emits initiated and committed audit events. Connector test-connectivity validates provider access without sending user-visible messages or creating delivery rows. IBOR connectors are administered from `/admin/settings?tab=ibor`.
