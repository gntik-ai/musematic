# Implementation Plan: Policy and Governance Engine

**Branch**: `028-policy-governance-engine` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/028-policy-governance-engine/spec.md`

## Summary

Implement the `policies/` bounded context in the Python control plane monolith: full policy CRUD with immutable versioning, deterministic multi-scope composition (global → deployment → workspace → agent → execution), governance compiler (produces typed enforcement bundles with Redis caching), tool gateway service (permission + purpose + budget + safety checks, BlockedActionRecord persistence, Kafka events), memory write gate (namespace auth + Redis rate limiting + contradiction check), maturity-gated access, purpose-bound authorization, visibility-aware registry filtering, and tool output sanitization for LLM secret isolation.

## Technical Context

**Language/Version**: Python 3.12+ (async everywhere)
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2.x, SQLAlchemy 2.x (async), Alembic 1.13+, aiokafka 0.11+, redis-py 5.x (async), pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ (strict)
**Storage**: PostgreSQL 16+ (5 new tables: policy_policies, policy_versions, policy_attachments, policy_blocked_action_records, policy_bundle_cache), Redis 7+ (bundle cache + write rate limit counters)
**Testing**: pytest + pytest-asyncio, live PostgreSQL test DB, MSW not applicable (backend), Alembic migration tests
**Target Platform**: Linux server, Kubernetes (`platform-control` namespace)
**Project Type**: Backend bounded context within Python control plane monolith
**Performance Goals**: Effective policy resolution <100ms (SC-002), gateway enforcement <10ms with cached bundle (SC-003), memory write gate <20ms (SC-007), sanitizer 100KB output <5ms (SC-009)
**Constraints**: §I — monolith only. §IV — no cross-boundary DB. §VI — all enforcement through tool gateway. §IX — zero-trust visibility. §XI — secrets never in LLM context. Deny-all on policy resolution failure (SC-011).
**Scale/Scope**: 5 DB tables, ~8 source files, 15 REST endpoints, 2 internal service interfaces, 2 new Kafka topics, 12 decision points

## Constitution Check

| Gate | Requirement | Status |
|------|-------------|--------|
| §I.Monolith | Stay in Python control plane | PASS — `policies/` bounded context in `apps/control-plane/src/platform/policies/` |
| §III.PostgreSQL | System-of-record in PostgreSQL | PASS — 5 tables for policy state, versions, attachments, blocked records |
| §III.Redis | Hot-state caching in Redis | PASS — bundle cache `policy:bundle:{fingerprint}`, write rate limit counters |
| §III.NoVectorsInPG | No vector search in PostgreSQL | PASS — N/A; no vector operations in this feature |
| §III.Kafka | Async events via Kafka | PASS — `policy.events` + `policy.gate.blocked` topics |
| §IV.NoCrossBoundaryDB | No direct access to other contexts' tables | PASS — registry queries via in-process service interface; memory contradiction check via memory service interface |
| §VI.PolicyMachineEnforced | All enforcement through tool gateway | PASS — `ToolGatewayService` is the enforcement point; no bypass paths |
| §IX.ZeroTrustVisibility | Default: agents see nothing | PASS — `WHERE 1=0` default in visibility filter when no config present |
| §XI.SecretsNeverInLLM | Tool output sanitization before LLM context | PASS — `OutputSanitizer` runs after every tool execution, before output is returned to agent context |
| §XIV.A2AGoesThruGateway | A2A invocations through tool gateway | PASS — `a2a_gateway/` calls `ToolGatewayService.validate_tool_invocation()` |
| §XV.MCPGoesThruGateway | MCP invocations through tool gateway | PASS — MCP proxy calls same gateway service |
| QualityGates.Coverage | ≥95% line coverage (pytest) | PASS — SC-010 requires ≥95%; integration tests for all 15 scenarios |
| QualityGates.Async | All code async | PASS — all service, repository, and router methods use `async def`; compiler is sync (CPU-bound) |
| QualityGates.Types | mypy strict passes | PASS — all signatures annotated; Pydantic v2 models enforced |

**Post-design re-check**: All 14 gates PASS. Zero constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/028-policy-governance-engine/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: 12 decisions
├── data-model.md        # Phase 1: SQLAlchemy models, Pydantic schemas, service signatures
├── quickstart.md        # Phase 1: 15 test scenarios
├── checklists/
│   └── requirements.md  # Spec quality checklist (all pass)
└── contracts/
    └── policies-api.md  # Phase 1: 15 endpoints + internal service interfaces + Kafka events
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── policies/
│       ├── __init__.py
│       ├── models.py          # 5 SQLAlchemy models + enums
│       ├── schemas.py         # Pydantic request/response schemas + EnforcementBundle
│       ├── service.py         # PolicyService (CRUD, composition, bundle retrieval)
│       ├── repository.py      # PolicyRepository (all DB queries)
│       ├── compiler.py        # GovernanceCompiler (sync, stateless)
│       ├── gateway.py         # ToolGatewayService + MemoryWriteGateService
│       ├── sanitizer.py       # OutputSanitizer (regex-based, pre-compiled patterns)
│       ├── router.py          # FastAPI router (15 endpoints)
│       ├── events.py          # Kafka event schemas + publisher functions
│       ├── exceptions.py      # PolicyNotFoundError, PolicyViolationError, PolicyCompilationError
│       └── dependencies.py    # FastAPI DI: get_policy_service, get_tool_gateway, get_memory_write_gate
│
└── migrations/versions/
    └── 028_policy_governance_engine.py  # Alembic migration: 5 new tables
│
└── tests/
    ├── unit/
    │   └── policies/
    │       ├── test_compiler.py     # GovernanceCompiler unit tests
    │       └── test_sanitizer.py    # OutputSanitizer unit tests
    └── integration/
        └── policies/
            ├── test_policy_crud.py           # US1: create, update, version history, archive
            ├── test_policy_composition.py    # US2: attachment, effective policy, precedence
            ├── test_tool_gateway.py          # US3: allow, block, BlockedActionRecord, fail-safe
            ├── test_governance_compiler.py   # US4: bundle compilation, shards, validation
            ├── test_memory_write_gate.py     # US5: namespace auth, rate limit, contradiction
            ├── test_maturity_gate.py         # US6: level checks, purpose mismatch
            ├── test_visibility_filter.py     # US7: zero-trust default, FQN patterns
            └── test_output_sanitizer.py      # US8: pattern detection, redaction, audit record
```

