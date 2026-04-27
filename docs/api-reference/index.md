# API Reference

The API Reference is the developer entry point for Musematic's public and operator-facing interfaces. It combines the generated OpenAPI 3.1 snapshot, protocol notes for realtime channels, and integration notes for A2A and MCP surfaces.

Use these pages when building clients, validating automation, or debugging integration failures:

- [REST API](rest-api.md) embeds the generated OpenAPI snapshot and documents authentication, rate limits, and versioning.
- [Error Codes](error-codes.md) lists stable error identifiers and remediation steps for common client and operator failures.
- [WebSocket API](websocket-api.md) describes the `/ws` realtime gateway and subscription messages.
- [A2A API](a2a-api.md) and [MCP API](mcp-api.md) document integration surfaces that are present but still evolving.

The committed `openapi.json` file is regenerated from `apps/control-plane/src/platform/main.py` by `scripts/export-openapi.py`. CI fails if that snapshot drifts from the FastAPI app, which keeps this section aligned with FR-619.
