# Research: A2A Protocol Gateway

**Feature**: 065-a2a-protocol-gateway | **Date**: 2026-04-19

## D-001: A2A Task Persistence — New Table vs. Interaction Extension

**Decision**: Create a new `a2a_tasks` table that links to the existing `interactions` table via `interaction_id` FK. The A2A task tracks the A2A-protocol state machine (submitted/working/input_required/completed/failed/cancelled/cancellation_pending) alongside A2A-specific metadata (task_id, protocol_version, direction, principal_id). The backing `Interaction` record tracks the internal execution state using the existing `InteractionState` enum.

**Rationale**: The interaction model already has `state` (initializing/ready/running/waiting/paused/completed/failed/canceled) and is owned by the `interactions/` bounded context. A2A state is a protocol-level projection that doesn't map 1-to-1 to internal states. A separate table keeps A2A concerns out of the interactions domain and avoids polluting the existing schema with protocol columns. The FK link satisfies FR-004 (bidirectional identifier link).

**Alternatives considered**:
- Extend `interactions` with A2A columns: rejected — breaks brownfield rule of additive-only changes to existing tables and couples two distinct bounded contexts.
- Store A2A state entirely in Redis: rejected — non-durable; A2A tasks must be recoverable across restarts.

## D-002: SSE Implementation — Starlette StreamingResponse

**Decision**: Use FastAPI/Starlette's `StreamingResponse` with an async generator that yields `data: {json}\n\n` strings and `Content-Type: text/event-stream`. No new SSE library is needed.

**Rationale**: There is no existing SSE pattern in the codebase (the platform uses WebSocket for real-time via `ws_hub/`). The WebSocket pattern requires a persistent connection manager; SSE is simpler for the A2A use case — it is one-directional (server→client), requires no session registry, and fits directly into a FastAPI endpoint. The platform's A2A streaming surface is a separate concern from the internal ws_hub.

**Alternatives considered**:
- `sse-starlette` library: adds a dependency for something achievable natively; rejected.
- WebSocket for A2A streaming: out of scope per spec Assumptions; rejected.

## D-003: Outbound Policy Check Integration

**Decision**: For outbound A2A calls, model the external endpoint as a pseudo-tool with FQN `a2a:{endpoint_id}`. Pass this as `tool_fqn` to `ToolGatewayService.validate_tool_invocation()` with the calling agent's `agent_id`, `agent_fqn`, `declared_purpose`, and `workspace_id`. This reuses all existing check logic (visibility, permission, budget, safety) without adding new policy primitives.

**Rationale**: `ToolGatewayService.validate_tool_invocation` is the existing outbound gate (file: `apps/control-plane/src/platform/policies/gateway.py`). The calling convention `tool_fqn=f"a2a:{endpoint_id}"` is consistent with how external connector targets are described in policy bundles. Operators attach policies to `a2a:*` tool patterns to control which external A2A endpoints are reachable.

**Alternatives considered**:
- New `validate_a2a_outbound()` method in ToolGatewayService: duplicates logic; rejected in favor of reuse.
- Inline policy check in the a2a_gateway service: breaks separation of concerns; rejected.

## D-004: Agent Card Generation from Registry Metadata

**Decision**: Generate Agent Cards from `AgentProfile` + the active `AgentRevision.manifest_snapshot` JSONB field. `AgentProfile` provides: `fqn` (→ Agent Card `name`), `purpose` (→ `description`). `AgentRevision.manifest_snapshot` provides: endpoint URL, version, capabilities, authentication schemes, skills (tool bindings). Agents are excluded from the public card if `status ≠ active` OR `visibility_agents` implies non-public scope OR `purpose` is empty.

**Rationale**: `manifest_snapshot` is the canonical source of agent runtime metadata per the registry design. Parsing it for Agent Card generation avoids adding new columns. The `AgentProfile.status` and `visibility_agents` fields are already populated and sufficient for public-visibility checks.

**Alternatives considered**:
- Add dedicated Agent Card columns to AgentProfile: schema change not justified; rejected.
- Hand-authored Agent Cards: spec FR-002 explicitly forbids this; rejected.

## D-005: Inbound Authentication Pattern

**Decision**: Inbound A2A requests carry a Bearer JWT in the Authorization header. Validate via `AuthService.validate_token(token)` (file: `apps/control-plane/src/platform/auth/service.py`, method `validate_token`). Revocation is checked on every request by querying the Redis session registry; no request-level caching of revocation state is permitted (per FR-028).

**Rationale**: `validate_token` raises `AccessTokenExpiredError` or `InvalidAccessTokenError` — both map cleanly to A2A authentication error responses. The method already queries the Redis session store, so revocation freshness is inherent.

**Alternatives considered**:
- API key authentication for external clients: requires a separate credential type; deferred — Bearer JWT is sufficient for launch.
- Cache revocation status per request session: rejected by FR-028.

## D-006: External Agent Card Cache — Redis Pattern

**Decision**: Cache external Agent Cards in Redis using key `cache:a2a_card:{sha256(endpoint_url)[:16]}` as a JSON blob with TTL defaulting to 3600 seconds (configurable per `ExternalA2AEndpoint.card_ttl_seconds`). Staleness is tracked via a companion key `cache:a2a_card_stale:{hash}` set when a refresh fails. The `a2a_external_endpoints` PostgreSQL record stores `cached_agent_card` (JSONB), `card_cached_at`, and `card_is_stale` for durable fallback when Redis is unavailable.