**Structure Decision**: Standard bounded context layout per constitution §5 (Python Bounded Context Structure). Compiler and sanitizer as dedicated files (separate from service.py) because they are complex enough to warrant isolation and are independently testable. Gateway includes both tool and memory gates (same file, same service dependencies). Router is thin — all business logic in service.py.

## Implementation Phases

### Phase 1 — Database Models and Migration

**Goal**: Create the 5 PostgreSQL tables and the Alembic migration.

**Tasks**:
1. Create `policies/__init__.py`, `policies/exceptions.py`
2. Create `policies/models.py` — 5 SQLAlchemy models + enums (PolicyPolicy, PolicyVersion, PolicyAttachment, PolicyBlockedActionRecord, PolicyBundleCache) per data-model.md
3. Create `migrations/versions/028_policy_governance_engine.py` — Alembic migration creating all 5 tables with correct indices, FK constraints, enum types

### Phase 2 — Policy CRUD (US1)

**Goal**: Create, update, archive, list policies with immutable versioning.

**Tasks**:
1. Create `policies/schemas.py` — all Pydantic schemas from data-model.md
2. Create `policies/repository.py` — PolicyRepository with CRUD queries and version history
3. Create `policies/events.py` — Kafka event schemas (PolicyCreatedEvent, PolicyUpdatedEvent, PolicyArchivedEvent, PolicyAttachedEvent) + async publisher functions
4. Create `policies/service.py` — PolicyService: `create_policy`, `update_policy` (creates new version + updates current_version_id), `archive_policy`, `get_policy`, `list_policies`, `get_version_history`
5. Create `policies/dependencies.py` — FastAPI DI providers
6. Create `policies/router.py` — policy CRUD endpoints: `POST /policies`, `GET /policies`, `GET /policies/{id}`, `PATCH /policies/{id}`, `POST /policies/{id}/archive`, `GET /policies/{id}/versions`, `GET /policies/{id}/versions/{n}`
7. Create `tests/integration/policies/test_policy_crud.py` — scenarios 1 from quickstart.md

