# Tasks: Context Engineering Service

**Input**: Design documents from `specs/022-context-engineering-service/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/context-engineering-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package skeleton, Alembic migration, and ClickHouse setup script before any story work begins.

- [X] T001 Create `apps/control-plane/src/platform/context_engineering/` package with stub `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `adapters.py`, `quality_scorer.py`, `compactor.py`, `privacy_filter.py`, `drift_monitor.py`, `context_engineering_clickhouse_setup.py`
- [X] T002 Create Alembic migration `apps/control-plane/migrations/versions/007_context_engineering.py` — 5 tables: `context_engineering_profiles`, `context_profile_assignments`, `context_assembly_records`, `context_ab_tests`, `context_drift_alerts` with all unique constraints and indexes from data-model.md
- [X] T003 [P] Implement `apps/control-plane/src/platform/context_engineering/context_engineering_clickhouse_setup.py` — idempotent `create_context_quality_scores_table()` using MergeTree engine, `PARTITION BY toYYYYMM(created_at)`, `ORDER BY (agent_fqn, created_at)`, `TTL created_at + INTERVAL 90 DAY`; columns: agent_fqn String, workspace_id UUID, assembly_id UUID, quality_score Float32, quality_subscores JSON, token_count UInt32, ab_test_id Nullable(UUID), ab_test_group Nullable(String), created_at DateTime

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core components shared by all user stories — schemas, exceptions, adapters, quality scorer, compactor, privacy filter.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement all exception classes in `apps/control-plane/src/platform/context_engineering/exceptions.py` — `ContextEngineeringError`, `ContextSourceUnavailableError`, `ProfileNotFoundError`, `InvalidProfileAssignmentError`, `AbTestNotFoundError`, `WorkspaceAuthorizationError`, `BudgetExceededMinimumError`
- [X] T005 [P] Implement all Pydantic schemas in `apps/control-plane/src/platform/context_engineering/schemas.py` — `ContextProvenanceEntry`, `ContextElement`, `ContextBundle`, `ContextQualityScore`, `BudgetEnvelope`, `SourceConfig`, `ProfileCreate`, `ProfileResponse`, `ProfileAssignmentCreate`, `AssemblyRecordResponse`, `DriftAlertResponse`, `AbTestCreate`, `AbTestResponse`; all enums: `CompactionStrategyType`, `ContextSourceType`, `AbTestStatus`, `ProfileAssignmentLevel`
- [X] T006 [P] Implement all SQLAlchemy models and enums in `apps/control-plane/src/platform/context_engineering/models.py` — `ContextEngineeringProfile`, `ContextProfileAssignment`, `ContextAssemblyRecord`, `ContextAbTest`, `ContextDriftAlert` with all columns, constraints, and indexes from data-model.md
- [X] T007 [P] Implement `apps/control-plane/src/platform/context_engineering/adapters.py` — `ContextSourceAdapter` protocol + all 9 concrete adapters: `SystemInstructionsAdapter` (reads agent purpose+approach from registry_service), `WorkflowStateAdapter` (execution_service), `ConversationHistoryAdapter` (interactions_service), `LongTermMemoryAdapter` (Qdrant agent_memory collection), `ToolOutputsAdapter` (execution_service step outputs), `ConnectorPayloadsAdapter` (connectors_service), `WorkspaceMetadataAdapter` (workspaces_service), `ReasoningTracesAdapter` (execution_service reasoning store), `WorkspaceGoalHistoryAdapter` (workspaces_service goal messages for GID); each adapter raises `ContextSourceUnavailableError` on failure
- [X] T008 [P] Implement `apps/control-plane/src/platform/context_engineering/quality_scorer.py` — `QualityScorer` class with `SOURCE_AUTHORITY` weight table; `score(elements, task_brief, weights) → ContextQualityScore`; 6 private scoring methods: `_score_relevance()` (keyword overlap with task_brief), `_score_freshness()` (exponential decay from element timestamp), `_score_authority()` (source type weight table lookup), `_score_contradiction_density()` (detect conflicting claims), `_score_token_efficiency()` (unique information units / total tokens), `_score_task_brief_coverage()` (task brief keyword coverage); aggregate as weighted average
- [X] T009 [P] Implement `apps/control-plane/src/platform/context_engineering/compactor.py` — `ContextCompactor` with `MINIMUM_VIABLE_SOURCES` set (system_instructions always; most recent conversation turn); `compact(elements, budget, strategies) → (compacted_elements, compaction_actions)`; strategy implementations: `_relevance_truncate()` (sort by relevance score ascending, drop until budget met), `_priority_evict()` (sort by source priority ascending, drop until budget met), `_semantic_deduplicate()` (merge near-duplicates, preserve both provenances), `async _hierarchical_compress()` (LLM call via httpx, opt-in only); `_count_tokens()`, `_is_minimum_viable()` guards; emit `BudgetExceededMinimumError` if minimum viable content still exceeds budget
- [X] T010 [P] Implement `apps/control-plane/src/platform/context_engineering/privacy_filter.py` — `PrivacyFilter` with `filter(elements, agent_fqn, workspace_id) → (allowed_elements, exclusion_records)`; calls `policies_service.get_active_context_policies(workspace_id, agent_id)` with 60-second in-process TTL cache; evaluates each element's `data_classification` against agent's allowed level; returns exclusion records with `reason` and `policy_id` for inclusion in `ContextAssemblyRecord.privacy_exclusions`

