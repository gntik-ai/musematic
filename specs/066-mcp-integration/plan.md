# Implementation Plan: MCP Integration

**Branch**: `066-mcp-integration` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/066-mcp-integration/spec.md`

## Summary

Implement bidirectional MCP (Model Context Protocol) integration as an additive extension across three existing bounded contexts plus two new modules. **Client mode**: `MCPToolRegistry` (new, in `registry/`) discovers and caches external MCP server tool catalogs at agent-execution start; `MCPClient` (new, in `common/clients/`) handles the HTTP protocol; `ToolGatewayService` is extended with an `mcp:` identifier scheme so outbound MCP tool invocations pass through the same four-check gateway as native tools. **Server mode**: `MCPServerService` (new, in `a2a_gateway/`) implements the inbound MCP server protocol (initialize, tools/list, tools/call) backed by operator-controlled `MCPExposedTool` records. A new `mcp/` bounded context holds the operator-management CRUD (server registration, exposure toggles, catalog refresh, health). Four new PostgreSQL tables + one JSONB column addition via Alembic migration 053. One new Kafka topic `mcp.events`. All MCP interactions pass through `ToolGatewayService` and `OutputSanitizer` without new gate types (additive only).

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+, APScheduler 3.x — all already in requirements.txt  
**Storage**: PostgreSQL 16 (4 new tables + 1 column via Alembic 053) + Redis (hot catalog cache + health aggregates)  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux, Kubernetes  
**Project Type**: Web service — additive extension in existing FastAPI monolith  
**Performance Goals**: Gateway denial ≤ 100ms p95 (SC-009); exposure toggle propagation ≤ 60s (SC-013); health status propagation ≤ 30s p95 (SC-014); catalog cache hit ≥ 90% within TTL (SC-007)  
**Constraints**: MCP external-only (FR-020 + Reminder 25); HTTPS-only outbound (FR-017); no new gate types in ToolGatewayService (FR-023 no-regression); additive ONLY to tool_gateway.py (SC-005)  
**Scale/Scope**: 2 new bounded context modules + extensions to 4 existing files, 1 migration, 1 Kafka topic, ~12–14 source files

## Constitution Check

*All principles checked against this feature design.*

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | New `mcp/` bounded context inside existing Python monolith; `a2a_gateway/` additions in existing context |
| **Principle III** — Dedicated data stores | ✅ PASS | PostgreSQL for durable state; Redis for hot cache/health; no in-memory shared state |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `MCPToolRegistry` reads registry via `RegistryService`; `MCPServerService` reads exposed tools via `MCPService` |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | `ToolGatewayService` enforces inbound and outbound MCP authz; `OutputSanitizer` on all results |
| **Principle VIII** — FQN addressing | ✅ PASS | MCP tool FQN scheme `mcp:{server_id}:{tool_name}` uses server UUID; no ambiguity possible |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Inbound MCP requests pass through auth + authorization before any tool code; outbound blocked by tool gateway unless explicitly permitted |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | `OutputSanitizer` applied to all MCP tool results in both directions (FR-005, FR-012) |
| **Reminder 25** — MCP tools through tool gateway | ✅ PASS | FR-004 + FR-011: every MCP invocation calls `ToolGatewayService.validate_tool_invocation` before network/tool execution |
| **Reminder 22** — MCP external-only | ✅ PASS | FR-020 + Out of Scope block: MCP is not usable for internal platform-to-platform routing |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | `tool_gateway.py` is additive (`mcp:` prefix branch); `registry/schemas.py` adds optional fields |
| **Brownfield Rule 2** — Alembic migrations | ✅ PASS | All DDL in migration 053 |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Service/repo/schema pattern; `EventEnvelope`; `AsyncRedisClient`; `ToolGatewayService`; `OutputSanitizer` |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | `mcp_servers` field is optional with default `[]`; existing agents unchanged |
| **Reminder 29** — No MinIO in app code | ✅ PASS | No object storage needed for MCP integration |

## Project Structure

### Documentation (this feature)

```text
specs/066-mcp-integration/
├── plan.md              ✅ This file
├── research.md          ✅ Phase 0 output
├── data-model.md        ✅ Phase 1 output
├── quickstart.md        ✅ Phase 1 output
├── contracts/
│   └── rest-api.md      ✅ Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/control-plane/
├── migrations/versions/
│   └── 053_mcp_integration.py              # NEW: 4 tables + 3 enums + 1 column
└── src/platform/
    ├── mcp/                                # NEW bounded context (operator CRUD)
    │   ├── __init__.py
    │   ├── models.py                       # MCPServerRegistration, MCPExposedTool, MCPCatalogCache, MCPInvocationAuditRecord + enums
    │   ├── schemas.py                      # Pydantic request/response schemas
    │   ├── repository.py                   # DB operations for all 4 tables
    │   ├── service.py                      # MCPService: registration, catalog refresh, health, exposure toggle
    │   ├── exceptions.py                   # MCP-specific exceptions
    │   ├── events.py                       # Kafka event publishing (mcp.events topic)
    │   └── router.py                       # FastAPI endpoints: 9 operator routes
    ├── common/clients/
    │   └── mcp_client.py                   # NEW: httpx-based MCP protocol client (initialize, tools/list, tools/call)
    ├── registry/
    │   └── mcp_registry.py                 # NEW: MCPToolRegistry — discovery, catalog caching (Redis + DB fallback)
    ├── policies/
    │   └── gateway.py                      # MODIFY: additive mcp: scheme branch in validate_tool_invocation
    ├── registry/
    │   └── schemas.py                      # MODIFY: mcp_servers field on AgentManifest, AgentProfileResponse, AgentPatch
    ├── a2a_gateway/
    │   ├── mcp_server.py                   # NEW: MCPServerService — inbound MCP protocol handler
    │   └── router.py                       # MODIFY: add 3 MCP protocol routes under /api/v1/mcp/protocol/
    └── main.py                             # MODIFY: mount mcp_router
