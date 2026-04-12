# Research: Policy and Governance Engine

**Branch**: `028-policy-governance-engine` | **Date**: 2026-04-12 | **Phase**: 0

## Decision Log

### Decision 1 — Bounded Context Location and Structure

- **Decision**: `apps/control-plane/src/platform/policies/` bounded context within the Python control plane. Standard structure: `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, with a `compiler.py` for the governance compiler and `gateway.py` for the tool gateway service.
- **Rationale**: Constitution §I mandates all bounded contexts live in the Python monolith. The `policies/` directory is already named in the repository structure. Dedicated files for compiler and gateway keep enforcement concerns clearly separated from CRUD.
- **Alternatives considered**: Separate Go microservice for the gateway (hot path performance) — rejected; gateway latency of <10ms is achievable in Python with a compiled bundle cache; separate service adds operational complexity and violates the monolith-first architecture decision.

---

### Decision 2 — PostgreSQL Schema (5 tables)

- **Decision**: Five tables owned exclusively by the `policies/` bounded context:
  1. `policy_policies` — header (id, name, description, scope_type, status, current_version_id, workspace_id, created_by, created_at, updated_at)
  2. `policy_versions` — immutable snapshots (id, policy_id, version_number, rules JSONB, change_summary, created_by, created_at)
  3. `policy_attachments` — bindings (id, policy_id, policy_version_id, target_type ENUM, target_id, created_by, created_at, is_active)
  4. `policy_blocked_action_records` — denied action audit (id, agent_id, agent_fqn, tool_fqn, action_type, enforcement_component ENUM, block_reason, policy_rule_ref JSONB, execution_id, workspace_id, created_at)
  5. `policy_bundle_cache` — compiled bundle metadata (id, fingerprint, bundle_data JSONB, source_version_ids UUID[], compiled_at, expires_at)
  Rules, capability constraints, enforcement rules, purpose scopes, and maturity gate rules are all encoded inside `policy_versions.rules` JSONB — they are immutable parts of a version snapshot and do not need normalization.
- **Rationale**: Storing rules as JSONB within the version snapshot enforces immutability (no separate table to accidentally mutate). The five separate tables give clean auditing boundaries. `policy_blocked_action_records` needs to be a proper table for audit queries, not just a Kafka event.
- **Alternatives considered**: Normalizing rules into separate tables (capability_constraints, enforcement_rules etc.) — rejected; rules are part of the version snapshot and are never modified or queried independently; JSONB gives flexibility without schema churn.

---

### Decision 3 — Policy Composition Algorithm

- **Decision**: Deterministic 5-level precedence chain: `global(0) → deployment(1) → workspace(2) → agent(3) → execution(4)`. Composition algorithm:
  1. Gather all active attachments for the agent (using agent_id, workspace_id, deployment_id, global)
  2. Load policy versions for each attachment (from DB or bundle cache)
  3. Within a scope level: merge rules additively; when rules conflict at the same level, `deny` takes precedence over `allow` (most restrictive wins)
  4. Across scope levels: more specific scope (higher number) overrides more general scope
  5. Tag each resolved rule with provenance: `{policy_id, version_id, scope_level, scope_target_id}`
  6. Detect conflicts between scopes, log them as `rule_conflict_resolved` warnings in the manifest
- **Rationale**: Determinism is required (SC-011). Deny-wins within a level is standard security posture. More-specific-overrides-general matches user mental model (workspace policy customizes global defaults). Provenance tagging is required by FR-007.
- **Alternatives considered**: Allow-wins within a level — rejected (security principle: restrict by default). Priority numbers on rules — rejected (adds user configuration burden; deterministic scope precedence is sufficient).

---

### Decision 4 — Governance Compiler

- **Decision**: `GovernanceCompiler` Python class in `policies/compiler.py`. Stateless, synchronous function `compile_bundle(policy_versions: list[PolicyVersionModel]) -> EnforcementBundle`. Validates input (rejects negative budgets, empty rule sets, self-references). Produces `EnforcementBundle` Pydantic model. Task-scoped shards computed by filtering bundle rules by `applicable_step_types: list[str]` on each rule. Compiler called by `PolicyService.get_enforcement_bundle(agent_id)` which checks Redis cache first (key: `bundle:{sha256_of_sorted_version_ids}`, TTL 300s).
- **Rationale**: Synchronous compilation is fine — it's CPU-bound not I/O-bound and completes in well under 2s for 20 policies (SC-006). Stateless design makes it easily testable. Redis caching prevents recompilation on every tool invocation.
- **Alternatives considered**: Async compiler — unnecessary; Python GIL means CPU-bound work doesn't benefit from async. Precompile bundles on policy change via Kafka consumer — rejected for v1; cache TTL is simpler and sufficient.

---

### Decision 5 — Tool Gateway

- **Decision**: `ToolGatewayService` class in `policies/gateway.py`. Entry point: `async def validate_tool_invocation(agent_id, tool_fqn, purpose, invocation_context) -> GateResult`. Four sequential checks:
  1. **Permission**: Is `tool_fqn` in the agent's allowed tools list?
  2. **Purpose**: Does `purpose` match the tool's declared compatible purposes?
  3. **Budget**: Query reasoning engine gRPC client for remaining budget; check against policy limit
  4. **Safety**: Do any safety rules explicitly deny this invocation?
  On pass: emit `policy.gate.allowed` Kafka event. On fail: persist `BlockedActionRecord` + emit `policy.gate.blocked` Kafka event. Returns `GateResult(allowed: bool, block_reason: str | None, policy_rule_ref: dict | None)`.
- **Rationale**: Sequential checks (fail fast — skip budget query if permission already denied) minimize latency. Called as a service function from the execution engine's tool dispatcher, not as middleware, so non-tool routes have no overhead.
- **Alternatives considered**: Parallel checks — rejected; permission check is cheapest and fails most often; sequential with fail-fast is more efficient. Gateway-as-middleware pattern — rejected; applies overhead to all HTTP routes.

---

### Decision 6 — Memory Write Gate

- **Decision**: `MemoryWriteGateService` class in `policies/gateway.py` (same file as tool gateway). Called by the `memory/` bounded context's `MemoryService.write_entry()` via in-process service call (injected as dependency). Five sequential checks:
  1. **Namespace authorization**: Is `target_namespace` in agent's allowed namespaces?
  2. **Rate limit**: Query Redis counter `policy:write_rate:{agent_id}:{minute_bucket}` using Lua script
  3. **Namespace existence**: Verify namespace exists (via memory service interface)
  4. **Contradiction check**: Call memory service's `check_contradiction(content, namespace)` to detect conflicts with high-confidence entries
  5. **Retention compliance**: Tag write with namespace retention metadata
  This avoids cross-boundary DB access (§IV) — the gate reads policy rules from the policies context, but namespace/contradiction checks go through the memory service interface.
- **Rationale**: In-process service injection keeps inter-context communication clean. Redis sliding-window rate limiting reuses existing Redis infrastructure. Contradiction check delegated to memory service (which owns the vector search capability).
- **Alternatives considered**: Memory write gate as a separate database table with triggers — rejected (violates §IV and §VI). Agent-managed rate limit tracking in application memory — rejected (violates §III, won't survive process restart).

---

### Decision 7 — Kafka Topics

- **Decision**: Two new Kafka topics added to the registry:
  - `policy.events` — policy lifecycle events (policy.created, policy.updated, policy.archived, policy.attached, policy.detached). Key: `policy_id`.
  - `policy.gate.blocked` — every blocked tool or memory invocation. Key: `agent_id`. High-volume topic, consumed by audit and analytics.
  `policy.gate.allowed` events are NOT emitted by default (too high volume for routine tool invocations). Instead, only emitted when `log_allowed_invocations` is set on the policy rule (for auditing specific sensitive tools).
- **Rationale**: Separating lifecycle events from gate events allows different consumer groups and retention policies. Suppressing `gate.allowed` by default follows the audit principle: log exceptions and opt-in for verbose auditing on sensitive tools only.
- **Alternatives considered**: Single `policy.events` topic for everything — rejected; gate blocked events are much higher volume than lifecycle events and need different retention. Always emitting `gate.allowed` — rejected; would flood the topic for platforms with many tool calls.

---

### Decision 8 — Redis Caching for Compiled Bundles

- **Decision**: Compiled `EnforcementBundle` serialized as JSON and stored in Redis with key `policy:bundle:{fingerprint}` where fingerprint = `SHA-256(sorted(version_ids joined with "|"))`. TTL = 300 seconds (5 minutes). Cache invalidated on `policy.attached` or `policy.detached` events via a Kafka consumer that deletes the affected agent's bundle key. Fallback: if Redis is unavailable, compile fresh on every invocation (slower but correct).
- **Rationale**: 5-minute TTL balances freshness with performance. Policy changes are rare — most tool invocations will hit the cache. Kafka-driven invalidation ensures correctness when policies are updated.
- **Alternatives considered**: No cache (recompile every invocation) — rejected; SC-003 requires <10ms gateway overhead; DB queries would violate this. Infinite TTL + explicit invalidation only — rejected; could serve stale bundles after a Redis restart.

---

### Decision 9 — Tool Output Sanitizer

- **Decision**: `OutputSanitizer` class in `policies/sanitizer.py`. Stateless, synchronous. Uses pre-compiled Python `re` patterns for each secret type:
  - `bearer_token`: `Bearer\s+[A-Za-z0-9._\-]{8,}`
  - `api_key`: `\b(sk-|key-)[A-Za-z0-9]{8,}`
  - `jwt_token`: `eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+`
  - `connection_string`: `(postgres|mysql|mongodb|redis|amqp)://[^@]+@[^/\s]+(/[^\s]*)?`
  - `password_literal`: `(?i)(password|passwd|pwd)\s*[=:]\s*\S+`
  Each match replaced with `[REDACTED:{type}]`. Every redaction logs a security audit event (not Kafka — written directly to `policy_blocked_action_records` with `enforcement_component = "sanitizer"`). Called by the tool gateway after a permitted invocation returns its output.
