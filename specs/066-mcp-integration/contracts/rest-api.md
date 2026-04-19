# REST API Contracts: MCP Integration

**Feature**: 066-mcp-integration | **Date**: 2026-04-19  
**Spec**: [spec.md](../spec.md)

---

## Base URL

All operator-management endpoints: `/api/v1/mcp`  
Inbound MCP protocol endpoints: `/api/v1/mcp/protocol`

---

## Operator Management API (9 endpoints)

### POST `/api/v1/mcp/servers`

Register an external MCP server. Operator-only.

**Request body**:
```json
{
  "display_name": "Vendor Code Search",
  "endpoint_url": "https://mcp.vendor.example/api",
  "auth_config": {
    "type": "api_key",
    "credential_ref": "connector_credential_id"
  },
  "catalog_ttl_seconds": 3600
}
```

**Responses**:
- `201 Created` — `MCPServerResponse` with `server_id`, `status: "active"`, `created_at`
- `400 Bad Request` — `code: https_required` if endpoint URL is not HTTPS (FR-017)
- `400 Bad Request` — `code: endpoint_already_registered` if URL already registered in workspace (FR-024)
- `403 Forbidden` — principal is not an operator

---

### GET `/api/v1/mcp/servers`

List all registered external MCP servers for the workspace.

**Query params**: `status` (filter: active/suspended/deregistered), `page`, `page_size`

**Response** `200 OK`:
```json
{
  "items": [
    {
      "server_id": "uuid",
      "display_name": "...",
      "endpoint_url": "https://...",
      "status": "active",
      "last_catalog_fetched_at": "2026-04-19T10:00:00Z",
      "tool_count": 12,
      "health": { "status": "healthy", "last_success_at": "...", "error_count_5m": 0 }
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

---

### GET `/api/v1/mcp/servers/{server_id}`

Get server details including current health status and catalog metadata.

**Response** `200 OK`:
```json
{
  "server_id": "uuid",
  "display_name": "...",
  "endpoint_url": "https://...",
  "status": "active",
  "catalog_ttl_seconds": 3600,
  "last_catalog_fetched_at": "...",
  "catalog_version_snapshot": "2024-11-05",
  "catalog_is_stale": false,
  "health": {
    "status": "healthy",
    "last_success_at": "...",
    "error_count_5m": 0,
    "last_error_at": null
  },
  "created_at": "...",
  "created_by": "uuid"
}
```

- `404 Not Found` — server not found in workspace

---

### PATCH `/api/v1/mcp/servers/{server_id}`

Update server record — suspend, reactivate, or change display name / TTL. Operator-only.

**Request body** (all optional):
```json
{
  "display_name": "New Name",
  "status": "suspended",
  "catalog_ttl_seconds": 1800
}
```

**Response** `200 OK` — updated `MCPServerResponse`

- `400 Bad Request` — `code: deregistered_servers_immutable` if server is deregistered

---

### DELETE `/api/v1/mcp/servers/{server_id}`

Deregister an external MCP server. Sets status to `deregistered`; does not delete the record. Operator-only.

**Response** `200 OK` — `{ "server_id": "...", "status": "deregistered" }`

---

### GET `/api/v1/mcp/servers/{server_id}/catalog`

View the cached tool catalog for a registered server.

**Response** `200 OK`:
```json
{
  "server_id": "uuid",
  "fetched_at": "...",
  "version_snapshot": "...",
  "is_stale": false,
  "tool_count": 12,
  "tools": [
    { "name": "search_code", "description": "...", "input_schema": {...} }
  ]
}
```

---

### POST `/api/v1/mcp/servers/{server_id}/refresh`

Force an immediate catalog refresh. Operator-only.

**Response** `202 Accepted` — `{ "server_id": "...", "refresh_scheduled": true }`

---

### GET `/api/v1/mcp/exposed-tools`

List all platform tools with their MCP-exposure status.

**Query params**: `is_exposed` (filter: true/false), `page`, `page_size`

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "uuid",
      "tool_fqn": "platform:document_search",
      "mcp_tool_name": "document_search",
      "mcp_description": "...",
      "is_exposed": true,
      "updated_at": "..."
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20
}
```

---

### PUT `/api/v1/mcp/exposed-tools/{tool_fqn}`

