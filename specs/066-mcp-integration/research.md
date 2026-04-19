# Research: MCP Integration

**Feature**: 066-mcp-integration | **Date**: 2026-04-19  
**Spec**: [spec.md](spec.md)

---

## D-001: Bounded Context Split

**Decision**: Two-location structure — new `mcp/` bounded context for data models, schemas, repository, service, and operator-management router; `a2a_gateway/mcp_server.py` + `a2a_gateway/router.py` additions for the inbound MCP protocol handler (external client-facing).

**Rationale**: The operator-management CRUD (server registration, exposure toggles, catalog refresh) belongs in its own bounded context for the same reason `a2a_gateway/` was split from `policies/`. The inbound protocol handler lives in `a2a_gateway/` because A2A and MCP share the external-interoperability domain, already mounted and visible. The outbound client code lives in `common/clients/mcp_client.py` because it is a shared infrastructure primitive callable by any bounded context, following the pattern of `common/clients/reasoning_engine.py`.

**Alternatives considered**:
- All-in-one `mcp/` context: too broad — would need to re-mount a second external-facing router alongside `a2a_gateway/router.py`.
- Extend `a2a_gateway/` for everything: conflates operator CRUD with external-protocol serving; makes the A2A context harder to reason about.

---

## D-002: MCP HTTP Client Implementation

**Decision**: `common/clients/mcp_client.py` wraps `httpx.AsyncClient` with MCP protocol semantics — initialize handshake, `tools/list`, `tools/call`, `resources/list`, error classification. No new external library introduced; `httpx 0.27+` is already in requirements.txt.

**Rationale**: The codebase uses `httpx.AsyncClient` directly in `a2a_gateway/client_service.py` for external HTTP calls. MCP over HTTP(S) is a JSON-RPC-style protocol — the client module needs handshake state and response parsing, not raw HTTP; a thin class encapsulating that state fits the `common/clients/` pattern (compare `reasoning_engine.py`).

**Alternatives considered**:
- A third-party MCP SDK: not stable enough for pinning at this stage; avoids a new external dependency.
- Use `a2a_gateway/client_service.py` as the template inline: correct pattern but the MCP client is shared across `registry/mcp_registry.py` (outbound) and `a2a_gateway/mcp_server.py` (inbound), so it belongs in `common/clients/`.

---

## D-003: Tool FQN Identifier Scheme for MCP Tools

**Decision**: MCP tool identifiers use the scheme `mcp:{server_id}:{tool_name}` where `server_id` is the UUID of the `MCPServerRegistration`. `ToolGatewayService.validate_tool_invocation` parses the first `:` to extract the scheme prefix; the existing path continues unchanged for all non-`mcp:` prefixed fqns (FR-023 / SC-005 no-regression guarantee).

**Rationale**: `ToolGatewayService.validate_tool_invocation` currently accepts `tool_fqn` as a plain string and uses `fnmatch()` for pattern matching with no scheme parsing. The additive change is: check `if tool_fqn.startswith("mcp:")` before the existing path. All MCP-specific logic (server membership check, catalog resolution) branches inside this check; the original code path is untouched for any `tool_fqn` that does not start with `mcp:`.

**Alternatives considered**:
- Use `mcp/{server_ref_slug}/{tool_name}` (slash-separated): conflicts with fnmatch pattern syntax already used in enforcement bundles.
- Opaque UUIDs as tool identifiers: loses human-readable tool names in audit logs.

---

## D-004: Agent Config `mcp_servers` Field

**Decision**: Add `mcp_server_refs: list[str]` column (JSONB, default `[]`) to `registry_agent_profiles` via migration 053. Add `mcp_servers: list[str]` to `AgentManifest`, `AgentProfileResponse`, and `AgentPatch` Pydantic schemas in `registry/schemas.py`. Server references are the string UUID of the `MCPServerRegistration` record (workspace-scoped).

**Rationale**: `AgentProfile` model has several JSONB list columns already (`role_types`, `visibility_agents`, `visibility_tools`, `tags`). A new JSONB column follows the same pattern and is indexed for querying agents that reference a specific server. Storing refs as UUIDs (not URLs) means renames or URL changes to the server record don't invalidate agent configs (SC-012 stable references).

**Alternatives considered**:
- Store in `manifest_snapshot` JSONB only: no SQL-level filter capability; querying all agents using a given server requires full table scan.
- Use server URL slug: fragile to URL changes; violates stable-reference requirement.

---

## D-005: Registry Discovery Service

**Decision**: `registry/mcp_registry.py` — `MCPToolRegistry` class that runs on agent execution start, resolves the agent's `mcp_server_refs` list against live `MCPServerRegistration` records (skipping suspended/deregistered), checks Redis cache for each server's catalog, falls back to DB `MCPCatalogCache`, and returns a list of `MCPToolBinding` objects ready for the tool gateway. Catalog misses and TTL expirations trigger a fresh fetch via `MCPClient`.

**Rationale**: Placement in `registry/` co-locates discovery with agent profile resolution. This module is called by the execution engine at task-start, not at request time — it must be async, fault-tolerant (skip unreachable servers with warning rather than aborting), and cache-aware. Fits the service class pattern seen in `registry/service.py`.

**Alternatives considered**:
- Inline in execution engine: would leak MCP concerns into the workflow engine.
- Merge into `mcp/service.py`: `mcp/service.py` handles operator CRUD; discovery at execution time is a separate concern closer to the registry domain.

---

## D-006: Inbound MCP Server Implementation