**Checkpoint**: Foundation ready — user story implementation can begin.

---

## Phase 3: User Story 1 — Deterministic Context Assembly with Provenance (Priority: P1) 🎯 MVP

**Goal**: Execution context calls `assemble_context()` and receives a deterministic, fully provenanced context bundle from multiple sources. Workspace goal super-context included when `goal_id` is provided.

**Independent Test**: Configure a profile with 3 enabled sources. Call `assemble_context(execution_id=A, step_id=B, ...)` twice. Verify returned bundles are identical. Verify each element has `provenance.origin`, `timestamp`, `authority_score`. Verify `ContextAssemblyRecord` persisted with full provenance chain. Call with `goal_id` set — verify `workspace_goal_history` source included. Check `context_quality_scores` ClickHouse row inserted.

- [X] T011 [US1] Implement `apps/control-plane/src/platform/context_engineering/repository.py` — `ContextEngineeringRepository` with: `create_profile()`, `get_profile()`, `list_profiles()`, `update_profile()`, `delete_profile()`, `create_assignment()`, `list_assignments()`, `get_assignment_by_agent_fqn()`, `get_assignment_by_role_type()`, `get_workspace_default_assignment()`, `create_assembly_record()`, `get_assembly_record()`, `list_assembly_records()`, `create_ab_test()`, `get_ab_test()`, `list_ab_tests()`, `update_ab_test_metrics()`, `create_drift_alert()`, `list_drift_alerts()`, `resolve_drift_alert()`
- [X] T012 [US1] Implement `ContextEngineeringService.assemble_context()` and `resolve_profile()` in `apps/control-plane/src/platform/context_engineering/service.py` — `assemble_context()` pipeline: (1) `resolve_profile()` (agent → role_type → workspace → built-in default), (2) `_resolve_ab_test_profile()` if active A/B test, (3) fetch sources in profile-defined order using adapter dict — catch `ContextSourceUnavailableError` per source → `partial_sources` flag, (4) apply `PrivacyFilter.filter()`, (5) `QualityScorer.score()` → pre-score, (6) budget check → if over budget apply `ContextCompactor.compact()`, (7) `QualityScorer.score()` → post-score, (8) store full bundle in MinIO (`context-assembly-records/{workspace_id}/{execution_id}/{step_id}/bundle.json`), (9) `repository.create_assembly_record()`, (10) write quality score row to ClickHouse, (11) emit `assembly.completed` Kafka event; `resolve_profile()` resolution order: agent_fqn match → role_type match → workspace default → built-in default `BudgetEnvelope()`
- [X] T013 [US1] Implement `apps/control-plane/src/platform/context_engineering/events.py` — `AssemblyCompletedPayload` + `publish_assembly_completed()`; `BudgetExceededMinimumPayload` + `publish_budget_exceeded_minimum()` using canonical `EventEnvelope` on topic `context_engineering.events`
- [X] T014 [US1] Implement `apps/control-plane/src/platform/context_engineering/dependencies.py` — `get_context_engineering_service()` async DI factory injecting all dependencies: `ContextEngineeringRepository`, `adapters` dict, `QualityScorer`, `ContextCompactor`, `PrivacyFilter`, `ObjectStorageClient`, `ClickHouseClient`, `KafkaProducer`, `PoliciesService`

