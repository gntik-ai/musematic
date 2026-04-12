# Tasks: Policy and Governance Engine

**Input**: Design documents from `/specs/028-policy-governance-engine/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/policies-api.md ✓, quickstart.md ✓

**Tests**: Included — SC-010 requires ≥95% test coverage.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label [US1]–[US8]

---

## Phase 1: Setup

**Purpose**: Bounded context skeleton, exceptions, and Alembic migration.

- [X] T001 Create bounded context directory `apps/control-plane/src/platform/policies/` with `__init__.py`
- [X] T002 Create `apps/control-plane/src/platform/policies/exceptions.py` — `PolicyNotFoundError(NotFoundError)`, `PolicyViolationError(AuthorizationError)`, `PolicyCompilationError(ValidationError)`, `PolicyAttachmentError(ValidationError)` inheriting from `PlatformError` hierarchy
- [X] T003 Create Alembic migration `apps/control-plane/migrations/versions/028_policy_governance_engine.py` — creates 5 tables: `policy_policies`, `policy_versions`, `policy_attachments`, `policy_blocked_action_records`, `policy_bundle_cache` with indices, FK constraints, and PostgreSQL enum types per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: SQLAlchemy models, Pydantic schemas, Kafka events, and FastAPI DI. Must be complete before any user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create `apps/control-plane/src/platform/policies/models.py` — 5 SQLAlchemy models (`PolicyPolicy`, `PolicyVersion`, `PolicyAttachment`, `PolicyBlockedActionRecord`, `PolicyBundleCache`) + enums (`PolicyScopeType`, `PolicyStatus`, `AttachmentTargetType`, `EnforcementComponent`) per data-model.md; use `Base, UUIDMixin, TimestampMixin, AuditMixin` mixins
- [X] T005 Create `apps/control-plane/src/platform/policies/schemas.py` — all Pydantic schemas per data-model.md: rule schemas (`EnforcementRuleSchema`, `MaturityGateRuleSchema`, `BudgetLimitsSchema`, `PolicyRulesSchema`), CRUD schemas (`PolicyCreate`, `PolicyUpdate`, `PolicyVersionResponse`, `PolicyResponse`, `PolicyWithVersionResponse`, `PolicyListResponse`), attachment schemas (`PolicyAttachRequest`, `PolicyAttachResponse`), composition schemas (`PolicyRuleProvenance`, `ResolvedRule`, `PolicyConflict`, `EffectivePolicyResponse`), gate schemas (`GateResult`, `SanitizationResult`), bundle schemas (`ValidationManifest`, `EnforcementBundle`)
- [X] T006 Create `apps/control-plane/src/platform/policies/events.py` — Pydantic event schemas (`PolicyCreatedEvent`, `PolicyUpdatedEvent`, `PolicyArchivedEvent`, `PolicyAttachedEvent`, `PolicyDetachedEvent`, `GateBlockedEvent`, `GateAllowedEvent`) + async publisher functions `publish_policy_event(producer, event)` and `publish_gate_blocked(producer, event)` using `EventEnvelope` wrapper; topics: `policy.events` (key: `policy_id`) and `policy.gate.blocked` (key: `agent_id`)
- [X] T007 Create `apps/control-plane/src/platform/policies/repository.py` — `PolicyRepository` with all methods per data-model.md: `create`, `get_by_id`, `list_with_filters`, `get_versions`, `get_version_by_number`, `create_attachment`, `deactivate_attachment`, `get_active_attachments`, `get_all_applicable_attachments(agent_id, workspace_id)`, `create_blocked_action_record`, `list_blocked_action_records`, `get_bundle_cache`, `upsert_bundle_cache`; all methods `async`, `AsyncSession` parameter
- [X] T008 Create `apps/control-plane/src/platform/policies/dependencies.py` — FastAPI DI providers: `get_policy_service`, `get_tool_gateway_service`, `get_memory_write_gate_service`; inject `AsyncSession`, `AsyncRedis`, `aiokafka.AIOKafkaProducer`

**Checkpoint**: Models, schemas, events, and repository ready. User story implementations can begin.

---

## Phase 3: User Story 1 — Policy Lifecycle Management (Priority: P1) 🎯 MVP

**Goal**: Platform administrator can create, version, list, filter, and archive policies via REST API.

**Independent Test**: Create policy → retrieve → update → verify version 2 created + version 1 still accessible → archive → verify absent from active listing. Run: `pytest tests/integration/policies/test_policy_crud.py`

### Tests for User Story 1

- [X] T009 [P] [US1] Create `apps/control-plane/tests/integration/policies/test_policy_crud.py` — test cases matching quickstart.md scenario 1: create policy returns version 1, update creates version 2 with original version 1 still retrievable, list with scope filter, archive removes from active listing but retains version history, invalid rules (negative budget) rejected with 422

### Implementation for User Story 1

- [X] T010 [P] [US1] Implement policy CRUD methods in `apps/control-plane/src/platform/policies/service.py` — `PolicyService.__init__`, `create_policy` (creates PolicyPolicy + PolicyVersion 1 + emits `policy.created`), `update_policy` (creates new PolicyVersion N+1 + updates `current_version_id` + emits `policy.updated`), `archive_policy` (sets status=archived + deactivates attachments + emits `policy.archived`), `get_policy`, `list_policies`, `get_version_history`, `get_version_by_number`
- [X] T011 [US1] Create `apps/control-plane/src/platform/policies/router.py` — register `APIRouter(prefix="/policies")`; implement CRUD endpoints: `POST /` (→ `service.create_policy`), `GET /` (→ `service.list_policies`), `GET /{policy_id}` (→ `service.get_policy`), `PATCH /{policy_id}` (→ `service.update_policy`), `POST /{policy_id}/archive` (→ `service.archive_policy`), `GET /{policy_id}/versions` (→ `service.get_version_history`), `GET /{policy_id}/versions/{version_number}` (→ `service.get_version_by_number`); all thin — delegate to service

**Checkpoint**: 7 CRUD endpoints live, versioning works, archiving works.

---

## Phase 4: User Story 2 — Policy Attachment and Composition (Priority: P1)

**Goal**: Operator can attach policies to agents/workspaces/global scope and resolve the effective policy with deterministic 5-level precedence and conflict provenance.

**Independent Test**: Attach global + workspace + agent policies, resolve effective policy — verify agent overrides workspace overrides global; verify conflicts listed; remove agent attachment — verify fallback to workspace+global. Run: `pytest tests/integration/policies/test_policy_composition.py`

### Tests for User Story 2

- [X] T012 [P] [US2] Create `apps/control-plane/tests/integration/policies/test_policy_composition.py` — test cases matching quickstart.md scenario 2: 3-level precedence (agent wins over workspace wins over global), deny-wins within same scope level, conflict logged with resolution annotation, attachment deactivation falls back to next scope level, provenance present on every resolved rule

### Implementation for User Story 2

- [X] T013 [P] [US2] Add attachment and composition methods to `apps/control-plane/src/platform/policies/service.py` — `attach_policy` (validates target exists + creates PolicyAttachment + emits `policy.attached`), `detach_policy` (deactivates attachment + emits `policy.detached`), `list_attachments`, `get_effective_policy` (composition algorithm: `repository.get_all_applicable_attachments` → load versions → sort by scope_level asc → merge rules with deny-wins at same level, more-specific-overrides across levels → tag each rule with provenance → detect conflicts → return `EffectivePolicyResponse`)
- [X] T014 [US2] Add attachment endpoints to `apps/control-plane/src/platform/policies/router.py` — `POST /{policy_id}/attach`, `DELETE /{policy_id}/attach/{attachment_id}`, `GET /{policy_id}/attachments`, `GET /effective/{agent_id}` (query param: `workspace_id`)

**Checkpoint**: Effective policy resolution correct, provenance tracked, conflicts detected.

---

## Phase 5: User Story 4 — Governance Compiler (Priority: P2)

**Goal**: Compile overlapping policy versions into a typed `EnforcementBundle` with task-scoped shards, conflict warnings, and Redis caching.

**Independent Test**: Compile 3-level policy set → verify bundle has merged rules + provenance in manifest; compile with negative budget → verify rejection before any bundle produced; request tool_invocation shard → verify only relevant rules. Run: `pytest tests/unit/policies/test_compiler.py`

### Tests for User Story 4

- [X] T015 [P] [US4] Create `apps/control-plane/tests/unit/policies/test_compiler.py` — test cases matching quickstart.md scenarios 6, 7: bundle merges 3 policies correctly, conflict resolved with warning in manifest, `get_shard("tool_invocation")` returns only tool rules, invalid policy (negative budget) raises `PolicyCompilationError` before returning partial bundle, fingerprint is SHA-256 hex of sorted version IDs

### Implementation for User Story 4

- [X] T016 [P] [US4] Create `apps/control-plane/src/platform/policies/compiler.py` — `GovernanceCompiler` class with `compile_bundle(policy_versions, agent_id, workspace_id) -> EnforcementBundle`; validation step (reject negative budgets, empty rule sets); merge step (build allowed/denied tool patterns, maturity gate rules, purpose rules, budget limits, safety rules per composition precedence); compute SHA-256 fingerprint of sorted version IDs; build `ValidationManifest` with conflicts + warnings; `EnforcementBundle.get_shard(step_type)` filters rules by `applicable_step_types`
- [X] T017 [US4] Add bundle retrieval methods to `apps/control-plane/src/platform/policies/service.py` — `get_enforcement_bundle(agent_id, workspace_id, session)`: check Redis key `policy:bundle:{fingerprint}` → on miss: call `repository.get_all_applicable_attachments` + load versions + call `compiler.compile_bundle` + write to Redis (TTL 300s) + upsert `policy_bundle_cache` table → return bundle; `invalidate_bundle(agent_id)`: delete Redis keys for agent
- [X] T018 [US4] Add bundle endpoints to `apps/control-plane/src/platform/policies/router.py` — `GET /bundle/{agent_id}` (query params: `workspace_id`, `step_type?`; calls `service.get_enforcement_bundle` then optionally `bundle.get_shard`), `POST /bundle/{agent_id}/invalidate`

**Checkpoint**: Compiler produces correct bundles, Redis caching works, shards filter correctly.

---

## Phase 6: User Story 3 — Tool Gateway Enforcement (Priority: P1)

**Goal**: Every tool invocation (native, MCP, A2A) validated against effective policy; blocked actions recorded; fail-safe deny-all on resolution failure.

**Independent Test**: Allow path → `GateResult(allowed=True)`; block path → `GateResult(allowed=False)` + `BlockedActionRecord` in DB + `policy.gate.blocked` Kafka event; broken DB → `GateResult(allowed=False, block_reason="policy_resolution_failure")`. Run: `pytest tests/integration/policies/test_tool_gateway.py`

### Tests for User Story 3

- [X] T019 [P] [US3] Create `apps/control-plane/tests/integration/policies/test_tool_gateway.py` — test cases matching quickstart.md scenarios 3, 4, 5: allow path (no BlockedActionRecord, no gate.blocked event), block path (BlockedActionRecord created with all required fields, gate.blocked Kafka event), budget exceeded block, fail-safe (broken session → deny-all with `policy_resolution_failure`), MCP/A2A invocation uses same gateway

### Implementation for User Story 3

- [X] T020 [P] [US3] Create `apps/control-plane/src/platform/policies/gateway.py` — `ToolGatewayService` class; `validate_tool_invocation(agent_id, agent_fqn, tool_fqn, declared_purpose, execution_id, workspace_id, session) -> GateResult`; wrap entire body in `try/except` → on any exception return `GateResult(allowed=False, block_reason="policy_resolution_failure")`; 4 sequential checks using bundle from `policy_service.get_enforcement_bundle`: (1) permission check (tool_fqn matches allowed_tool_patterns, not in denied_tool_patterns), (2) purpose check (declared_purpose in allowed_purposes and not in denied_purposes), (3) budget check (query reasoning engine gRPC client for remaining budget), (4) safety check (no safety rule explicitly denies this invocation); on fail: `await repository.create_blocked_action_record(...)` + `await publish_gate_blocked(...)`; on pass: emit `policy.gate.allowed` only if tool in `log_allowed_tools`; `sanitize_tool_output(output, ...) -> SanitizationResult` delegates to `OutputSanitizer`
- [X] T021 [US3] Add blocked action record endpoints to `apps/control-plane/src/platform/policies/router.py` — `GET /blocked-actions` (query params: `agent_id`, `enforcement_component`, `workspace_id`, `execution_id`, `since`, `page`, `page_size`), `GET /blocked-actions/{record_id}`

**Checkpoint**: Tool gateway enforces all 4 checks, BlockedActionRecord persisted, fail-safe deny-all verified.

---

## Phase 7: User Story 5 — Memory Write Gate (Priority: P2)

**Goal**: Memory writes validated for namespace authorization, per-agent rate limiting (Redis), contradiction check, and retention compliance.

**Independent Test**: Allowed namespace write proceeds; unauthorized namespace blocked with `namespace_unauthorized`; 4th write in same minute window blocked with `rate_limit_exceeded`; contradicting high-confidence entry blocked with `contradiction_detected`. Run: `pytest tests/integration/policies/test_memory_write_gate.py`

### Tests for User Story 5

- [X] T022 [P] [US5] Create `apps/control-plane/tests/integration/policies/test_memory_write_gate.py` — test cases matching quickstart.md scenarios 8, 9: namespace allowed proceeds, namespace denied creates BlockedActionRecord with `namespace_unauthorized`, rate limit creates BlockedActionRecord after N writes with `rate_limit_exceeded`, Redis counter `policy:write_rate:{agent_id}:{bucket}` incremented correctly, contradiction check blocks with `contradiction_detected`

### Implementation for User Story 5

- [X] T023 [US5] Add `MemoryWriteGateService` to `apps/control-plane/src/platform/policies/gateway.py` — `validate_memory_write(agent_id, agent_fqn, target_namespace, content_hash, workspace_id, session) -> GateResult`; 5 sequential checks: (1) namespace authorization (read agent's allowed_namespaces from bundle), (2) rate limit via Redis `INCR policy:write_rate:{agent_id}:{minute_bucket}` + `EXPIRE 120` Lua script — block if over limit, (3) namespace existence check via in-process memory service interface call, (4) contradiction check via memory service `check_contradiction(content_hash, target_namespace)`, (5) attach retention metadata from policy; on fail: persist BlockedActionRecord (enforcement_component="memory_write_gate") + emit gate.blocked; update `policies/dependencies.py` to register `MemoryWriteGateService`

**Checkpoint**: Memory write gate enforces all 5 checks, Redis rate limit works, BlockedActionRecord created on deny.

---

## Phase 8: User Story 8 — Tool Output Sanitization (Priority: P3)

**Goal**: Sanitize tool outputs for secret patterns before returning to agent context; log redaction audit records.

**Independent Test**: Bearer token in output → `[REDACTED:bearer_token]` + BlockedActionRecord; JWT token → `[REDACTED:jwt_token]`; clean output → unchanged + no record. Run: `pytest tests/unit/policies/test_sanitizer.py`

### Tests for User Story 8

- [X] T024 [P] [US8] Create `apps/control-plane/tests/unit/policies/test_sanitizer.py` — test cases matching quickstart.md scenario 14: bearer_token redacted, jwt_token redacted, api_key redacted, connection_string redacted, password_literal redacted, multi-secret output (all 5 types in one string) each replaced independently, clean output unchanged, `redaction_count` correct, BlockedActionRecord created for each redaction with `enforcement_component="sanitizer"` and no actual secret value in record

### Implementation for User Story 8

- [X] T025 [P] [US8] Create `apps/control-plane/src/platform/policies/sanitizer.py` — `OutputSanitizer` class; pre-compiled `SECRET_PATTERNS: dict[str, re.Pattern]` (bearer_token, api_key, jwt_token, connection_string, password_literal) per research.md Decision 9; `sanitize(output, agent_id, agent_fqn, tool_fqn, execution_id, session) -> SanitizationResult`; scan output for all patterns → replace matches with `[REDACTED:{type}]` → for each redaction write `PolicyBlockedActionRecord` (enforcement_component="sanitizer", action_type="sanitizer_redaction", target=secret_type, block_reason="secret_pattern_detected") → return `SanitizationResult(output, redaction_count, redacted_types)`

**Checkpoint**: Sanitizer correctly redacts all 5 secret types, audit records written without exposing actual secrets.

---

## Phase 9: User Story 6 — Maturity Gate and Purpose-Bound Authorization (Priority: P3)

**Goal**: Level-0 agent cannot access level-1+ capabilities; purpose mismatch blocks invocation; maturity levels endpoint lists capability tiers.

**Independent Test**: Level-0 agent invokes level-1 tool → blocked with `maturity_level_insufficient` including required level; same agent promoted to level 1 → invocation succeeds; "customer-support" agent invokes "financial-trading" tool → blocked with `purpose_mismatch`. Run: `pytest tests/integration/policies/test_maturity_gate.py`

### Tests for User Story 6

- [X] T026 [P] [US6] Create `apps/control-plane/tests/integration/policies/test_maturity_gate.py` — test cases matching quickstart.md scenarios 10, 11: maturity level 0 blocked with `maturity_level_insufficient` + `required_level` in policy_rule_ref, level 1 agent succeeds without policy change, purpose mismatch blocked with `purpose_mismatch`, matching purpose allowed, `GET /maturity-gates` returns structured level-to-capability mapping

### Implementation for User Story 6

- [X] T027 [US6] Integrate maturity gate and purpose checks into `apps/control-plane/src/platform/policies/gateway.py` `ToolGatewayService.validate_tool_invocation()` — (a) maturity check: after permission check, query registry service interface for `agent_maturity_level`; evaluate `bundle.maturity_gate_rules` — for each rule, if tool_fqn matches a capability pattern and agent level < min_maturity_level: return `GateResult(allowed=False, block_reason="maturity_level_insufficient", policy_rule_ref={"required_level": min_maturity_level})`; (b) purpose check: already in permission check — compare `declared_purpose` against tool's `compatible_purposes` from registry service; block with `purpose_mismatch` if no overlap
- [X] T028 [P] [US6] Add maturity gates endpoint to `apps/control-plane/src/platform/policies/router.py` — `GET /maturity-gates`: reads all active global MaturityGateRule entries from policy bundle; returns structured `{"levels": [{level: int, capabilities: [str]}]}` response

**Checkpoint**: Maturity gates block insufficient-level agents, purpose mismatches blocked, capability tiers queryable.

---

## Phase 10: User Story 7 — Visibility-Aware Discovery Enforcement (Priority: P3)

**Goal**: Registry queries filtered by agent FQN visibility patterns at SQL level; zero-trust default (empty results with no config).

**Independent Test**: Agent with `visibility_agents: ["finance-ops:*"]` gets only finance-ops agents; agent with no config gets 0 results; workspace-level grants union with per-agent patterns. Run: `pytest tests/integration/policies/test_visibility_filter.py`

### Tests for User Story 7

- [X] T029 [P] [US7] Create `apps/control-plane/tests/integration/policies/test_visibility_filter.py` — test cases matching quickstart.md scenarios 12, 13: zero-trust default (empty query result), wildcard FQN pattern filters correctly, workspace-level grant unions with agent patterns, SQL-level filtering confirmed (no post-filter — count DB rows returned by query, not application-filtered)

### Implementation for User Story 7

- [X] T030 [US7] Add `get_visibility_filter(agent_id) -> VisibilityFilter` to `apps/control-plane/src/platform/policies/service.py` — reads agent profile from registry service interface to get `visibility_agents` and `visibility_tools` FQN patterns; returns `VisibilityFilter(agent_patterns=[], tool_patterns=[])` (empty = zero-trust) as default when no config; unions workspace-level grants from `workspaces_service` interface
- [X] T031 [US7] Integrate `VisibilityFilter` into registry repository SQL query in `apps/control-plane/src/platform/registry/repository.py` — modify `list_agents` and `list_tools` queries to accept optional `VisibilityFilter`; translate FQN patterns to SQL predicates: exact match → `= 'ns:name'`, wildcard `ns:*` → `fqn LIKE 'ns:%'`, regex → `fqn ~ 'pattern'`; default to `WHERE 1=0` when filter is empty/None

**Checkpoint**: Registry returns zero results by default, FQN patterns filter at SQL level.

---

## Phase 11: Polish and Cross-Cutting Concerns

**Purpose**: Wire router into main API, Kafka bundle invalidation consumer, integration test coverage audit, linting.

- [X] T032 Register `policies.router` in `apps/control-plane/src/platform/api/__init__.py` — add `app.include_router(policies_router, prefix="/api/v1")`
- [X] T033 Add Kafka consumer handler in `apps/control-plane/src/platform/policies/events.py` — subscribe to `policy.events` topic; on `policy.attached` or `policy.detached` events: call `policy_service.invalidate_bundle(target_id)` to delete Redis keys for affected agent
- [X] T034 [P] Add `tests/integration/policies/__init__.py` and shared fixtures in `conftest.py` — async test session, test PostgreSQL database with migration 028 applied, mock registry service interface, mock memory service interface, mock reasoning engine gRPC stub
- [X] T035 [P] Run `pytest tests/integration/policies/ tests/unit/policies/ --cov=platform/policies --cov-report=term-missing` — confirm ≥95% line coverage; add missing test cases for any uncovered branches
- [X] T036 [P] Run `ruff check apps/control-plane/src/platform/policies/` and `mypy --strict apps/control-plane/src/platform/policies/` — fix all violations; all public functions have docstrings; all signatures fully annotated

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001–T003 sequential (migration depends on models)
- **Foundational (Phase 2)**: Depends on Phase 1; T004–T008 — T005 depends on T004 (models imported by schemas); T006 depends on T005; T007 depends on T004; T008 depends on T007
- **US1 (Phase 3)**: Depends on Foundational — T009 (tests) + T010 (service) parallelizable; T011 (router) depends on T010
- **US2 (Phase 4)**: Depends on Foundational + US1 service.py exists; T012 + T013 parallelizable; T014 depends on T013
- **US4 (Phase 5)**: Depends on Foundational + US2 (composition needed for bundle); T015 + T016 parallelizable; T017 depends on T016; T018 depends on T017
- **US3 (Phase 6)**: Depends on US4 (uses `get_enforcement_bundle`); T019 + T020 parallelizable; T021 depends on T020
- **US5 (Phase 7)**: Depends on Foundational (uses repository + events); T022 + T023 parallelizable
- **US8 (Phase 8)**: Depends on Foundational (needs `PolicyBlockedActionRecord`); T024 + T025 parallelizable
- **US6 (Phase 9)**: Depends on US3 (extends gateway.py); T026 + T027 parallelizable; T028 independent
- **US7 (Phase 10)**: Depends on Foundational + registry service interface; T029 + T030 parallelizable; T031 depends on T030
- **Polish (Phase 11)**: Depends on all user story phases; T034 + T035 + T036 parallelizable after T032 + T033

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories — start after Foundational
- **US2 (P1)**: No dependency on US1 but extends service.py and router.py — can be developed after US1 commit or in parallel in separate branch
- **US4 (P2)**: Depends on US2 (composition results used by compiler)
- **US3 (P1)**: Depends on US4 (gateway uses `get_enforcement_bundle`)
- **US5 (P2)**: Independent of US3 — can develop in parallel with US4/US3
- **US8 (P3)**: Independent of US3/US5 — can develop in parallel
- **US6 (P3)**: Extends US3 gateway — must be after US3
- **US7 (P3)**: Independent — touches registry bounded context, not policies service

---

## Parallel Example: Phases 7 + 8 simultaneously

```bash
# Developer A: US5 (Memory Write Gate)
T022 → T023

