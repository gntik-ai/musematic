# Tasks: AI-Assisted Agent Composition

**Input**: Design documents from `/specs/038-ai-agent-composition/`  
**Branch**: `038-ai-agent-composition`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included — acceptance criteria requires ≥95% line coverage (pytest + pytest-asyncio 8.x, mypy strict, ruff).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task serves (US1–US5 from spec.md)

## Path Conventions

All paths relative to `apps/control-plane/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the composition bounded context directory skeleton and register the runtime profile.

- [X] T001 Create `apps/control-plane/src/platform/composition/` directory with empty `__init__.py`; create sub-module directories: `llm/`, `generators/`, `validation/` — each with empty `__init__.py`
- [X] T002 Register `composition` runtime profile in `apps/control-plane/src/platform/main.py` — add conditional block that imports and mounts `composition.router` when `RUNTIME_PROFILE=composition`

**Checkpoint**: `python -m platform.main` starts with `RUNTIME_PROFILE=composition` without import errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All 5 SQLAlchemy models, Pydantic schemas, repository, Alembic migration, exceptions, Kafka events publisher, and FastAPI dependencies — required before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Create `apps/control-plane/src/platform/composition/models.py` — all 5 SQLAlchemy models in correct mixin order (`Base → UUIDMixin → TimestampMixin → WorkspaceScopedMixin → concrete columns`): `CompositionRequest`, `AgentBlueprint`, `FleetBlueprint`, `CompositionValidation`, `CompositionAuditEntry` (no `updated_at`, no update/delete); JSONB columns (`tool_selections`, `connector_suggestions`, `policy_recommendations`, `context_profile`, `member_roles`, `orchestration_rules`, etc.); indexes per data-model.md; CheckConstraints for enums
- [X] T004 Create `apps/control-plane/src/platform/composition/schemas.py` — Pydantic v2 request/response schemas for all 5 user stories; field validators: `description` min_length=1 max_length=10000, `confidence_score` ∈ [0.0, 1.0], `version` ≥ 1, `topology_type` ∈ allowed set, `maturity_estimate` ∈ allowed set; `AgentBlueprintGenerateRequest`, `FleetBlueprintGenerateRequest`, `AgentBlueprintOverrideRequest`, `FleetBlueprintOverrideRequest`, and all response schemas
- [X] T005 Create `apps/control-plane/src/platform/composition/repository.py` — `CompositionRepository` async class with all CRUD methods; `insert_audit_entry()` with no `update_audit_entry()` or `delete_audit_entry()` counterparts; `upsert_request_status()`; cursor-based pagination for `list_requests()` and `get_audit_entries()`
- [X] T006 Create `apps/control-plane/src/platform/composition/exceptions.py` — `CompositionError`, `LLMServiceUnavailableError` (503), `BlueprintVersionConflictError` (409), `DescriptionTooLongError` (400), `BlueprintNotFoundError` (404), all inheriting from project's `PlatformError`
- [X] T007 Create `apps/control-plane/src/platform/composition/events.py` — `CompositionEventPublisher` class with async `publish(event_type, request_id, workspace_id, payload, actor_id=None)` method wrapping `EventEnvelope` and publishing to `composition.events` Kafka topic (key: `composition_request_id`)
- [X] T008 Create `apps/control-plane/src/platform/composition/dependencies.py` — `Annotated[CompositionService, Depends(get_composition_service)]` dependency; `get_composition_service` factory wiring `CompositionRepository`, `CompositionEventPublisher`, `LLMCompositionClient`, and 3 service interface clients (registry, policy, connector)
- [X] T009 Create `apps/control-plane/migrations/versions/038_ai_agent_composition.py` — Alembic migration creating all 5 tables with correct column types, check constraints, and indexes per data-model.md; no ClickHouse DDL needed for this feature
- [X] T010 Create `apps/control-plane/src/platform/composition/service.py` stub — `CompositionService` class with empty method signatures for all operations; constructor accepts repository, publisher, LLM client, and service interface clients

**Checkpoint**: `make migrate` applies migration cleanly; `mypy` finds no import errors in the composition package; all models and schemas importable.

---

## Phase 3: User Story 1 — Generate Agent Blueprint from Description (Priority: P1) 🎯 MVP

**Goal**: Natural-language description → complete agent blueprint (model config, tools, connectors, policies, context profile, maturity estimate) in <30 seconds.

**Independent Test**: Submit a description "Create a research agent that can browse the web and summarize findings" to `POST /api/v1/compositions/agent-blueprint`. Confirm response within 30s contains all required sections (model_config, tool_selections, connector_suggestions, policy_recommendations, context_profile, maturity_estimate, confidence_score). Confirm `CompositionRequest` status transitions to `completed`. Confirm audit entry `blueprint_generated` created.

### Tests for User Story 1

- [X] T011 [P] [US1] Write unit tests in `apps/control-plane/tests/unit/composition/test_llm_client.py` — mock httpx; test successful generation returns parsed Pydantic response; test LLM timeout → `LLMServiceUnavailableError`; test non-2xx response → `LLMServiceUnavailableError`; test JSON parse failure → `LLMServiceUnavailableError`; test retry logic (2 retries on 503)
- [X] T012 [P] [US1] Write unit tests in `apps/control-plane/tests/unit/composition/test_agent_generator.py` — mock `LLMCompositionClient`; test blueprint generated from description with workspace context; test `low_confidence=True` when confidence_score < 0.5; test `follow_up_questions` populated when low_confidence; test description passed through to prompt; test available tools/models included in system prompt context

### Implementation for User Story 1

- [X] T013 [US1] Implement `apps/control-plane/src/platform/composition/llm/client.py` — `LLMCompositionClient.generate(system_prompt: str, user_prompt: str, response_schema: type[T]) -> T`: `async with httpx.AsyncClient(timeout=COMPOSITION_LLM_TIMEOUT_SECONDS)` POST to `COMPOSITION_LLM_API_URL`; set `response_format={"type": "json_object"}`; on connection error/timeout raise `LLMServiceUnavailableError`; on non-2xx raise `LLMServiceUnavailableError`; parse response body as `response_schema` Pydantic model; retry up to `COMPOSITION_LLM_MAX_RETRIES` on 503; include `COMPOSITION_LLM_MODEL` in request body
- [X] T014 [US1] Implement `apps/control-plane/src/platform/composition/generators/agent.py` — `AgentBlueprintGenerator.generate(description: str, workspace_id: UUID, workspace_context: WorkspaceCompositionContext) -> AgentBlueprintRaw`: build system prompt including `workspace_context` (available tool names + capability descriptions, model identifiers + tiers, connector types + names, active policy names — **never credentials**); build user prompt from `description`; call `LLMCompositionClient.generate(system_prompt, user_prompt, AgentBlueprintRaw)`; set `low_confidence = confidence_score < COMPOSITION_LOW_CONFIDENCE_THRESHOLD`
- [X] T015 [US1] Implement `generate_agent_blueprint()` in `apps/control-plane/src/platform/composition/service.py` — fetch workspace context from service interfaces (tools, models, connectors via `RegistryServiceInterface.get_available_tools/models`, connectors via `ConnectorServiceInterface.list_workspace_connectors`); insert `CompositionRequest(status='pending')`; call `AgentBlueprintGenerator.generate`; insert `AgentBlueprint`; update request `status='completed'`; insert `blueprint_generated` audit entry; publish Kafka event; on `LLMServiceUnavailableError`: update request `status='failed'`, insert `generation_failed` audit entry, re-raise
- [X] T016 [US1] Add agent blueprint endpoints to `apps/control-plane/src/platform/composition/router.py` — `POST /agent-blueprint` (201 with `AgentBlueprintResponse`), `GET /agent-blueprints/{blueprint_id}` (404 if not found); both workspace-scoped from JWT; mount router at `/api/v1/compositions`
- [X] T017 [P] [US1] Write integration tests in `apps/control-plane/tests/integration/composition/test_agent_blueprint_endpoints.py` — mock LLM client with pre-recorded fixture; test `POST /agent-blueprint` returns 201 with correct schema; test `POST /agent-blueprint` with empty description returns 400; test `POST /agent-blueprint` with LLM unavailable returns 503; test `GET /agent-blueprints/{id}` returns 200; test `GET /agent-blueprints/{non-existent-id}` returns 404

**Checkpoint**: `POST /api/v1/compositions/agent-blueprint` generates a complete agent blueprint; request status transitions correctly; audit entry created.

---

## Phase 4: User Story 2 — Generate Fleet Blueprint from Mission (Priority: P2)

**Goal**: Mission description → fleet topology with member roles, orchestration rules, delegation/escalation paths in <30 seconds.

**Independent Test**: Submit "I need a data pipeline team: one agent to fetch data from APIs, one to transform it, one to generate reports" to `POST /api/v1/compositions/fleet-blueprint`. Confirm 3 member roles with distinct purposes. Confirm `topology_type` is `sequential`. Confirm delegation rules route output between stages. Confirm `single_agent_suggestion=false`. Confirm audit entry created.

### Tests for User Story 2

- [X] T018 [P] [US2] Write unit tests in `apps/control-plane/tests/unit/composition/test_fleet_generator.py` — mock `LLMCompositionClient`; test fleet with 3 roles returns correct topology; test single-role response sets `single_agent_suggestion=True`; test delegation rules contain from_role, to_role, trigger_condition; test escalation rules include urgency field; test `low_confidence=True` when confidence_score < 0.5

### Implementation for User Story 2

- [X] T019 [US2] Implement `apps/control-plane/src/platform/composition/generators/fleet.py` — `FleetBlueprintGenerator.generate(description: str, workspace_id: UUID, workspace_context: WorkspaceCompositionContext) -> FleetBlueprintRaw`: build fleet-specific system prompt instructing LLM to produce topology type (sequential/hierarchical/peer/hybrid), member roles (each with inline agent blueprint structure), orchestration rules, delegation rules, escalation rules; if only 1 member role in response, set `single_agent_suggestion=True`; call same `LLMCompositionClient` as agent generator
- [X] T020 [US2] Implement `generate_fleet_blueprint()` in `apps/control-plane/src/platform/composition/service.py` — same lifecycle pattern as `generate_agent_blueprint()` but calling `FleetBlueprintGenerator.generate` and inserting `FleetBlueprint`
- [X] T021 [US2] Add fleet blueprint endpoints to `apps/control-plane/src/platform/composition/router.py` — `POST /fleet-blueprint` (201 with `FleetBlueprintResponse`), `GET /fleet-blueprints/{blueprint_id}` (404 if not found); workspace-scoped
- [X] T022 [P] [US2] Write integration tests in `apps/control-plane/tests/integration/composition/test_fleet_blueprint_endpoints.py` — mock LLM client; test `POST /fleet-blueprint` returns 201 with correct schema including member_roles array; test `single_agent_suggestion=true` for single-role response; test `POST /fleet-blueprint` with empty description returns 400; test `GET /fleet-blueprints/{id}` returns 200

**Checkpoint**: `POST /api/v1/compositions/fleet-blueprint` generates a fleet blueprint with topology and delegation rules; audit entry created.

---

## Phase 5: User Story 3 — Validate Composition Blueprint (Priority: P2)

**Goal**: All 5 constraint checks run concurrently; per-check pass/fail with remediation guidance; cycle detection for fleet blueprints; graceful fallback when service interface unavailable.

**Independent Test**: Generate an agent blueprint with a tool that does not exist in the workspace. Call `POST /agent-blueprints/{id}/validate`. Confirm `tools_check.passed=false` with specific tool name flagged. Confirm `overall_valid=false`. Confirm `CompositionValidation` row inserted. Confirm `blueprint_validated` audit entry created. Then call validate on a valid fleet blueprint with circular delegation and confirm `cycle_check.passed=false` with the cycle path in details.

### Tests for User Story 3

- [X] T023 [P] [US3] Write unit tests in `apps/control-plane/tests/unit/composition/test_blueprint_validator.py` — mock all 3 service interfaces; test all-pass → `overall_valid=True`; test single tool unavailable → `overall_valid=False`; test model unavailable; test connector not configured; test policy conflict; test `asyncio.gather` runs all 5 checks even when one fails (no short-circuit); test cycle_check=None for agent blueprints; test simple fleet cycle (A→B→A) detected; test complex multi-hop cycle; test service interface unavailable → status `validation_unavailable` (not exception)

### Implementation for User Story 3

- [X] T024 [US3] Implement `apps/control-plane/src/platform/composition/validation/validator.py` — `BlueprintValidator.validate_agent(blueprint, workspace_id)` and `validate_fleet(blueprint, workspace_id)`: `asyncio.gather(_tools_check(), _model_check(), _connectors_check(), _policy_check())` + `_cycle_check()` for fleet only; each sub-coroutine calls service interface and returns `CheckResult(passed: bool | None, details: list | dict, remediation: str | None)`; if service interface raises exception, catch and return `CheckResult(passed=None, status='validation_unavailable')`; assemble `CompositionValidationCreate`; `_cycle_check()` runs pure DFS on `delegation_rules + escalation_rules` adjacency graph, returns `CheckResult(passed=not has_cycle, details={cycles_found: [...]})` 
- [X] T025 [US3] Implement `validate_agent_blueprint()` and `validate_fleet_blueprint()` in `apps/control-plane/src/platform/composition/service.py` — fetch blueprint from repository; call `BlueprintValidator.validate_agent/fleet`; insert `CompositionValidation` via repository; insert `blueprint_validated` audit entry; publish Kafka event; return validation response
- [X] T026 [US3] Add validation endpoints to `apps/control-plane/src/platform/composition/router.py` — `POST /agent-blueprints/{blueprint_id}/validate`, `POST /fleet-blueprints/{blueprint_id}/validate`; return `CompositionValidationResponse`; 404 if blueprint not found
- [X] T027 [P] [US3] Write integration tests in `apps/control-plane/tests/integration/composition/test_validation_endpoints.py` — mock service interfaces; test `POST /validate` with all-pass returns `overall_valid: true`; test tool unavailable returns `overall_valid: false` with tool name in details; test fleet cycle detected returns `cycle_check.passed: false`; test service interface unavailable returns `overall_valid: false` with `validation_unavailable` status

**Checkpoint**: Validation runs all 5 checks concurrently; cycle detection works for fleet blueprints; service interface failures degrade gracefully.

---

## Phase 6: User Story 4 — Track Composition Audit Trail (Priority: P3)

**Goal**: Append-only audit trail queryable per request with event_type filter and cursor pagination; full provenance of generation, validation, override, and finalization events.

**Independent Test**: Generate an agent blueprint. Validate it. Query `GET /requests/{id}/audit`. Confirm two entries: `blueprint_generated` and `blueprint_validated` in chronological order. Confirm cursor pagination returns correct `next_cursor`. Confirm `insert_audit_entry()` in repository has no `update_audit_entry()` or `delete_audit_entry()` counterparts.

### Tests for User Story 4

- [X] T028 [P] [US4] Write integration tests in `apps/control-plane/tests/integration/composition/test_audit_endpoints.py` — test `GET /requests/{id}/audit` returns entries in chronological order; test `event_type` filter returns only matching events; test cursor pagination returns correct pages; test `GET /requests/{id}` returns request with status; test `GET /requests` list filters by request_type and status; test audit trail for non-existent request returns 404

### Implementation for User Story 4

- [X] T029 [US4] Verify `apps/control-plane/src/platform/composition/repository.py` `insert_audit_entry()` has no update/delete counterparts — add assertion comment; implement `get_audit_entries(request_id, workspace_id, event_type_filter=None, cursor=None, limit=50)` using cursor on `created_at` timestamp; implement `get_request(request_id, workspace_id)` and `list_requests(workspace_id, request_type=None, status=None, cursor=None, limit=20)`
- [X] T030 [US4] Add audit trail and request endpoints to `apps/control-plane/src/platform/composition/router.py` — `GET /requests/{request_id}/audit` with `event_type`, `limit`, `cursor` query params returning `{items: [], next_cursor}`; `GET /requests/{request_id}` returning `CompositionRequestResponse`; `GET /requests` with `request_type`, `status`, `limit`, `cursor` query params; all workspace-scoped from JWT

**Checkpoint**: Full audit trail queryable per request; pagination works; list endpoint filterable by type and status.

---

## Phase 7: User Story 5 — Apply and Track Human Overrides (Priority: P3)

**Goal**: Field-path overrides create new blueprint versions; full override history recorded in audit trail with old/new values; modified blueprints re-validatable.

**Independent Test**: Generate an agent blueprint (version 1). Submit a PATCH with `{"overrides": [{"field_path": "model_config.model_id", "new_value": "claude-sonnet-4-6", "reason": "cost optimization"}]}`. Confirm response has `version: 2` with updated `model_config.model_id`. Confirm version 1 row still exists in DB. Confirm `blueprint_overridden` audit entry with `old_value`, `new_value`, `field_path`, and actor_id. Submit PATCH again → `version: 3`. Then call validate on version 3 and confirm validation runs against updated model.

### Tests for User Story 5

- [X] T031 [P] [US5] Write unit tests in `apps/control-plane/tests/unit/composition/test_composition_service.py` — test `override_agent_blueprint()` creates version N+1 row with updated field; test old version row preserved in DB; test `blueprint_overridden` audit entry contains correct old_value, new_value, field_path, actor_id; test invalid field_path raises 400; test `override_fleet_blueprint()` same behavior; test re-validation after override validates the latest version (not original)

### Implementation for User Story 5

- [X] T032 [US5] Implement `override_agent_blueprint(blueprint_id, overrides, actor_id, workspace_id)` and `override_fleet_blueprint(...)` in `apps/control-plane/src/platform/composition/service.py` — fetch current blueprint (latest version); apply each field-path override using deep merge; track `{field_path, old_value, new_value, reason}` per override; insert new `AgentBlueprint` row with `version = current_version + 1` (old row preserved); insert `blueprint_overridden` audit entry with overrides list in payload; publish Kafka event
- [X] T033 [US5] Add override endpoints to `apps/control-plane/src/platform/composition/router.py` — `PATCH /agent-blueprints/{blueprint_id}` returning `AgentBlueprintResponse` with new version; `PATCH /fleet-blueprints/{blueprint_id}` returning `FleetBlueprintResponse`; 404 if blueprint not found; 400 if field_path invalid

**Checkpoint**: Override creates new version; old versions preserved; audit trail captures full override history; re-validation works against latest version.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Coverage closure, strict type checking, lint, and final integration validation.

- [X] T034 [P] Run `pytest apps/control-plane/tests/unit/composition/ --cov=platform/composition --cov-report=term-missing` and add targeted tests for any uncovered branches; focus on error paths (DB failures, service interface failures, Kafka publish failures, field_path resolution errors)
- [X] T035 [P] Run `mypy --strict apps/control-plane/src/platform/composition/` and fix all type errors; pay special attention to JSONB column typing, `asyncio.gather` return type unpacking, `httpx.Response` parsing, Pydantic v2 generic model usage
- [X] T036 [P] Run `ruff check apps/control-plane/src/platform/composition/` and fix all lint errors; ensure all public methods have docstrings per constitution coding conventions
- [X] T037 [P] Add `COMPOSITION_*` settings to `apps/control-plane/src/platform/common/config.py` (PlatformSettings): `COMPOSITION_LLM_API_URL`, `COMPOSITION_LLM_MODEL`, `COMPOSITION_LLM_TIMEOUT_SECONDS = 25.0`, `COMPOSITION_LLM_MAX_RETRIES = 2`, `COMPOSITION_DESCRIPTION_MAX_CHARS = 10000`, `COMPOSITION_LOW_CONFIDENCE_THRESHOLD = 0.5`, `COMPOSITION_VALIDATION_TIMEOUT_SECONDS = 10.0`
- [X] T038 Validate full feature integration: run `make migrate` against clean DB; start with `RUNTIME_PROFILE=composition`; confirm `GET /api/v1/compositions/requests` returns 200; run `pytest tests/integration/composition/ -v --tb=short` and confirm all pass

**Checkpoint**: `pytest --cov` reports ≥95% coverage; `mypy --strict` and `ruff check` both exit 0; integration test suite passes against local DB.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1)**: Depends on Phase 2 — independent of US2–US5
- **Phase 4 (US2)**: Depends on Phase 2 + Phase 3 (reuses `LLMCompositionClient` and workspace context fetching from US1)
- **Phase 5 (US3)**: Depends on Phase 2 — validation is independent; can run after US1 or US2 exists to have blueprints to validate
- **Phase 6 (US4)**: Depends on Phase 2 — audit entries are written throughout US1/US2/US3 automatically; only the query endpoints are new
- **Phase 7 (US5)**: Depends on Phase 2 + Phase 3 (overrides need at least agent blueprints to exist)
- **Phase 8 (Polish)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: After Foundation — core LLM + agent generation; independent MVP
- **US2 (P2)**: After US1 — reuses `LLMCompositionClient` and `WorkspaceCompositionContext` fetching pattern
- **US3 (P2)**: After Foundation — validation is standalone; needs blueprints to exist for testing (US1 provides these)
- **US4 (P3)**: After Foundation — audit entries are written by US1/US2/US3; only query surface is new
- **US5 (P3)**: After US1 — overrides work on existing blueprints created by US1/US2

### Within Each User Story

- Unit tests → implementation → integration tests
- Models/exceptions (Phase 2) before services; services before endpoints
- LLM client (T013) before generators (T014, T019)

### Parallel Opportunities

- US3, US4, US5 can run in parallel after US1 completes (all use different files)
- All `[P]` test tasks within each phase run concurrently
- Foundation tasks T003–T010 have sequential dependencies within them (models before schemas before repository)

---

## Parallel Example: Foundation Phase (Phase 2)

```bash
# Sequential order within foundation:
T003 → models.py           # First
T004 → schemas.py          # After models (schemas import model enums)
T005 → repository.py       # After models
T006 → exceptions.py       # Parallel with T004/T005
T007 → events.py           # Parallel with T004/T005
T008 → dependencies.py     # After service.py stub (T010)
T009 → migration           # After models.py
T010 → service.py stub     # After repository + exceptions
```

## Parallel Example: US1 + US3 (simultaneous after Foundation)

```bash
# Developer A: US1 (agent blueprint generation)
T011 → test_llm_client.py
T012 → test_agent_generator.py
T013 → llm/client.py
T014 → generators/agent.py
T015 → service.py (generate_agent_blueprint)
T016 → router.py (agent endpoints)
T017 → test_agent_blueprint_endpoints.py

# Developer B: US3 (validation) simultaneously
T023 → test_blueprint_validator.py
T024 → validation/validator.py
T025 → service.py (validate methods)
T026 → router.py (validate endpoints)
T027 → test_validation_endpoints.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundation)
2. Complete Phase 3 (US1 — Agent Blueprint Generation)
3. **STOP and VALIDATE**: Submit a natural-language description, confirm blueprint returns in <30s with all sections populated
4. Deploy/demo: `POST /api/v1/compositions/agent-blueprint` is fully functional

### Incremental Delivery

1. Foundation → US1 (agent blueprint) → **MVP demo**
2. Add US2 (fleet blueprint) → richer composition
3. Add US3 (validation) → safety before instantiation
4. Add US4 (audit trail) → governance and compliance
5. Add US5 (overrides) → human-in-the-loop control
6. Polish → production-ready

### Parallel Team Strategy

With 3 developers after Foundation:
- Developer A: US1 (agent generation) → US2 (fleet generation)
- Developer B: US3 (validation) → US5 (overrides)
- Developer C: US4 (audit trail) → Phase 8 (polish)