- **Rationale**: Pre-compiled regex patterns compile once at class instantiation, meeting the 5ms for 100KB SC-009. Direct audit record write (not Kafka) for redaction events ensures audit trail even if Kafka is unavailable.
- **Alternatives considered**: ML-based secret detection — rejected; too slow, too many false positives for structured data. Hashicorp Vault pattern scanning — not available in the runtime path. Post-hoc log scanning — rejected (secrets would already be in LLM context, violating §XI).

---

### Decision 10 — Visibility-Aware Registry Filtering

- **Decision**: The registry discovery API in the `registry/` bounded context accepts an optional `agent_id` parameter. When provided, the `PolicyService` (injected into the registry service via in-process dependency) provides a `VisibilityFilter` containing the agent's `visibility_agents` and `visibility_tools` FQN patterns. The registry repository translates these patterns to SQL predicates: exact FQN uses `=`, wildcard `namespace:*` uses `namespace || ':' || '%'` with `LIKE`, regex uses PostgreSQL `~` operator. Applied in the `WHERE` clause of the registry query — not post-filter. Default (no visibility config): `WHERE 1=0` (returns empty — zero-trust §IX).
- **Rationale**: SQL-level filtering meets SC-008 (same latency as unfiltered queries) because it reduces the result set before pagination. The `PolicyService` injection follows §IV (no cross-boundary DB access). Default-deny (`WHERE 1=0`) implements §IX zero-trust.
- **Alternatives considered**: Post-filter in application code — rejected; FR-024 explicitly requires query-level filtering. Separate discovery service — rejected; over-engineering; the registry already owns agent profiles.

