# Tasks: MCP Integration

**Input**: Design documents from `specs/066-mcp-integration/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on in-progress tasks)
- **[Story]**: Which user story (US1–US5)

---

## Phase 1: Setup

**Purpose**: Migration and bounded context skeleton — must exist before any story work begins.

- [X] T001 Create `apps/control-plane/src/platform/mcp/__init__.py` (empty package marker)
- [X] T002 Create `apps/control-plane/migrations/versions/053_mcp_integration.py` with 3 enums (`mcp_server_status`, `mcp_invocation_direction`, `mcp_invocation_outcome`), 4 tables (`mcp_server_registrations`, `mcp_exposed_tools`, `mcp_catalog_cache`, `mcp_invocation_audit_records`), and `ADD COLUMN mcp_server_refs JSONB NOT NULL DEFAULT '[]'` + GIN index on `registry_agent_profiles`; down_revision = `052_a2a_gateway`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, exceptions, events, repository, and base schemas — required by every user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Add `MCP_*` settings block to `apps/control-plane/src/platform/common/config.py`: `MCP_CATALOG_TTL_SECONDS=3600`, `MCP_MAX_PAYLOAD_BYTES=10_485_760`, `MCP_INVOCATION_TIMEOUT_SECONDS=30`, `MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE=60`, `MCP_PROTOCOL_VERSION="2024-11-05"`
- [X] T004 [P] Create `apps/control-plane/src/platform/mcp/models.py` with SQLAlchemy models: `MCPServerRegistration` (id, workspace_id, display_name, endpoint_url, auth_config JSONB, status, catalog_ttl_seconds, last_catalog_fetched_at, catalog_version_snapshot, created_by, timestamps), `MCPExposedTool` (id, workspace_id, tool_fqn, mcp_tool_name, mcp_description, mcp_input_schema JSONB, is_exposed, created_by, timestamps), `MCPCatalogCache` (id, server_id FK, tools_catalog JSONB, resources_catalog JSONB, prompts_catalog JSONB, fetched_at, version_snapshot, is_stale, next_refresh_at), `MCPInvocationAuditRecord` (id, workspace_id, principal_id, agent_id, agent_fqn, server_id, tool_identifier, direction, outcome, policy_decision JSONB, payload_size_bytes, error_code, error_classification, timestamp) plus all 3 enums using `Base, UUIDMixin, TimestampMixin` mixins
- [X] T005 [P] Create `apps/control-plane/src/platform/mcp/exceptions.py` with: `MCPError` (base), `MCPServerNotFoundError`, `MCPServerSuspendedError`, `MCPServerUnavailableError(classification: str)`, `MCPToolNotFoundError`, `MCPProtocolVersionError`, `MCPPayloadTooLargeError`, `MCPDuplicateRegistrationError`, `MCPInsecureTransportError`, `MCPPolicyDeniedError`
- [X] T006 [P] Create `apps/control-plane/src/platform/mcp/events.py` with `publish_mcp_event(producer, event_type, payload)` using `EventEnvelope` format; event types: `mcp.server.registered`, `mcp.server.suspended`, `mcp.server.deregistered`, `mcp.catalog.refreshed`, `mcp.catalog.stale`, `mcp.tool.invoked`, `mcp.tool.denied`; topic = `"mcp.events"`
- [X] T007 Create `apps/control-plane/src/platform/mcp/repository.py` with `MCPRepository` class: `create_server`, `get_server`, `list_servers`, `update_server`, `get_exposed_tools`, `upsert_exposed_tool`, `get_catalog_cache`, `upsert_catalog_cache`, `create_audit_record`, `list_audit_records_by_agent` — all async using `AsyncSession`; follows `PolicyRepository` pattern (depends on T004)
- [X] T008 Create `apps/control-plane/src/platform/mcp/schemas.py` with Pydantic v2 schemas: `MCPServerRegisterRequest`, `MCPServerResponse`, `MCPServerPatch`, `MCPServerListResponse`, `MCPExposedToolUpsertRequest`, `MCPExposedToolResponse`, `MCPExposedToolListResponse`, `MCPCatalogResponse`, `MCPServerHealthStatus` (depends on T004)

**Checkpoint**: Foundation complete — user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Agent Discovers and Invokes External MCP Tools (Priority: P1) 🎯 MVP

**Goal**: Operators register external MCP servers; platform agents discover those servers' tools at execution start; outbound MCP tool calls pass through the tool gateway.

**Independent Test**: Register a test MCP server. Add its UUID to a test agent's `mcp_servers`. Start execution. Verify (a) tools discovered with `mcp:{server_id}:{tool_name}` identifiers, (b) gateway check called before outbound request, (c) result returned to agent after sanitization (quickstart S4, S6, S7).

- [X] T009 [P] [US1] Create `apps/control-plane/src/platform/common/clients/mcp_client.py` with `MCPClient(base_url, auth_config, *, http_client, timeout_seconds)` class: `async initialize() → MCPCapabilities`, `async list_tools() → list[MCPToolDefinition]`, `async call_tool(name, arguments) → MCPToolResult`; uses `httpx.AsyncClient`; raises `MCPServerUnavailableError` on connection/timeout, `MCPProtocolVersionError` on handshake mismatch; follows `common/clients/reasoning_engine.py` pattern
- [X] T010 [P] [US1] Add optional `mcp_servers: list[str] = []` to `AgentManifest`, `AgentProfileResponse`, and `AgentPatch` schemas in `apps/control-plane/src/platform/registry/schemas.py`; `AgentPatch.mcp_servers` is `list[str] | None = None` (None = no change, [] = clear); map to `mcp_server_refs` column in `AgentProfile` ORM model
- [X] T011 [US1] Create `apps/control-plane/src/platform/mcp/service.py` with `MCPService` class: `register_server(workspace_id, request, created_by)` → validates HTTPS, checks duplicate, creates record, publishes `mcp.server.registered`; `get_server`, `list_servers`, `update_server` (suspend/reactivate), `deregister_server`; `get_server_health(server_id)` → reads Redis `cache:mcp_server_health:{server_id}` HASH with DB fallback; constructor: `(repository, settings, producer, redis_client)` (depends on T007, T008, T006, T005)
- [X] T012 [US1] Create `apps/control-plane/src/platform/registry/mcp_registry.py` with `MCPToolRegistry` class: `resolve_agent_catalog(agent_id, workspace_id, session)` → reads `AgentProfile.mcp_server_refs`, resolves active `MCPServerRegistration` records (skip suspended/deregistered), for each server checks Redis `cache:mcp_catalog:{server_id}`, on miss fetches via `MCPClient.list_tools()`, stores in Redis with TTL from `MCP_CATALOG_TTL_SECONDS`, returns `list[MCPToolBinding]` with identifiers `mcp:{server_id}:{tool_name}`; `invoke_tool(tool_fqn, arguments, *, execution_ctx)` → parses `mcp:{server_id}:{tool_name}`, calls `MCPClient.call_tool`, returns `MCPToolResult`; constructor: `(mcp_service, settings, redis_client)` (depends on T009, T011)
- [X] T013 [US1] Extend `apps/control-plane/src/platform/policies/gateway.py` `ToolGatewayService.validate_tool_invocation`: add an additive `if tool_fqn.startswith("mcp:")` branch that (a) extracts `server_id` from FQN, (b) verifies `server_id` is in the agent's `mcp_server_refs` list (raises `permission_denied` if not), (c) passes the namespaced `tool_fqn` through all four existing checks unchanged; MUST NOT touch the `else` path for non-`mcp:` fqns (SC-005 no-regression) (depends on T012, T010)
- [X] T014 [US1] Create `apps/control-plane/src/platform/mcp/router.py` with `APIRouter(prefix="/api/v1/mcp", tags=["mcp"])`: `POST /servers`, `GET /servers`, `GET /servers/{server_id}`, `PATCH /servers/{server_id}`, `DELETE /servers/{server_id}` — all operator-only (RBAC check); inject `MCPService` via `Depends`; follow `a2a_gateway/router.py` error-handling pattern (depends on T011, T008)
- [X] T015 [US1] Mount `mcp_router` in `apps/control-plane/src/platform/main.py` alongside existing routers (depends on T014)

**Checkpoint**: US1 fully functional — agent discovers and invokes external MCP tools through the gateway.

---

## Phase 4: User Story 2 — External MCP Client Discovers and Invokes Platform Tools (Priority: P1)

**Goal**: External MCP clients connect to the platform as an MCP server; they discover operator-exposed platform tools and invoke them through the tool gateway.

**Independent Test**: Mark 2 platform tools as `is_exposed=true`. Connect an external MCP client, call `tools/list`, verify only those 2 tools returned. Call `tools/call`; verify gateway enforced and result returned in MCP format (quickstart S13, S14, S15, S16).

- [X] T016 [P] [US2] Add exposed-tools management endpoints to `apps/control-plane/src/platform/mcp/router.py`: `GET /exposed-tools`, `PUT /exposed-tools/{tool_fqn}` — operator-only; add `toggle_exposure(tool_fqn, is_exposed)` method to `MCPService`; invalidate Redis discovery cache for exposed-tools on toggle (depends on T014, T011)
- [X] T017 [US2] Create `apps/control-plane/src/platform/a2a_gateway/mcp_server.py` with `MCPServerService` class: `handle_initialize(request, principal)` → validates `MCP_PROTOCOL_VERSION`, returns capabilities; `handle_tools_list(principal, workspace_id)` → queries `MCPExposedTool WHERE is_exposed=true` via `MCPService`, returns MCP-compliant tool list; `handle_tools_call(name, arguments, principal, workspace_id, session)` → resolves native `tool_fqn` from `mcp_tool_name`, calls `ToolGatewayService.validate_tool_invocation`, executes tool, pipes result through `OutputSanitizer`, returns MCP canonical format; constructor: `(mcp_service, tool_gateway_service, sanitizer, settings)` (depends on T013, T016)
- [X] T018 [US2] Add MCP protocol routes to `apps/control-plane/src/platform/a2a_gateway/router.py`: `POST /api/v1/mcp/protocol/initialize`, `POST /api/v1/mcp/protocol/tools/list`, `POST /api/v1/mcp/protocol/tools/call`; auth via `AuthService.validate_token()` from `Authorization` header; inject `MCPServerService` via `Depends`; return MCP error format `{"code": -32603, "message": ..., "data": {"code": "..."}}` on failures (depends on T017)

**Checkpoint**: US2 fully functional — external MCP clients discover and invoke platform tools.

---

## Phase 5: User Story 3 — All MCP Interactions Flow Through Tool Gateway (Priority: P1)

**Goal**: Every MCP interaction (inbound and outbound) produces an `MCPInvocationAuditRecord`; rate limits enforced per-principal in both directions; `mcp.tool.invoked` / `mcp.tool.denied` Kafka events emitted.

**Independent Test**: With deny-all outbound policy, verify outbound MCP calls denied with audit record and `mcp.tool.denied` event. Inbound: submit invocation from principal without permission; verify denial + audit + event (quickstart S7, S14, S22, S25).

- [X] T019 [P] [US3] Add `MCPInvocationAuditRecord` writes to `apps/control-plane/src/platform/registry/mcp_registry.py` `invoke_tool`: write audit record for every outcome (`allowed`, `denied`, `error_transient`, `error_permanent`) via `MCPRepository.create_audit_record`; emit `mcp.tool.invoked` or `mcp.tool.denied` event (depends on T012, T006, T007)
- [X] T020 [P] [US3] Add `MCPInvocationAuditRecord` writes to `apps/control-plane/src/platform/a2a_gateway/mcp_server.py` `handle_tools_call`: write audit record with `direction=inbound` for every outcome; emit `mcp.tool.invoked` or `mcp.tool.denied` event (depends on T017, T006, T007)
- [X] T021 [US3] Add per-principal rate-limit check to `apps/control-plane/src/platform/a2a_gateway/mcp_server.py` `handle_tools_call`: call `AsyncRedisClient.check_rate_limit("mcp", str(principal_id), MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE, 60_000)` before gateway check; return `429` / MCP error on breach; write audit record with `block_reason="rate_limit"` (depends on T020)
- [X] T022 [US3] Add per-principal rate-limit check to `apps/control-plane/src/platform/registry/mcp_registry.py` `invoke_tool` (outbound direction): same `check_rate_limit` call; on breach write audit record with `outcome=denied, block_reason="rate_limit"` (depends on T019)

**Checkpoint**: US3 fully functional — every MCP interaction is audited and rate-limited.

---

## Phase 6: User Story 4 — Error Handling and Resilience for MCP Failures (Priority: P2)

**Goal**: Transient vs. permanent failure classification surfaces to callers; health status updated on every outcome; operator can see server health within 30 seconds.

**Independent Test**: Stop external test server. Invoke tool; verify `error_classification=transient`, retry-safe hint. Send malformed response; verify `error_classification=permanent`. Check `GET /servers/{id}` shows health degraded within 30s (quickstart S21, S23).

- [X] T023 [P] [US4] Add error classification to `apps/control-plane/src/platform/common/clients/mcp_client.py`: HTTP 5xx / timeout → raise `MCPServerUnavailableError(classification="transient")`; invalid JSON / unexpected response structure → raise `MCPServerUnavailableError(classification="permanent")`; explicit MCP error payload → raise `MCPToolError(code, message, classification="permanent")`; add `retry_safe: bool` field to `MCPServerUnavailableError` (depends on T009)
- [X] T024 [P] [US4] Add health aggregate update to `apps/control-plane/src/platform/mcp/service.py` `_update_health(server_id, outcome)`: writes Redis HASH `cache:mcp_server_health:{server_id}` — fields: `status` (healthy/degraded/unreachable), `last_success_at`, `error_count_5m` (sliding counter, TTL 5m), `last_error_at`; HASH TTL = 90s; called after every catalog fetch and tool invocation (depends on T011)
- [X] T025 [US4] Surface error classification in `apps/control-plane/src/platform/registry/mcp_registry.py` `invoke_tool`: catch `MCPServerUnavailableError` and `MCPToolError`; set `MCPToolResult.error_classification` from exception; call `MCPService._update_health(server_id, outcome)` after each invocation; emit `mcp.catalog.stale` if classification is transient (depends on T023, T024, T019)
- [X] T026 [US4] Add health data to `GET /api/v1/mcp/servers/{server_id}` response in `apps/control-plane/src/platform/mcp/router.py`: call `MCPService.get_server_health(server_id)` and include `MCPServerHealthStatus` in `MCPServerResponse`; health reads Redis with DB `last_catalog_fetched_at` fallback (depends on T024, T014)

**Checkpoint**: US4 fully functional — failures classified; operator health visible.

---

## Phase 7: User Story 5 — External MCP Tool Catalog Caching and Refresh (Priority: P3)

**Goal**: Redis hot-tier cache (TTL-based); DB durable fallback with staleness flag; APScheduler background refresh job; operator can force-refresh or view cached catalog.

**Independent Test**: Register server, call `resolve_agent_catalog` twice within TTL — verify single outbound fetch. Expire TTL; verify fresh fetch. Kill server; verify stale DB catalog returned with `is_stale=True` (quickstart S5, S18, S19).

- [X] T027 [P] [US5] Add DB durable-tier cache upsert to `apps/control-plane/src/platform/mcp/repository.py` `upsert_catalog_cache`: write `MCPCatalogCache` row after each successful fetch; update `is_stale=False`, `fetched_at`, `version_snapshot`, `next_refresh_at = now() + ttl`; read on Redis miss; follows `MCPCatalogCache` model from T004 (depends on T007)
- [X] T028 [P] [US5] Add Redis hot-tier cache write/read to `apps/control-plane/src/platform/registry/mcp_registry.py` `resolve_agent_catalog`: after successful `MCPClient.list_tools()` fetch, write `cache:mcp_catalog:{server_id}` (JSON-serialized catalog) with TTL from `MCP_CATALOG_TTL_SECONDS`; on Redis HIT return cached catalog without outbound fetch; detect version change between `version_snapshot` and live capabilities (FR-025) — invalidate on mismatch (depends on T012)
- [X] T029 [US5] Add stale-fallback path to `apps/control-plane/src/platform/registry/mcp_registry.py` `resolve_agent_catalog`: on `MCPClient` fetch failure, check `MCPRepository.get_catalog_cache(server_id)`; if found return cached catalog with `is_stale=True`; emit `mcp.catalog.stale` Kafka event; schedule next retry at `now() + catalog_ttl_seconds` by updating `MCPCatalogCache.next_refresh_at`; if no DB cache exists, skip server and log warning (depends on T028, T027, T025)
- [X] T030 [US5] Add APScheduler background job `mcp_catalog_refresh` to `apps/control-plane/src/platform/mcp/service.py`: runs every 60s; queries `MCPCatalogCache WHERE next_refresh_at <= now()`; for each server calls `MCPToolRegistry.resolve_agent_catalog` with `force_refresh=True` bypass; emits `mcp.catalog.refreshed` on success; register job in app lifespan in `main.py` (depends on T029, T011)
- [X] T031 [US5] Add `GET /api/v1/mcp/servers/{server_id}/catalog` and `POST /api/v1/mcp/servers/{server_id}/refresh` endpoints to `apps/control-plane/src/platform/mcp/router.py`: catalog endpoint reads `MCPRepository.get_catalog_cache` and returns `MCPCatalogResponse`; refresh endpoint calls `MCPService.force_refresh(server_id)` which sets `next_refresh_at = now()` and triggers scheduler; operator-only (depends on T030, T027, T014)

**Checkpoint**: US5 fully functional — catalog cached, refreshed automatically, stale fallback works.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T032 [P] Verify migration integrity: run `make migrate-check` to confirm migration 053 applies cleanly on top of 052; verify `registry_agent_profiles.mcp_server_refs` column exists and defaults to `[]`
- [X] T033 [P] Add `mcp/dependencies.py` with `get_mcp_service()`, `get_mcp_tool_registry()` FastAPI dependency factories following the pattern in `a2a_gateway/` — inject `MCPRepository`, `MCPService`, `MCPToolRegistry` via `Depends` in `mcp/router.py` and `a2a_gateway/router.py`
- [X] T034 Validate acceptance scenarios S1–S25 from `specs/066-mcp-integration/quickstart.md` against the implemented endpoints and service interfaces

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — first P1 story, no story dependencies
- **US2 (Phase 4)**: Depends on US1 Phase 3 (needs `ToolGatewayService` mcp: branch from T013)
- **US3 (Phase 5)**: Depends on US1 (T012) and US2 (T017) — audit writes on both directions
- **US4 (Phase 6)**: Depends on US1 (T009, T011) — error classification in MCPClient
- **US5 (Phase 7)**: Depends on US1 (T012) — cache layers on top of discovery
- **Polish (Phase 8)**: Depends on all user stories

### User Story Completion Order

```
Phase 1 (Setup) → Phase 2 (Foundational)
  → US1 (Phase 3)
      → US2 (Phase 4)
          → US3 (Phase 5, depends US1+US2)
  → US4 (Phase 6, depends US1)      ← can start in parallel with US2 once US1 complete
  → US5 (Phase 7, depends US1)      ← can start in parallel with US2/US4 once US1 complete
