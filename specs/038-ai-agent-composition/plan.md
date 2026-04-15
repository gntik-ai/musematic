# Implementation Plan: AI-Assisted Agent Composition

**Branch**: `038-ai-agent-composition` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/038-ai-agent-composition/spec.md`

## Summary

Build a greenfield `composition/` bounded context in the Python control plane implementing: LLM-driven agent blueprint generation from natural-language descriptions (structured httpx → JSON mode), fleet blueprint generation with topology and delegation rules, concurrent constraint validation (5 checks via service interfaces + `asyncio.gather`), append-only composition audit trail, and human override versioning. No new Python packages needed — all dependencies are already in the tech stack.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, httpx 0.27+ (LLM API calls)  
**Storage**: PostgreSQL 16 (5 tables)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Kubernetes `platform-control` namespace, `composition` runtime profile  
**Project Type**: Python modular monolith bounded context  
**Performance Goals**: Blueprint generation in <30s (25s LLM timeout + 5s buffer); validation completes in <10s (5 concurrent in-process calls); audit reads are cursor-paginated  
**Constraints**: All async (no sync I/O); append-only `composition_audit_entries`; LLM prompt MUST NEVER contain secrets (Constitution XI); no cross-boundary DB access (service interfaces only)  
**Scale/Scope**: ~10 concurrent blueprint generation requests per workspace; audit trail unbounded (cursor-paginated reads)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| I. Modular Monolith | ✅ | New `composition/` bounded context in control plane |
| III. Dedicated Data Stores | ✅ | PostgreSQL for relational blueprint state; no ClickHouse/Qdrant needed (not analytics/vector workload) |
| IV. No Cross-Boundary DB Access | ✅ | Registry, policy, connector accessed via service interfaces only |
| V. Append-Only Journal | ✅ | `composition_audit_entries` is insert-only |
| XI. Secrets Never in LLM Context | ✅ | LLM prompt contains tool names and capability descriptions only; never credentials, API keys, or connection strings |
| All async | ✅ | All service, repository, and router methods are `async def`; httpx uses async client |

**New dependency justification**: None required. `httpx 0.27+` (LLM calls) is already in the tech stack per feature 022 (context engineering) and 034 (evaluation).

**Post-Phase 1 re-check**: All design decisions comply. Blueprint versioning creates new rows (no mutation) ensuring an implicit immutable audit trail in addition to explicit `composition_audit_entries`. Validation uses `asyncio.gather` for concurrent service interface calls.

## Project Structure

### Documentation (this feature)

```text
specs/038-ai-agent-composition/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-endpoints.md       # REST endpoint contracts
│   └── service-interfaces.md  # In-process service interface contracts
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/control-plane/
├── pyproject.toml                    # No changes needed (httpx already in deps)
├── src/platform/
│   ├── main.py                       # Register composition runtime profile
│   └── composition/
│       ├── __init__.py
│       ├── models.py                 # 5 SQLAlchemy models
│       ├── schemas.py                # Pydantic request/response schemas
│       ├── service.py                # CompositionService + CompositionServiceInterface
│       ├── repository.py             # Async DB access (insert-only audit entries)
│       ├── router.py                 # FastAPI router (/api/v1/compositions)
│       ├── events.py                 # Kafka event types + CompositionEventPublisher
│       ├── exceptions.py             # CompositionError hierarchy
│       ├── dependencies.py           # FastAPI DI: get_composition_service
│       ├── llm/
│       │   ├── __init__.py
│       │   └── client.py             # LLMCompositionClient: prompt + httpx call + JSON parse
│       ├── generators/
│       │   ├── __init__.py
│       │   ├── agent.py              # AgentBlueprintGenerator: build prompt, call LLM, parse
│       │   └── fleet.py              # FleetBlueprintGenerator: fleet prompt, call LLM, parse
│       └── validation/
│           ├── __init__.py
│           └── validator.py          # BlueprintValidator: 5 checks via asyncio.gather
│
├── migrations/versions/
│   └── 038_ai_agent_composition.py   # All 5 PostgreSQL tables
│
└── tests/
    ├── unit/composition/
    │   ├── test_llm_client.py
    │   ├── test_agent_generator.py
    │   ├── test_fleet_generator.py
    │   ├── test_blueprint_validator.py
    │   ├── test_audit_recorder.py
    │   └── test_composition_service.py
    └── integration/composition/
        ├── test_agent_blueprint_endpoints.py
        ├── test_fleet_blueprint_endpoints.py
        ├── test_validation_endpoints.py
        └── test_audit_endpoints.py
