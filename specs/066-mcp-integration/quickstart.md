# Quickstart & Test Scenarios: MCP Integration

**Feature**: 066-mcp-integration | **Date**: 2026-04-19  
**Spec**: [spec.md](spec.md)

---

## S1 — External MCP server registration succeeds for operator

Setup: Platform operator with workspace.  
Expected:
- `POST /api/v1/mcp/servers` returns `201 Created` with `server_id` and `status: "active"`
- `MCPServerRegistration` record created in DB with `status=active`
- `mcp.server.registered` Kafka event emitted

## S2 — Duplicate registration rejected

Setup: An MCP server URL already registered in the workspace.  
Expected:
- Second `POST /api/v1/mcp/servers` with same URL returns `400` with `code: endpoint_already_registered`
- No duplicate record created (FR-024)

## S3 — Non-HTTPS endpoint registration rejected

Setup: Operator submits `http://` endpoint URL.  
Expected:
- `POST /api/v1/mcp/servers` returns `400` with `code: https_required`
- No record created (FR-017)

## S4 — Agent execution discovers external MCP tools

Setup: Active external MCP server registered. Agent has the server's UUID in `mcp_servers`. Fresh catalog needed.  
Expected:
- Execution engine calls `MCPToolRegistry.resolve_agent_catalog(agent_id, workspace_id, …)`
- Platform connects to external server, performs MCP initialize handshake, calls `tools/list`
- Returned tools added to agent's available toolset with namespaced identifiers `mcp:{server_id}:{tool_name}`
- `mcp.catalog.refreshed` Kafka event emitted
- Redis key `cache:mcp_catalog:{server_id}` set with TTL

## S5 — Catalog served from cache on second execution

Setup: Same server with warm Redis cache (within TTL).  
Expected:
- Second `MCPToolRegistry.resolve_agent_catalog` call returns cached tools
- No outbound HTTP request to external server
- Cache hit rate ≥ 90% under repeated calls within TTL (SC-007)

## S6 — MCP tool invocation passes through tool gateway before network call

Setup: Agent with access to external MCP tool. Policy check passes.  
Expected:
- `ToolGatewayService.validate_tool_invocation` called with `tool_fqn="mcp:{server_id}:{tool_name}"`
- Gateway returns `GateResult(allowed=True)` before any network request to external server
- `mcp.tool.invoked` Kafka event emitted with `outcome=allowed`
- `MCPInvocationAuditRecord` written (FR-007)

## S7 — MCP tool invocation denied by tool gateway

Setup: Agent whose policy denies the specific MCP server (e.g., deny-all outbound).  
Expected:
- `ToolGatewayService.validate_tool_invocation` returns `GateResult(allowed=False, block_reason="permission_denied")`
- No outbound HTTP request made (FR-004 / SC-001)
- `PolicyBlockedActionRecord` written
- `mcp.tool.denied` Kafka event emitted
- Agent receives tool-failure result with gateway-denial classification

## S8 — MCP tool invocation denied — budget exceeded

Setup: Agent with exhausted budget invokes an external MCP tool.  
Expected:
- Gateway returns budget-exceeded denial before any network request (FR-006)
- No call to external MCP server
- Audit record captures `outcome=denied`, `block_reason=budget_exceeded`

## S9 — MCP tool result passes through output sanitization

Setup: External MCP server returns a result containing a synthetic bearer token.  
Expected:
- `OutputSanitizer.sanitize` applied to MCP tool result before delivering to agent
- Token replaced with `[REDACTED:bearer_token]`
- `redaction_count > 0` in `SanitizationResult` (FR-005 / SC-003)

## S10 — Native tool invocations unaffected by MCP gateway changes (no regression)

Setup: Run all existing native-tool integration tests.  
Expected:
- 100% pass — gateway modification is additive (`mcp:` prefix branch only)
- Decision outputs for non-`mcp:` tool_fqns are byte-identical to pre-MCP behavior (FR-023 / SC-005)

## S11 — Tool name collision across two MCP servers impossible

Setup: Two registered MCP servers, each exposing a tool named `search`.  
Expected:
- Agent toolset contains `mcp:{server_a_id}:search` and `mcp:{server_b_id}:search`
- Both tools identifiable and invocable without ambiguity (FR-008 / SC-006)

## S12 — Suspended server excluded from discovery

Setup: Agent config references a suspended MCP server and an active one.  
Expected:
- Discovery skips suspended server with a warning log
- Agent toolset contains only tools from the active server
- No error cascades to execution; execution proceeds (FR-026 / edge case)

## S13 — Inbound MCP client performs tool discovery