Create or update an MCP-exposed tool definition. Setting `is_exposed: false` disables discovery within 60 seconds (SC-013). Operator-only.

**Request body**:
```json
{
  "mcp_tool_name": "document_search",
  "mcp_description": "Search documents in the workspace",
  "mcp_input_schema": {
    "type": "object",
    "properties": { "query": { "type": "string" } },
    "required": ["query"]
  },
  "is_exposed": true
}
```

**Response** `200 OK` or `201 Created` — `MCPExposedToolResponse`

---

## Inbound MCP Protocol Endpoints (3 endpoints)

These endpoints implement the MCP server-side protocol. All require `Authorization` header.

### POST `/api/v1/mcp/protocol/initialize`

MCP initialization handshake. Validates protocol version; returns server capabilities.

**Request body**:
```json
{
  "protocolVersion": "2024-11-05",
  "capabilities": { "tools": {} },
  "clientInfo": { "name": "...", "version": "..." }
}
```

**Response** `200 OK`:
```json
{
  "protocolVersion": "2024-11-05",
  "capabilities": { "tools": { "listChanged": true } },
  "serverInfo": { "name": "musematic-platform", "version": "1.0" }
}
```

- `400 Bad Request` — `code: protocol_version_unsupported`, `supported: ["2024-11-05"]`
- `401 Unauthorized` — missing or invalid `Authorization` header

---

### POST `/api/v1/mcp/protocol/tools/list`

Discover MCP-exposed platform tools for the authenticated principal.

**Request body**: `{}` (no parameters required by MCP spec)

**Response** `200 OK`:
```json
{
  "tools": [
    {
      "name": "document_search",
      "description": "Search documents in the workspace",
      "inputSchema": {
        "type": "object",
        "properties": { "query": { "type": "string" } },
        "required": ["query"]
      }
    }
  ]
}
```

- Only tools with `is_exposed: true` appear (FR-009, SC-008)
- `401 Unauthorized` — unauthenticated request

---

### POST `/api/v1/mcp/protocol/tools/call`

Invoke a platform tool via MCP. Every call passes through `ToolGatewayService` (FR-011).

**Request body**:
```json
{
  "name": "document_search",
  "arguments": { "query": "AI research papers" }
}
```

**Response** `200 OK` (MCP canonical format):
```json
{
  "content": [
    { "type": "text", "text": "Found 12 matching documents…" }
  ],
  "isError": false
}
```

**Error response** (MCP error format):
```json
{
  "code": -32603,
  "message": "Tool invocation denied",
  "data": { "code": "authorization_error", "block_reason": "permission_denied" }
}
```

Error codes used:
- `tool_not_found` — tool name not in exposed subset (SC-008)
- `authentication_error` — unauthenticated (401)
- `authorization_error` — gateway denial (403)
- `payload_too_large` — result exceeds `MCP_MAX_PAYLOAD_BYTES`
- `internal_error` — tool execution failure (internal trace NOT disclosed, FR-014)

---

## Internal Service Interface

### `MCPToolRegistry.resolve_agent_catalog(agent_id, workspace_id, session) → list[MCPToolBinding]`

Called by the execution engine at agent-execution start (FR-003).

Returns the resolved set of MCP tool bindings for the agent, with namespaced identifiers (`mcp:{server_id}:{tool_name}`). Skips suspended/deregistered servers (FR-026). Uses Redis cache → DB cache → live fetch hierarchy (D-008).

**Raises**: `MCPServerUnavailableError` (transient, non-fatal — server is skipped with warning)

---

### `MCPToolRegistry.invoke_tool(tool_fqn, arguments, *, agent_id, agent_fqn, declared_purpose, execution_id, workspace_id, session) → MCPToolResult`

Called by the execution engine when the agent invokes an `mcp:` prefixed tool. Does NOT call `ToolGatewayService` itself — the caller (ToolGatewayService) is already wrapping this call. This method performs the outbound network request to the external MCP server and returns the raw result for sanitization.

**Raises**: `MCPToolError(classification="transient"|"permanent")` (FR-013)

---

### `MCPService.get_server_health(server_id, workspace_id) → MCPServerHealthStatus`

Called by the operator-monitoring surface. Returns health aggregate from Redis with DB fallback (D-012 / FR-022).