### Phase 3 — Policy Attachment and Composition (US2)

**Goal**: Attach policies to targets; resolve effective policy with deterministic precedence.

**Tasks**:
1. Add to `policies/repository.py` — `get_all_applicable_attachments(agent_id, workspace_id)` spanning all 5 scope levels
2. Add to `policies/service.py` — `attach_policy`, `detach_policy`, `get_effective_policy` (composition algorithm: gather attachments → load versions → compose by scope level → track provenance → detect conflicts)
3. Add to `policies/router.py` — attachment endpoints: `POST /policies/{id}/attach`, `DELETE /policies/{id}/attach/{attachment_id}`, `GET /policies/{id}/attachments`, `GET /policies/effective/{agent_id}`
4. Create `tests/integration/policies/test_policy_composition.py` — scenario 2 (global + workspace + agent precedence, conflict detection)

### Phase 4 — Governance Compiler (US4)

**Goal**: Compile policy versions into typed enforcement bundle with task-scoped shards.

**Tasks**:
1. Create `policies/compiler.py` — `GovernanceCompiler.compile_bundle()`: validate inputs → merge rules by scope precedence → compute fingerprint → build `EnforcementBundle` → build `ValidationManifest` with conflicts/warnings; `EnforcementBundle.get_shard(step_type)` filters rules by `applicable_step_types`
2. Add to `policies/service.py` — `get_enforcement_bundle()`: check Redis cache (`policy:bundle:{fingerprint}`) → on miss: gather applicable policy versions + call `compiler.compile_bundle()` → store in Redis (TTL 300s) + `policy_bundle_cache` table → return bundle
3. Add to `policies/router.py` — `GET /policies/bundle/{agent_id}`, `POST /policies/bundle/{agent_id}/invalidate`
4. Create `tests/unit/policies/test_compiler.py` — scenarios 6, 7: bundle correctness, conflict resolution, invalid input rejection, shard filtering

### Phase 5 — Tool Gateway and Output Sanitizer (US3 + US8)

**Goal**: Enforce every tool invocation; sanitize outputs for secret isolation.

**Tasks**:
1. Create `policies/sanitizer.py` — `OutputSanitizer` with pre-compiled regex patterns (bearer_token, api_key, jwt_token, connection_string, password_literal); `sanitize(output, agent_id, tool_fqn, ...) -> SanitizationResult`; writes `PolicyBlockedActionRecord` for each redaction (enforcement_component="sanitizer")
2. Create `policies/gateway.py` — `ToolGatewayService.validate_tool_invocation()`: fetch bundle (from `get_enforcement_bundle`) → sequential 4-check evaluation (permission → purpose → budget → safety) → on fail: persist BlockedActionRecord + emit `policy.gate.blocked` → on pass: emit `policy.gate.allowed` (opt-in) → return `GateResult`; `sanitize_tool_output()`: delegates to `OutputSanitizer`
3. Add gateway fail-safe: if `get_enforcement_bundle` raises any exception, return `GateResult(allowed=False, block_reason="policy_resolution_failure")`
4. Add to `policies/router.py` — `GET /policies/blocked-actions`, `GET /policies/blocked-actions/{id}`
5. Create `tests/integration/policies/test_tool_gateway.py` — scenarios 3, 4, 5, 14 from quickstart.md
6. Create `tests/unit/policies/test_sanitizer.py` — scenario 14: pattern tests for all 5 secret types, clean output passthrough