```

**Structure Decision**: Single `composition/` bounded context with three focused sub-modules (`llm/`, `generators/`, `validation/`). The LLM client is isolated in its own sub-module so it can be mocked cleanly in tests. Generators are separated by blueprint type (agent vs fleet) — they share the same LLM client but have distinct prompt logic.

## Implementation Phases

### Phase 1 — Models, Schemas, Repository, Migration

**Goal**: All data models, Pydantic schemas, repository, and Alembic migration ready before any business logic.

1. Create `models.py` — all 5 SQLAlchemy models per `data-model.md`; correct mixin order (`Base → UUIDMixin → TimestampMixin → WorkspaceScopedMixin → concrete columns`); `composition_audit_entries` has no `updated_at` (append-only); JSONB columns for blueprint payloads; indexes on `(workspace_id, status)`, `(workspace_id, request_type)`
2. Create `schemas.py` — Pydantic v2 request/response schemas for all endpoints; `description` validators: min_length=1, max_length=10000; `confidence_score` ∈ [0.0, 1.0]; `version` ≥ 1
3. Create `repository.py` — all async CRUD; `insert_audit_entry()` has no update/delete counterparts; `upsert_request_status()` for status transitions; cursor-based pagination for list methods
4. Create `exceptions.py` — `CompositionError`, `LLMServiceUnavailableError` (503), `BlueprintVersionConflictError` (409), `DescriptionTooLongError` (400), all inheriting from `PlatformError`
5. Create Alembic migration `038_ai_agent_composition.py` — all 5 tables with correct column types, constraints, check constraints, indexes

---

### Phase 2 — LLM Client + Agent Blueprint Generation (US1)

**Goal**: Natural-language description → complete agent blueprint in <30s.

1. `llm/client.py` — `LLMCompositionClient.generate(system_prompt: str, user_prompt: str, response_schema: type[T]) -> T`: `async with httpx.AsyncClient(timeout=COMPOSITION_LLM_TIMEOUT_SECONDS)` POST to `COMPOSITION_LLM_API_URL`; set `response_format={type: "json_object"}` for JSON mode; parse response into `response_schema` Pydantic model; raise `LLMServiceUnavailableError` on connection error, timeout, or non-2xx response
2. `generators/agent.py` — `AgentBlueprintGenerator.generate(description, workspace_id, available_context)`: build system prompt (platform context: available tools, models, connectors, active policies — no secrets); build user prompt from description; call `LLMCompositionClient.generate`; parse into `AgentBlueprintRaw`; map to `AgentBlueprintCreate` with `confidence_score`, `low_confidence` flag, `follow_up_questions`
3. `service.py` — `CompositionService.generate_agent_blueprint(request: AgentBlueprintGenerateRequest)`: fetch workspace context (tools/models/connectors via service interfaces); insert `CompositionRequest(status='pending')`; call `AgentBlueprintGenerator.generate`; insert `AgentBlueprint`; update request `status='completed'`; insert audit entry; publish `blueprint_generated` Kafka event; on LLM error: update request `status='failed'`, insert failure audit entry, re-raise
4. `router.py` — `POST /agent-blueprint` (201), `GET /agent-blueprints/{id}`, `PATCH /agent-blueprints/{id}` (override), `POST /agent-blueprints/{id}/validate`

---

### Phase 3 — Fleet Blueprint Generation (US2)

**Goal**: Mission description → fleet topology with roles, orchestration rules, delegation, escalation.

1. `generators/fleet.py` — `FleetBlueprintGenerator.generate(description, workspace_id, available_context)`: build fleet-specific system prompt instructing LLM to produce topology type, member roles (each with inline agent blueprint structure), orchestration rules, delegation rules, escalation rules; call `LLMCompositionClient.generate`; parse into `FleetBlueprintRaw`; if single-agent heuristic (only 1 member role suggested), set `single_agent_suggestion=True`
2. `service.py` — `CompositionService.generate_fleet_blueprint(request: FleetBlueprintGenerateRequest)`: same pattern as agent blueprint generation; call `FleetBlueprintGenerator.generate`
3. `router.py` — `POST /fleet-blueprint` (201), `GET /fleet-blueprints/{id}`, `PATCH /fleet-blueprints/{id}`, `POST /fleet-blueprints/{id}/validate`

---

### Phase 4 — Blueprint Validation (US3)

**Goal**: 5 constraint checks run concurrently; cycle detection for fleet blueprints; partial validation on service unavailability.

1. `validation/validator.py` — `BlueprintValidator.validate_agent(blueprint)` and `validate_fleet(blueprint)`: `asyncio.gather(_tools_check(), _model_check(), _connectors_check(), _policy_check())` (+ `_cycle_check()` for fleet); each sub-coroutine calls appropriate service interface and returns `CheckResult(passed, details, remediation?)`; if service interface unavailable, return `CheckResult(passed=None, status='validation_unavailable')`; assemble `CompositionValidationCreate`; insert via repository; insert `blueprint_validated` audit entry
2. `validation/validator.py` — `_cycle_check(fleet_blueprint)`: pure in-process DFS on `delegation_rules + escalation_rules` graph; detect any cycles; return `CheckResult` with path of detected cycles
3. `service.py` — expose `validate_agent_blueprint(blueprint_id, workspace_id)` and `validate_fleet_blueprint(blueprint_id, workspace_id)` delegating to `BlueprintValidator`

---

### Phase 5 — Audit Trail + Human Overrides (US4 + US5)

**Goal**: Append-only audit trail queryable with filters; override versioning; re-validation of modified blueprints.

1. `repository.py` — verify `insert_audit_entry()` has no update/delete counterparts; add `get_audit_entries(request_id, workspace_id, event_type_filter, cursor, limit)` with cursor pagination on `created_at`
2. `service.py` — `override_agent_blueprint(blueprint_id, overrides, actor_id)`: apply field-path overrides to current blueprint data; insert new `AgentBlueprint` row with `version = current + 1` (old row preserved); insert `blueprint_overridden` audit entry with `{field_path, old_value, new_value, reason}` per override; `override_fleet_blueprint` same pattern
3. `router.py` — `GET /requests/{id}/audit` with `event_type`, `cursor`, `limit` query params; `GET /requests/{id}`; `GET /requests` list with `request_type`, `status` filters
4. `events.py` — `CompositionEventPublisher` wrapping `EventEnvelope` and publishing to `composition.events` topic

---

### Phase 6 — Tests, Linting, Type Checking

**Goal**: ≥95% coverage; mypy strict; ruff clean.

1. Unit tests for all sub-modules with injected mock service interfaces and pre-recorded LLM response fixtures (6 test files)
2. `test_llm_client.py` — test successful generation, LLM timeout → `LLMServiceUnavailableError`, non-2xx response → error, JSON parse failure → error
3. `test_blueprint_validator.py` — test all-pass; single tool unavailable; model unavailable; connector not configured; policy conflict; fleet cycle detection (simple cycle + complex cycle)
4. Integration tests for all endpoint groups using SQLite local mode + mock service interfaces (4 test files)
5. Edge case tests: empty description (400), description > 10000 chars (400), LLM unavailable (503), override non-existent field path (400), audit trail empty (empty list not error), fleet with no cycles passes cycle check
6. Run coverage, close gaps, mypy strict, ruff