Setup: Set two platform tools as `is_exposed=true`. External MCP client authenticates.  
Expected:
- `POST /api/v1/mcp/protocol/initialize` returns `200` with `protocolVersion: "2024-11-05"`
- `POST /api/v1/mcp/protocol/tools/list` returns exactly the 2 exposed tools with MCP-compliant schemas
- Non-exposed tools not present in response (FR-009 / SC-008)

## S14 — Inbound MCP tool invocation passes through tool gateway

Setup: Authenticated external MCP client invokes an exposed platform tool.  
Expected:
- `POST /api/v1/mcp/protocol/tools/call` triggers `ToolGatewayService.validate_tool_invocation` before tool code executes
- On allow: tool executes, result sanitized, returned in MCP canonical format
- `MCPInvocationAuditRecord` written with `direction=inbound` (FR-011 / SC-002)

## S15 — Inbound MCP invocation denied — unauthenticated

Setup: No `Authorization` header on `tools/call` request.  
Expected:
- `401 Unauthorized` with MCP error body
- No tool code executes, no internal tool names disclosed (FR-014)
- Auth failure audit record written

## S16 — Inbound MCP invocation denied — tool not in exposed subset

Setup: External MCP client attempts to call a tool not marked `is_exposed=true`.  
Expected:
- `tools/call` returns MCP error with `code: tool_not_found`
- No metadata about the tool's internal existence disclosed (SC-008)
- Denial audit record written

## S17 — Operator toggles tool exposure — takes effect within 60 seconds

Setup: Platform tool with `is_exposed=true`. Operator sets `is_exposed=false`.  
Expected:
- `PUT /api/v1/mcp/exposed-tools/{tool_fqn}` returns `200`
- Within 60 seconds, `tools/list` no longer includes the tool (SC-013 / FR-019)
- No platform restart required

## S18 — Catalog TTL expiry triggers fresh fetch

Setup: Redis cache entry for server expired. Agent execution starts.  
Expected:
- `MCPToolRegistry.resolve_agent_catalog` detects cache miss
- Fresh `tools/list` request sent to external server
- Redis cache updated with new TTL
- `mcp.catalog.refreshed` Kafka event emitted (FR-015)

## S19 — Stale catalog returned on fetch failure

Setup: External server returns 503 on catalog refresh. DB cache entry exists.  
Expected:
- `MCPToolRegistry` returns DB-cached catalog with `is_stale=True`
- Agent can still invoke cached tools
- `mcp.catalog.stale` Kafka event emitted; retry scheduled (FR-016)

## S20 — MCP protocol version mismatch rejected

Setup: External MCP client sends `protocolVersion: "1999-01-01"` in initialize.  
Expected:
- `POST /api/v1/mcp/protocol/initialize` returns `400` with `code: protocol_version_unsupported`, `supported: ["2024-11-05"]`
- Response latency ≤ 100ms p95 (SC-009)
- No tool catalog loaded

## S21 — Transient vs. permanent failure classification

Setup: External MCP server returns HTTP 503 (transient) on tool call, then an invalid JSON-RPC response (permanent).  
Expected:
- 503: `MCPToolResult.error_classification=transient`; agent receives retry-safe hint; audit `outcome=error_transient`
- Invalid response: `MCPToolResult.error_classification=permanent`; agent receives terminal error; audit `outcome=error_permanent`
- Both classifications distinguishable in audit log (SC-010 / FR-013)

## S22 — Non-exposed tool probe reveals no internal metadata

Setup: External MCP client guesses an internal tool name and calls `tools/call`.  
Expected:
- Response: MCP `tool_not_found` error
- Response body contains NO internal stack traces, NO internal tool names beyond exposed subset (FR-014)

## S23 — Health status visible within 30 seconds of state change

Setup: External MCP server becomes unreachable.  
Expected:
- Within 30 seconds, `GET /api/v1/mcp/servers/{server_id}` shows `health.status=unhealthy`
- Redis health key `cache:mcp_server_health:{server_id}` updated on first failed invocation (SC-014 / FR-022)

## S24 — Agent with no `mcp_servers` list unaffected

Setup: Existing agent without `mcp_servers` field in config.  
Expected:
- `MCPToolRegistry.resolve_agent_catalog` returns empty list immediately
- No MCP handshake attempted
- Execution proceeds as before (backward compatibility / SC-005)

## S25 — MCP invocation rate limit enforced per principal

Setup: External MCP client at rate limit (60 req/min default).  
Expected:
- 61st request within window returns HTTP 429 (or MCP error `rate_limit_exceeded`)
- `MCPInvocationAuditRecord` written with `outcome=denied`, `block_reason=rate_limit`
- Rate-limit enforcement mirrors native tool limits (FR-021)