**Checkpoint**: `assemble_context()` returns deterministic, provenanced bundles from multiple sources. Assembly records and quality scores persisted.

---

## Phase 4: User Story 2 — Quality Scoring and Budget Enforcement with Compaction (Priority: P1)

**Goal**: Every assembly has quality scores (pre+post compaction). Over-budget bundles are compacted to within limits. Minimum viable context (system instructions + most recent turn) always preserved.

**Independent Test**: Call `assemble_context()` with token budget 1,000 against a conversation history of 5,000 tokens. Verify `compaction_applied=true`, `token_count_post ≤ 1,000`. Verify `quality_score_pre` and `quality_score_post` both present in assembly record. Verify system_instructions present in compacted bundle. Set budget to 50 tokens — verify `budget_exceeded_minimum` flag set and `budget_exceeded_minimum` event emitted.

- [X] T015 [US2] Wire `QualityScorer` + `ContextCompactor` fully into `ContextEngineeringService.assemble_context()` in `apps/control-plane/src/platform/context_engineering/service.py` — ensure pre-compaction score computed before compaction, post-compaction score computed after; record `compaction_actions` list from compactor; write both scores and token counts to `ContextAssemblyRecord`; emit `budget_exceeded_minimum` event if minimum viable content exceeds budget

**Checkpoint**: Quality scoring and compaction work end-to-end. Assembly records contain both pre/post scores and compaction actions.

---

## Phase 5: User Story 3 — Privacy Filtering (Priority: P1)

**Goal**: Mandatory privacy filter excludes unauthorized context elements. All exclusions logged with reason and policy. Filter non-bypassable from profile configuration.

**Independent Test**: Create a context source with `data_classification=confidential`. Call `assemble_context()` with an agent not authorized for confidential data. Verify confidential elements absent from bundle. Check assembly record `privacy_exclusions` list — verify exclusion has `reason` and `policy_id`. Grant agent confidential access — verify elements now included.

- [X] T016 [US3] Wire `PrivacyFilter.filter()` into `ContextEngineeringService.assemble_context()` in `apps/control-plane/src/platform/context_engineering/service.py` — confirm it runs after source fetching and before quality scoring; `privacy_exclusions` output stored in `ContextAssemblyRecord`; verify `PrivacyFilter` cannot be bypassed by any profile flag (no opt-out parameter in the pipeline)

**Checkpoint**: All three P1 user stories complete. Core assembly pipeline fully functional with provenance, quality scoring, compaction, and privacy filtering.

---

## Phase 6: User Story 4 — Context Drift Monitoring and Alerting (Priority: P2)

**Goal**: APScheduler drift monitor detects quality degradation per agent (mean - 2σ over 7-day window) and generates drift alerts with Kafka events.

**Independent Test**: Seed `context_quality_scores` with 7 days of data at mean=0.82, stddev=0.04. Insert 50 rows with quality_score=0.55 (< 0.74 = mean - 2σ). Run `DriftMonitorTask.run()`. Verify `ContextDriftAlert` created with correct historical_mean, recent_mean, degradation_delta. Verify `context_engineering.drift.detected` event emitted on Kafka.

- [X] T017 [US4] Implement `apps/control-plane/src/platform/context_engineering/drift_monitor.py` — `DriftMonitorTask` with `async run()`: query ClickHouse `SELECT agent_fqn, avg(quality_score) as mean, stddevPop(quality_score) as std FROM context_quality_scores WHERE created_at > now()-7*86400 AND created_at <= now()-86400 GROUP BY agent_fqn` (historical window), then `SELECT agent_fqn, avg(quality_score) as recent_mean FROM context_quality_scores WHERE created_at > now()-86400 GROUP BY agent_fqn` (recent window); for each agent where `recent_mean < historical_mean - 2 * historical_std`: create `ContextDriftAlert` in PostgreSQL, emit Kafka event; analysis_window_days and significance multiplier from `PlatformSettings`
- [X] T018 [P] [US4] Add `DriftDetectedPayload` + `publish_drift_detected()` to `apps/control-plane/src/platform/context_engineering/events.py`
- [X] T019 [US4] Add `ContextEngineeringService.run_drift_analysis()`, `list_drift_alerts()`, `resolve_drift_alert()` to `apps/control-plane/src/platform/context_engineering/service.py`
- [X] T020 [US4] Add drift alert endpoints to `apps/control-plane/src/platform/context_engineering/router.py` — `GET /api/v1/context-engineering/drift-alerts` (query params: `resolved` bool, `limit`, `offset`), `POST /api/v1/context-engineering/drift-alerts/{alert_id}/resolve`