---

### Decision 11 — Maturity Gate and Purpose-Bound Authorization

- **Decision**: Maturity gate rules stored within `policy_versions.rules` JSONB as `maturity_gate_rules: [{min_maturity_level: int, capability_patterns: ["external_api", "cross_namespace_memory", ...]}]`. The tool gateway's permission check reads the agent's current maturity level (via in-process call to registry service interface, which reads from `registry_agent_profiles`) and evaluates maturity gate rules. Purpose-bound authorization: each tool registration includes `compatible_purposes: list[str]` (stored in the registry). The gateway's purpose check compares the invocation's declared purpose against the tool's `compatible_purposes` + agent's `declared_purpose`.
- **Rationale**: Maturity gate rules co-located with other policy rules (JSONB) means no separate table. Reading maturity level via in-process call respects §IV. Tool purpose tags stored in the registry (which owns tool registrations) — the gateway reads them via service interface.
- **Alternatives considered**: Separate `maturity_gate_rules` table — rejected; JSONB in version snapshot is sufficient and enforces immutability. Maturity level cached in policies — rejected; would go stale when trust context promotes an agent.

---

### Decision 12 — Alembic Migration

- **Decision**: Migration `028_policy_governance_engine` adds 5 new tables: `policy_policies`, `policy_versions`, `policy_attachments`, `policy_blocked_action_records`, `policy_bundle_cache`. Also adds `compatible_purposes: ARRAY(Text)` and `applicable_maturity_level: Integer` columns to `registry_agent_profiles` (via a separate migration in the registry context's models, coordinated with the policies team).
- **Rationale**: Each bounded context controls its own tables (§IV). The registry columns addition requires coordination but is cleaner than storing tool purposes in the policies tables.
- **Alternatives considered**: Store tool purposes in policies context — rejected; would require reading registry data from the policies context's own table (violates §IV). Store in a shared table — rejected (no shared tables in the modular monolith).