### Phase 6 — Memory Write Gate (US5)

**Goal**: Intercept memory writes with namespace auth, rate limiting, contradiction check.

**Tasks**:
1. Add `MemoryWriteGateService` to `policies/gateway.py` — `validate_memory_write()`: 5 sequential checks (namespace auth → rate limit via Redis Lua script → namespace existence via memory service interface → contradiction check via memory service interface → retention tag); persist BlockedActionRecord on fail; emit `policy.gate.blocked`
2. Add Redis Lua script usage for `policy:write_rate:{agent_id}:{minute_bucket}` sliding window
3. Register `MemoryWriteGateService` in `policies/dependencies.py`
4. Create `tests/integration/policies/test_memory_write_gate.py` — scenarios 8, 9 from quickstart.md

### Phase 7 — Maturity Gate, Purpose-Bound Auth, and Visibility Filter (US6 + US7)

**Goal**: Maturity-level capability gating, purpose mismatch blocking, zero-trust visibility filtering.

**Tasks**:
1. Add maturity gate check to `ToolGatewayService.validate_tool_invocation()` — read agent maturity level via registry service interface; evaluate `maturity_gate_rules` from bundle; block with `maturity_level_insufficient` if insufficient
2. Add purpose-bound check to `ToolGatewayService.validate_tool_invocation()` — compare `declared_purpose` against tool's `compatible_purposes` (from registry); block with `purpose_mismatch` if no overlap
3. Add to `policies/service.py` — `get_visibility_filter(agent_id) -> VisibilityFilter`: reads agent's `visibility_agents` + `visibility_tools` FQN patterns; returns default-deny filter if no config
4. Register visibility filter injection into registry router/repository via in-process dependency
5. Add to `policies/router.py` — `GET /policies/maturity-gates`
6. Create `tests/integration/policies/test_maturity_gate.py` — scenarios 10, 11
7. Create `tests/integration/policies/test_visibility_filter.py` — scenarios 12, 13

### Phase 8 — Bundle Cache Invalidation and Polish

**Goal**: Wire Kafka consumer for cache invalidation; full integration test coverage; ruff + mypy pass.

**Tasks**:
1. Add Kafka consumer handler for `policy.events` in `policies/events.py` — on `policy.attached` or `policy.detached`: delete affected agent's bundle keys from Redis
2. Wire `policies/router.py` into `apps/control-plane/src/platform/api/` main router
3. Verify quickstart.md scenario 15 (bundle cache hit, no DB queries on second call)
4. Run `ruff check` and `mypy --strict` — fix all violations
5. Run `pytest tests/ --cov=platform/policies --cov-report=term-missing` — confirm ≥95% coverage

## Key Decisions

See `research.md` for full rationale. Summary:

1. **5-table PostgreSQL schema** with rules as JSONB in PolicyVersion — enforces immutability, avoids schema churn
2. **Deterministic composition**: more-specific scope overrides, deny-wins within same level, provenance on every rule
3. **Governance compiler**: synchronous, stateless, Python class — CPU-bound not I/O-bound; Redis cache with SHA-256 fingerprint
4. **Tool gateway**: sequential 4-check (permission → purpose → budget → safety), fail-fast; deny-all on resolution failure
5. **Memory write gate**: Redis Lua sliding window for rate limiting, contradiction via memory service interface (no cross-boundary DB)
6. **Two new Kafka topics**: `policy.events` (lifecycle) + `policy.gate.blocked` (enforcement audit); `policy.gate.allowed` opt-in only
7. **Visibility filter**: SQL-level `WHERE` clause (not post-filter), default `WHERE 1=0` for zero-trust
8. **Output sanitizer**: 5 pre-compiled Python regex patterns, direct BlockedActionRecord write (not Kafka) for redaction audit