**Checkpoint**: Drift monitoring generates alerts within 5 minutes of quality degradation.

---

## Phase 7: User Story 5 — Context A/B Testing (Priority: P2)

**Goal**: Operators create A/B tests comparing two profiles. Assembly requests randomly assigned to control/variant using deterministic hash. Per-group metrics tracked.

**Independent Test**: Create A/B test with control and variant profiles for agent "test-ns:test-agent". Trigger 100 assemblies. Verify ~50/50 split (within 5%). Check assembly records have `ab_test_group` set. End test — verify status=completed, per-group quality means present.

- [X] T021 [US5] Implement `ContextEngineeringService._resolve_ab_test_profile()` and A/B test CRUD methods in `apps/control-plane/src/platform/context_engineering/service.py` — `_resolve_ab_test_profile(agent_fqn, workspace_id) → (profile, ab_group | None)`: query active A/B test for agent/workspace, compute group via `int(sha256(f"{test_id}:{execution_id}").hexdigest()[-8:], 16) % 2` (0=control, 1=variant), return appropriate profile; implement `create_ab_test()`, `get_ab_test()`, `end_ab_test()`, `get_ab_test_results()` updating `control/variant_assembly_count` and `control/variant_quality_mean` incrementally
- [X] T022 [US5] Add A/B test endpoints to `apps/control-plane/src/platform/context_engineering/router.py` — `POST /api/v1/context-engineering/ab-tests`, `GET /api/v1/context-engineering/ab-tests`, `GET /api/v1/context-engineering/ab-tests/{test_id}`, `POST /api/v1/context-engineering/ab-tests/{test_id}/end`

**Checkpoint**: A/B test group assignment functional with ~50/50 split and per-group metric tracking.

---

## Phase 8: User Story 6 — Context Engineering Profile Management (Priority: P3)

**Goal**: Operators CRUD profiles with source config, budget, and compaction preferences. Profiles assignable at agent/role-type/workspace level. Agent-specific takes precedence over workspace default.

**Independent Test**: Create profile with 4 sources, budget 4,096 tokens, strategies=[relevance_truncation]. Assign to agent "test-ns:agent". Trigger assembly — verify profile applied (correct sources, budget). Create workspace-level default. Create agent without explicit assignment — verify workspace default used. Update profile — verify next assembly uses updated config immediately.

- [X] T023 [US6] Implement profile management methods in `apps/control-plane/src/platform/context_engineering/service.py` — `create_profile()`, `get_profile()`, `list_profiles()`, `update_profile()` (takes effect immediately — no caching), `delete_profile()` (fail with 409 if has active assignments), `assign_profile()` (create `ContextProfileAssignment`), `resolve_profile()` (resolution: agent_fqn match → role_type match → workspace default → built-in `BudgetEnvelope()` defaults)
- [X] T024 [US6] Add profile management endpoints to `apps/control-plane/src/platform/context_engineering/router.py` — `POST /api/v1/context-engineering/profiles`, `GET /api/v1/context-engineering/profiles`, `GET /api/v1/context-engineering/profiles/{profile_id}`, `PUT /api/v1/context-engineering/profiles/{profile_id}`, `DELETE /api/v1/context-engineering/profiles/{profile_id}`, `POST /api/v1/context-engineering/profiles/{profile_id}/assign`
- [X] T025 [US6] Add assembly record query endpoints to `apps/control-plane/src/platform/context_engineering/router.py` — `GET /api/v1/context-engineering/assembly-records` (query params: `agent_fqn`, `limit`, `offset`), `GET /api/v1/context-engineering/assembly-records/{record_id}`

**Checkpoint**: All 6 user stories complete. Full context engineering service functional end-to-end.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Integration wiring, background task registration, tests, and quality gates.

