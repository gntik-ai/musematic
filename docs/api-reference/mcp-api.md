# MCP API

The MCP integration documents how Musematic exposes tools and context to agents through the platform tool gateway. The migrated webhook verification material lives in the [Developer Guide MCP integration page](../developer-guide/mcp-integration.md).

## Contract Status

The API surface is partial in the current codebase. Treat this page as an integration note until the MCP router, tool registry, and runtime gateway are declared stable in a future release.

## Design Expectations

- Tool calls are authorized through the same policy and purpose checks used by workflow execution.
- Credentials are never embedded in tool descriptors; providers resolve secrets through the platform secret provider.
- Tool results include enough metadata for audit, replay, and error remediation.
- Webhook-style callbacks must use signature verification and replay protection.

Related requirements: FR-619 for API quality, FR-616 for reference freshness, and FR-618 for secure integration guidance.