**Decision**: `a2a_gateway/mcp_server.py` — `MCPServerService` class implementing the MCP server protocol: handshake (`initialize`), `tools/list` (returns operator-designated exposed tools filtered by `OutputSanitizer`-safe schemas), and `tools/call` (validates principal, calls `ToolGatewayService`, dispatches to native tool executor, sanitizes output, returns MCP-formatted result). Routes added to `a2a_gateway/router.py` under `/api/v1/mcp/`.

**Rationale**: A2A gateway router is already mounted and handles external-protocol traffic. Adding MCP inbound routes there avoids a second external-facing router mount in `main.py`. The `MCPServerService` in `a2a_gateway/mcp_server.py` mirrors `A2AServerService` in `a2a_gateway/server_service.py` — same injection pattern, same auth dependency.

**Alternatives considered**:
- Separate `mcp_gateway/` bounded context with its own router mount: clean isolation but doubles the router-mounting overhead for a small addition.

---

## D-007: New Tables and Migration

**Decision**: Migration `053_mcp_integration.py` creates 4 new tables (`mcp_server_registrations`, `mcp_exposed_tools`, `mcp_catalog_cache`, `mcp_invocation_audit_records`), 3 new enums (`mcp_server_status`, `mcp_invocation_direction`, `mcp_invocation_outcome`), and 1 new JSONB column `mcp_server_refs` on `registry_agent_profiles`. Down-revision = `052_a2a_gateway`.

**Rationale**: All DDL in Alembic (Brownfield Rule 2). The four entities map directly to the spec (FR-001, FR-009, FR-015, FR-007). No existing table is modified beyond the additive `mcp_server_refs` column.

**Alternatives considered**:
- Reuse `a2a_audit_records` for MCP audit: different fields (direction, server_id, mcp-specific outcome codes); a separate table keeps queries clean.
- Store catalog in Redis only: catalog must survive cache eviction; DB durable fallback is required (FR-016 stale fallback).

---

## D-008: Catalog Cache Strategy

**Decision**: Two-tier cache. Hot tier: Redis key `cache:mcp_catalog:{server_id}` with TTL from `PlatformSettings.MCP_CATALOG_TTL_SECONDS` (default 3600s). Warm tier: `MCPCatalogCache` DB table with `is_stale` flag. On miss/expiry → `MCPClient` fresh fetch → write both tiers. On fetch failure with warm tier hit → return DB catalog with `is_stale=True`; schedule retry via `APScheduler` job `mcp_catalog_refresh`.

**Rationale**: Mirrors the A2A external Agent Card cache pattern (`cache:a2a_card:{sha256(url)[:16]}` + `A2AExternalEndpoint.card_cached_at`). Using server UUID (not URL hash) as cache key because the UUID is already the stable reference. Redis TTL enforces the 90%-hit-rate target (SC-007); DB fallback satisfies FR-016.

**Alternatives considered**:
- Redis only with no DB fallback: violates FR-016 (stale fallback requires persistence across Redis flushes).

---

## D-009: Kafka Topic and Events

**Decision**: New topic `mcp.events` with 7 event types: `mcp.server.registered`, `mcp.server.suspended`, `mcp.server.deregistered`, `mcp.catalog.refreshed`, `mcp.catalog.stale`, `mcp.tool.invoked` (outbound allowed), `mcp.tool.denied` (outbound or inbound denied). All events use the existing `EventEnvelope` format with `correlation_id` propagation.

**Rationale**: Follows the existing Kafka topic naming convention (`a2a.events`, `policy.events`). Operator monitoring subscribes to this topic for health visibility (SC-014, FR-022). Audit trail supplements the `mcp_invocation_audit_records` DB table for streaming consumers.

**Alternatives considered**:
- Reuse `policy.events` for denials: `mcp.events` keeps a single subscriber view per integration surface; mixing topics creates fan-out confusion.

---

## D-010: Platform Settings Additions

**Decision**: Add to `PlatformSettings` (additive, `env_prefix="PLATFORM_"`):
```
MCP_CATALOG_TTL_SECONDS: int = 3600
MCP_MAX_PAYLOAD_BYTES: int = 10_485_760   # 10 MB
MCP_INVOCATION_TIMEOUT_SECONDS: int = 30
MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE: int = 60  # matches native default
MCP_PROTOCOL_VERSION: str = "2024-11-05"
```

**Rationale**: Mirrors the `A2A_*` block in `PlatformSettings` (lines 385-389). All defaults match spec Assumptions. Rate limit default mirrors native (`A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE = 60`).

---

## D-011: Inbound Authentication Pattern

**Decision**: Reuse `AuthService.validate_token()` for inbound MCP clients. External MCP clients authenticate with a platform API key or session token in the `Authorization` header. No revocation caching (mirrors A2A's D-005). External client principal is mapped to a workspace-scoped `ServiceAccount` record.

**Rationale**: Constitution Reminder 25: MCP uses the same auth surfaces as native tools. No new auth primitives (spec Assumption). `AuthService.validate_token()` returns a `TokenPayload` with `principal_id` and `workspace_id`; both are required for `ToolGatewayService.validate_tool_invocation`.

---

## D-012: Health Status Aggregation

**Decision**: Redis key `cache:mcp_server_health:{server_id}` (HASH, TTL 90s) stores `{status, last_success_at, error_count_5m, last_error_at}`. Updated by `MCPToolRegistry` on every catalog fetch/invocation. `MCPService.get_server_health(server_id)` reads from Redis with a DB fallback to last-known timestamp. Surfaced via `GET /api/v1/mcp/servers/{server_id}` (SC-014, FR-022).

**Rationale**: Same pattern as `fleet:health:{id}` from feature 033 (Redis HASH, TTL 90s). The 90s TTL allows up to 90s lag for health visibility, well within the SC-014 30s p95 requirement given the update-on-every-call pattern.