- [X] T026 Mount context engineering router in `apps/control-plane/src/platform/api/__init__.py` — include `context_engineering.router` with prefix `/api/v1/context-engineering`
- [X] T027 [P] Register `DriftMonitorTask` in `apps/control-plane/entrypoints/scheduler_main.py` — use APScheduler `CronTrigger` every 5 minutes; call `context_engineering_service.run_drift_analysis()`
- [X] T028 [P] Call `context_engineering_clickhouse_setup.create_context_quality_scores_table()` in both `apps/control-plane/entrypoints/api_main.py` and `apps/control-plane/entrypoints/scheduler_main.py` lifespan startup hooks (idempotent — safe to call on every restart)
- [X] T029 [P] Write unit tests in `apps/control-plane/tests/unit/test_ce_quality_scorer.py` — test each of the 6 scoring sub-methods independently, test aggregate weighted average, test edge cases (empty elements list, single element, all same source type)
- [X] T030 [P] Write unit tests in `apps/control-plane/tests/unit/test_ce_compactor.py` — relevance truncation removes least-relevant first, priority eviction removes lowest-priority source first, semantic deduplication merges near-duplicates preserving both provenances, minimum viable context (system_instructions) always retained even when over budget, compaction actions list correct
- [X] T031 [P] Write unit tests in `apps/control-plane/tests/unit/test_ce_privacy_filter.py` — element with unauthorized data classification excluded, exclusion logged with reason + policy_id, element with authorized classification included, all-excluded source still produces valid (empty) element list, filter cannot be bypassed
- [X] T032 [P] Write unit tests in `apps/control-plane/tests/unit/test_ce_determinism.py` — same (execution_id, step_id) inputs produce identical ContextBundle output, A/B test group assignment is deterministic for same (test_id, execution_id) pair, sha256-based group assignment achieves ~50/50 distribution over 10,000 samples
- [X] T033 [P] Write unit tests in `apps/control-plane/tests/unit/test_ce_schemas.py` — `BudgetEnvelope` defaults, `SourceConfig` priority range validation, `ContextQualityScore` sub-score range validation, `ProfileCreate` compaction strategies list
- [X] T034 Write integration tests in `apps/control-plane/tests/integration/test_ce_assembly_pipeline.py` — full pipeline: profile → source fetching (all 9 adapters via mocks) → privacy filter → quality score → compaction → assembly record persistence → ClickHouse quality row → Kafka assembly.completed event; verify provenance chain on every element; verify `WorkspaceGoalHistoryAdapter` called when goal_id provided
- [X] T035 [P] Write integration tests in `apps/control-plane/tests/integration/test_ce_profile_management.py` — profile CRUD, assignment at agent/role_type/workspace levels, resolution precedence order, workspace default applies to unassigned agents, profile update takes effect on next call
- [X] T036 [P] Write integration tests in `apps/control-plane/tests/integration/test_ce_ab_testing.py` — group assignment achieves ~50/50 over 100 assemblies (within 5%), per-group metrics tracked separately, test ends cleanly, no-test path uses default profile
- [X] T037 [P] Write integration tests in `apps/control-plane/tests/integration/test_ce_drift_monitor.py` — seed ClickHouse with stable 7-day history, insert recent low-quality scores, run DriftMonitorTask, verify ContextDriftAlert created with correct deltas, verify Kafka event emitted, verify no alert when quality within bounds
- [X] T038 [P] Write integration tests in `apps/control-plane/tests/integration/test_ce_budget_enforcement.py` — over-budget assembly triggers compaction, compacted bundle within budget, minimum viable context retained, budget_exceeded_minimum flag set when minimum exceeds budget, compaction_actions list contains correct strategies applied
- [X] T039 Run ruff check and mypy --strict on `apps/control-plane/src/platform/context_engineering/` — resolve all lint and type errors; verify test coverage ≥ 95%

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002 and T003 parallelizable after T001
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories; T005–T010 all parallelizable after T004
- **US1 (Phase 3)**: Depends on Phase 2 complete — T011 (repository) → T012 (service) → T013/T014 parallelizable after T012
- **US2 (Phase 4)**: Depends on US1 complete (needs `assemble_context()` pipeline to wire quality scoring into)
- **US3 (Phase 5)**: Depends on US1 complete (needs pipeline to wire privacy filter into)
- **US4 (Phase 6)**: Depends on Phase 2 complete + ClickHouse quality score writes from US1; T017/T018 parallelizable
- **US5 (Phase 7)**: Depends on US1 complete (A/B profile resolution plugs into `assemble_context()`)
- **US6 (Phase 8)**: Depends on Phase 2 complete (models + repository exist); T023 → T024/T025 parallelizable
- **Polish (Phase 9)**: Depends on all desired stories complete; T026–T033 parallelizable; test files T034–T038 parallelizable