→ Polish (Phase 8)
```

### Parallel Opportunities Within Each Phase

**Phase 2**: T003, T004, T005, T006 all parallel → T007 and T008 after T004.

**Phase 3 (US1)**: T009 and T010 parallel → T011 (needs T005–T008) → T012 (needs T009, T011) → T013 → T014 → T015.

**Phase 4 (US2)**: T016 parallel with T017 setup → T017 (needs T013, T016) → T018.

**Phase 5 (US3)**: T019 and T020 parallel → T021 and T022 parallel.

**Phase 6 (US4)**: T023 and T024 parallel → T025 → T026.

**Phase 7 (US5)**: T027 and T028 parallel → T029 → T030 → T031.

---

## Parallel Example: Phase 2 (Foundational)

```bash
# All four parallel tasks together:
Task T003: Add MCP_* settings to common/config.py
Task T004: Create mcp/models.py (4 models + 3 enums)
Task T005: Create mcp/exceptions.py
Task T006: Create mcp/events.py

# Then sequentially:
Task T007: Create mcp/repository.py  ← needs T004
Task T008: Create mcp/schemas.py     ← needs T004
```

## Parallel Example: Phase 3 (US1)

```bash
# Parallel:
Task T009: Create common/clients/mcp_client.py
Task T010: Add mcp_servers field to registry/schemas.py