```

## Complexity Tracking

No constitution violations. All existing surfaces reused additively. `tool_gateway.py` modification is the highest-risk file — the no-regression guarantee (SC-005) requires the `mcp:` branch to be a pure prefix-check branch with zero changes to the existing code path.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:
- D-001: Two-location structure — `mcp/` bounded context for operator CRUD + `a2a_gateway/` additions for protocol handler
- D-002: `MCPClient` in `common/clients/mcp_client.py` using `httpx.AsyncClient` (no new dependency)
- D-003: Tool FQN scheme `mcp:{server_id}:{tool_name}`; gateway parses `mcp:` prefix; original path unchanged
- D-004: `mcp_server_refs: JSONB NOT NULL DEFAULT '[]'` column on `registry_agent_profiles`; `mcp_servers: list[str]` in Pydantic schemas
- D-005: `MCPToolRegistry` in `registry/mcp_registry.py`; called by execution engine at task start
- D-006: `MCPServerService` in `a2a_gateway/mcp_server.py`; routes added to `a2a_gateway/router.py`
- D-007: Migration `053_mcp_integration.py`; down-revision = `052_a2a_gateway`
- D-008: Two-tier cache: Redis `cache:mcp_catalog:{server_id}` TTL 3600s + `MCPCatalogCache` DB fallback
- D-009: New Kafka topic `mcp.events` with 7 event types; all use `EventEnvelope`
- D-010: `MCP_*` block added to `PlatformSettings`: `MCP_CATALOG_TTL_SECONDS=3600`, `MCP_MAX_PAYLOAD_BYTES=10485760`, `MCP_INVOCATION_TIMEOUT_SECONDS=30`, `MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE=60`, `MCP_PROTOCOL_VERSION="2024-11-05"`
- D-011: Inbound auth via `AuthService.validate_token()` — no revocation caching (mirrors A2A D-005)
- D-012: Redis `cache:mcp_server_health:{server_id}` HASH TTL 90s for health aggregation

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 4 new tables, 3 new enums, 1 new column, Redis keys, Kafka events
- [contracts/rest-api.md](contracts/rest-api.md) — 9 operator endpoints + 3 MCP protocol endpoints + 3 internal service interfaces
- [quickstart.md](quickstart.md) — 25 acceptance scenarios (S1–S25)