### User Story Dependencies

- **US1+US2+US3 (P1)**: All must complete together — they are a single pipeline (assembly → scoring → compaction → privacy → persist); US2 and US3 are wiring tasks that extend the US1 pipeline
- **US4 (P2)**: Depends on US1 (needs quality scores in ClickHouse); otherwise independent
- **US5 (P2)**: Depends on US1 (A/B resolution plugs into assemble_context); otherwise independent
- **US6 (P3)**: Depends only on Phase 2 (models + repository); profile management can be built independently

### Within Each User Story

- Models and schemas (Phase 2) before all service work
- Repository before service methods that need it
- Service before router endpoints
- Internal interface (`assemble_context`) before router or external callers

### Parallel Opportunities

- T002, T003 — migration and ClickHouse setup, different files
- T005, T006, T007, T008, T009, T010 — all foundational modules, different files
- T013, T014 — events stub and dependencies factory, after T012
- T018, T019 — event payloads and service drift methods, different responsibilities
- T021 includes A/B group logic + wiring into assemble_context — sequential after T012
- T026, T027, T028 — router mount, scheduler registration, ClickHouse startup call — all different files
- T029, T030, T031, T032, T033 — all unit test files, fully parallel
- T034, T035, T036, T037, T038 — all integration test files, fully parallel

---

## Parallel Example: Phase 2 (Foundational)

```
# Launch all in parallel after T004 completes:
Task T005: Implement schemas.py (all Pydantic types)
Task T006: Implement models.py (all SQLAlchemy models)
Task T007: Implement adapters.py (9 context source adapters)
Task T008: Implement quality_scorer.py (QualityScorer)
Task T009: Implement compactor.py (ContextCompactor)
Task T010: Implement privacy_filter.py (PrivacyFilter)

# Then sequentially:
Task T011: repository.py (depends on T006 models)
Task T012: service.assemble_context() (depends on T005, T007-T010, T011)
Tasks T013+T014: events.py + dependencies.py (parallel, both depend on T012)
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — all P1)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational)
2. Complete Phase 3 (US1 — assembly with provenance)
3. Complete Phase 4 (US2 — quality scoring + compaction)
4. Complete Phase 5 (US3 — privacy filtering)
5. **STOP and VALIDATE**: Run quickstart.md scenario 1 (deterministic assembly) and scenario 2 (budget enforcement)
6. All three P1 stories together form the deployable MVP — `assemble_context()` is fully functional

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 → `assemble_context()` works with provenanced bundles → callable by execution context
3. US2 → quality scoring + compaction → production-safe budget management
4. US3 → privacy filter → security boundary active
5. US4 → drift monitoring → quality observability
6. US5 → A/B testing → profile optimization capability
7. US6 → profile management UI → operator control

### Parallel Team Strategy

After Phase 2 completes:
- Developer A: US1+US2+US3 (P1 pipeline — must ship together)
- Developer B: US6 (profile management — independent of pipeline internals)
- Developer C: US4+US5 (monitoring + A/B testing — both depend on US1 but not on each other)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in current phase
- US1, US2, and US3 are tightly coupled pipeline stages — treat as a single increment
- `PrivacyFilter` (T010/T016) is the security boundary — ensure it cannot be bypassed by any profile flag (test this explicitly in T031)
- Determinism (SC-002) must be verified by T032 before considering US1 complete
- `WorkspaceGoalHistoryAdapter` (T007) implements the workspace super-context — ensure it is called only when `goal_id` is provided to `assemble_context()`
- Hierarchical compression in compactor (T009) is async and makes an LLM call via httpx — must be clearly opt-in (not in the default compaction_strategies list)
- The `context_engineering.events` Kafka topic must exist before integration tests run — verify via quickstart.md Kafka setup
- `_resolve_ab_test_profile()` in T021 must use `sha256(f"{test_id}:{execution_id}")` — the seed must NOT include `step_id` so the same execution always gets the same group even across multiple steps