# Then:
Task T011: Create mcp/service.py     ← needs T007, T008, T006, T005
Task T012: Create registry/mcp_registry.py  ← needs T009, T011
Task T013: Extend policies/gateway.py       ← needs T012, T010
...
```

---

## Implementation Strategy

### MVP: US1 + US2 + US3 (3 P1 Stories)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T008)
3. Complete Phase 3: US1 (T009–T015) — agents invoke external MCP tools
4. **VALIDATE**: Test S4, S5, S6, S7, S9, S10, S11 from quickstart.md
5. Complete Phase 4: US2 (T016–T018) — external clients invoke platform tools
6. **VALIDATE**: Test S13, S14, S15, S16, S17 from quickstart.md
7. Complete Phase 5: US3 (T019–T022) — full audit + rate limits
8. **VALIDATE**: Test S22, S25 from quickstart.md
9. **SHIP MVP** — bidirectional MCP with full gateway enforcement

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 complete → agents consume external MCP tools (primary value)
3. US2 complete → external clients use platform tools (server mode)
4. US3 complete → full audit trail, rate limits (security complete)
5. US4 complete → resilience + health visibility (operational hardening)
6. US5 complete → catalog caching (performance optimization)

### Parallel Team Strategy

Once Foundational (Phase 2) is complete:
- Developer A: US1 (T009–T015) — MCPClient, MCPToolRegistry, gateway extension
- Developer B: Can start US4 T023 (error classification) in parallel with US1 since MCPClient is separate file
- Developer C: Drafts US2 `mcp_server.py` while waiting for T013 (gateway extension)

---

## Notes

- T013 (`policies/gateway.py` modification) is the **highest-risk task** — the `mcp:` branch MUST be additive only; any change to the existing `else` path is a regression (SC-005). Review carefully.
- T028 (Redis hot-tier) and T027 (DB durable-tier) are logically coupled but in different files — can be parallelized but must be integrated in T029.
- `mcp/router.py` is built incrementally: T014 (US1 server CRUD) → T016 (US2 exposed-tools) → T026 (US4 health) → T031 (US5 catalog). Each task extends the existing file.
- `AgentProfile.mcp_server_refs` column added in migration 053 (T002); the Pydantic schema update (T010) must align with this column name.
- All 25 quickstart scenarios in S1–S25 have corresponding tasks: S1–S3 → T011+T014, S4–S12 → T012+T013, S13–S17 → T017+T018, S18–S23 → T019–T026, S24–S25 → T010+T022.