# Developer B: US8 (Output Sanitizer)
T024 → T025
```

## Parallel Example: Within US1

```bash
# Launch together after Phase 2:
Task T009: "Create test_policy_crud.py integration tests"
Task T010: "Implement PolicyService CRUD methods in service.py"
# Then:
Task T011: "Create policy CRUD router endpoints" (depends on T010)
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US4 + US3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 — Policy CRUD working
4. Complete Phase 4: US2 — Effective policy resolution working
5. Complete Phase 5: US4 — Governance compiler + bundle cache working
6. Complete Phase 6: US3 — **Tool gateway active — policies now enforced**
7. **STOP and VALIDATE**: Core enforcement loop functional end-to-end

### Incremental Delivery

1. Setup + Foundational → skeletons ready
2. + US1 → Policies can be created, versioned, archived
3. + US2 → Policies attached, effective policy resolved
4. + US4 → Bundles compiled and cached
5. + US3 → **Full enforcement active (MVP ship point)**
6. + US5 → Memory writes gated
7. + US8 + US6 + US7 → Full security hardening complete

### Parallel Team Strategy

With 3 developers after US4:
- Developer A: US3 (Tool Gateway) → US6 (Maturity Gate)
- Developer B: US5 (Memory Write Gate)
- Developer C: US8 (Output Sanitizer) → US7 (Visibility Filter)

---

## Notes

- [P] tasks = different files, no blocking dependencies — safe to run in parallel
- SC-010 requires ≥95% coverage — all test tasks are required
- **Fail-safe deny-all** (T020) is the most critical correctness property — test it first in T019
- The `GovernanceCompiler` (T016) is synchronous (CPU-bound) — do not add `async` to its `compile_bundle` method
- `OutputSanitizer` (T025) must NEVER include the actual secret value in the `PolicyBlockedActionRecord` — test this explicitly in T024
- Visibility filter (T031) modifies the `registry/` bounded context — coordinate with registry team to avoid merge conflicts; the change is additive (optional `VisibilityFilter` parameter with default `None = no filter` → but wait, default must be zero-trust, so `None = WHERE 1=0`)
- Bundle cache invalidation (T033) Kafka consumer must handle `target_type` for both agent and workspace attachments — workspace attachment change invalidates bundles for all agents in that workspace (use `invalidate_bundle_for_workspace` method)