**Rationale**: The platform's Redis caching pattern uses `redis_client.set(key, json_bytes, ttl=seconds)` and `redis_client.get(key)` (see `policies/service.py` `_redis_set_json`/`_redis_get_json`). Dual-layer (Redis hot + PostgreSQL durable) matches the existing bundle cache pattern and satisfies FR-015 (stale fallback on fetch failure).

**Alternatives considered**:
- Cache in PostgreSQL only: acceptable for correctness but adds DB load on every card lookup; rejected.
- In-memory process cache: non-durable and not shared across workers; rejected per constitution Principle III.

## D-007: Audit Records — New a2a_audit_records Table

**Decision**: Write A2A audit records to a new `a2a_audit_records` PostgreSQL table (not to `policy_blocked_action_records`). A2A audits cover both success and failure events (FR-018), while `PolicyBlockedActionRecord` is purpose-built for denied/blocked events only. For denied A2A actions (outbound block, rate limit, auth failure), also write a `PolicyBlockedActionRecord` via the existing repository so policy dashboards include A2A denials.

**Rationale**: `PolicyBlockedActionRecord` has `enforcement_component` and `block_reason` fields that only make sense for blocked actions. A2A requires auditing successful task completions too. Dual-writing denied events to both tables keeps policy dashboards working without requiring changes to existing policy views.

**Alternatives considered**:
- Extend `PolicyBlockedActionRecord` with a `success` flag: schema change to an existing table; rejected.
- Write A2A audit to OpenSearch directly: no existing audit-to-OpenSearch writer pattern found; rejected.

## D-008: Rate Limiting — Existing Redis Sliding Window

**Decision**: Reuse `AsyncRedisClient.check_rate_limit("a2a", str(principal_id), limit, 60_000)` with Redis key pattern `ratelimit:a2a:{principal_id}`. The Lua script `rate_limit_check.lua` already implements a sliding window by timestamp-sorted set. Limit and window are configurable via platform settings.

**Rationale**: The platform already has a working rate-limit Lua script (`lua/rate_limit_check.lua`) and a clean `check_rate_limit` interface on `AsyncRedisClient` (file: `apps/control-plane/src/platform/common/clients/redis.py`). No new implementation is needed.

**Alternatives considered**:
- Per-agent rate limits instead of per-principal: both are needed; per-principal is primary, per-agent can be added as a second check if required.

## D-009: Multi-Turn Conversation Backing

**Decision**: Each A2A task is backed by one `Conversation` (created on task submission) and one `Interaction` per logical turn. When the platform agent signals `input_required`, the A2A task state transitions to `input_required` and the interaction state transitions to `waiting` (existing `InteractionState.waiting`). When the external client submits a follow-up, a new `Interaction` is created in the same conversation, resuming from the last turn's context.

**Rationale**: The `Interaction` model supports `conversation_id` FK, and `InteractionState.waiting` already represents paused/pending states. Reusing these removes the need for new persistence concepts. One conversation per A2A task means the full message history is recoverable for multi-turn context.

**Alternatives considered**:
- Single interaction for entire A2A task: would require mutating a single interaction record for each turn; violates the append-only journal principle.
- Separate A2A conversation model: unnecessary duplication.

## D-010: New Kafka Topic — a2a.events

**Decision**: Publish A2A lifecycle events to a new Kafka topic `a2a.events`. Event types: `a2a.task.submitted`, `a2a.task.state_changed`, `a2a.task.completed`, `a2a.task.failed`, `a2a.task.cancelled`, `a2a.outbound.attempted`, `a2a.outbound.denied`. Payload follows the existing `EventEnvelope` format with `correlation_context` populated from workspace/interaction context.

**Rationale**: All async event coordination goes through Kafka (Principle III). A dedicated `a2a.events` topic keeps A2A telemetry separate from `interaction.events` and `policy.gate.blocked`, allowing targeted consumers (operator dashboards, audit pipeline) without coupling to existing topic consumers.

**Alternatives considered**:
- Reuse `interaction.events` for A2A events: pollutes existing consumers with A2A-specific payloads; rejected.
- No Kafka topic: violates the platform event pattern; rejected.

## D-011: Alembic Migration Number

**Decision**: Use migration `052` — the next number after `051_reasoning_trace_export.py`.

**Rationale**: Migration `051` is the highest-numbered migration in `apps/control-plane/migrations/versions/`. The A2A gateway requires one migration creating three new tables (`a2a_tasks`, `a2a_external_endpoints`, `a2a_audit_records`) and one new enum `A2ATaskState`.

## D-012: Protocol Version Configuration

**Decision**: The supported A2A protocol version is a single string constant sourced from `PlatformSettings` (e.g., `A2A_PROTOCOL_VERSION = "1.0"`). All inbound requests with a different `Content-Type` version header are rejected per FR-020.

**Rationale**: The spec mandates a single pinned protocol version (Assumption). Surfacing it via `PlatformSettings` allows operators to update it without code changes when the A2A protocol evolves.
