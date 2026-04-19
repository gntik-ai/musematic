# Tasks: Agent Adaptation Pipeline and Context Engineering Levels

**Feature**: `068-adaptation-context-levels`  
**Input**: `specs/068-adaptation-context-levels/` — plan.md, spec.md, data-model.md, contracts/rest-api.md, quickstart.md  
**Branch**: `068-adaptation-context-levels`

**Tests**: Included — spec acceptance scenarios and plan test files both specify test coverage.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Migration and config extensions — must land before any model or service code.

- [X] T001 Create Alembic migration `055_adaptation_pipeline_and_proficiency.py` in `apps/control-plane/migrations/versions/` — down_revision `054_trajectory_evaluation_schema`; adds 6 enum values to `adaptation_proposal_status`; creates enums `proficiency_level`, `outcome_classification`, `correlation_classification`, `snapshot_type`; adds 12 columns to `agentops_adaptation_proposals`; creates 4 tables (`agentops_adaptation_snapshots`, `agentops_adaptation_outcomes`, `agentops_proficiency_assessments`, `context_engineering_correlation_results`); adds 3 partial unique indexes and 4 regular indexes
- [X] T002 Extend `AgentOpsSettings` in `apps/control-plane/src/platform/common/config.py` with 6 new fields: `adaptation_proposal_ttl_hours`, `adaptation_rollback_retention_days`, `adaptation_observation_window_hours`, `adaptation_signal_poll_interval_minutes`, `adaptation_min_observations_per_dimension`, `adaptation_proficiency_dwell_time_hours`; extend `ContextEngineeringSettings` with 3 fields: `correlation_window_days`, `correlation_min_data_points`, `correlation_recompute_interval_hours`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models, schemas, repository methods, events, and exceptions that all user-story phases depend on. No user story can start until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Extend `AdaptationProposal` SQLAlchemy model in `apps/control-plane/src/platform/agentops/models.py` with 12 new nullable columns (`expected_improvement`, `pre_apply_snapshot_key`, `applied_at`, `applied_by`, `rolled_back_at`, `rolled_back_by`, `rollback_reason`, `expires_at`, `revoked_at`, `revoked_by`, `revoke_reason`, `signal_source`) and 6 new `adaptation_proposal_status` enum values (`applied`, `rolled_back`, `expired`, `orphaned`, `stale`, `revoked`)
- [X] T004 [P] Add `AdaptationSnapshot` and `AdaptationOutcome` SQLAlchemy models to `apps/control-plane/src/platform/agentops/models.py` (JSONB `configuration`, `configuration_hash`, `retention_expires_at` for snapshot; immutable `expected_delta`, `observed_delta`, `classification`, `variance_annotation` JSONB for outcome)
- [X] T005 [P] Add `ProficiencyAssessment` SQLAlchemy model to `apps/control-plane/src/platform/agentops/models.py` (append-only: `agent_fqn`, `workspace_id`, `level proficiency_level`, `dimension_values JSONB`, `observation_count`, `trigger`, `assessed_at`)
- [X] T006 [P] Add `CorrelationResult` SQLAlchemy model to `apps/control-plane/src/platform/context_engineering/models.py` (`workspace_id`, `agent_fqn`, `dimension`, `performance_metric`, `window_start`, `window_end`, `coefficient FLOAT nullable`, `classification correlation_classification`, `data_point_count`, `computed_at`)
- [X] T007 [P] Extend `AdaptationProposalResponse` Pydantic schema in `apps/control-plane/src/platform/agentops/schemas.py` with 12 new optional fields; add `AdaptationApplyRequest/Response`, `AdaptationRollbackRequest/Response`, `AdaptationRevokeRequest/Response`, `AdaptationOutcomeResponse`, `AdaptationLineageResponse`, `ProficiencyResponse`, `ProficiencyHistoryResponse`, `ProficiencyFleetResponse`
- [X] T008 [P] Add correlation Pydantic schemas to `apps/control-plane/src/platform/context_engineering/schemas.py`: `CorrelationResultResponse`, `CorrelationFleetResponse`, `CorrelationRecomputeRequest`
- [X] T009 [P] Add 9 new event types to `apps/control-plane/src/platform/agentops/events.py`: `applied`, `rolled_back`, `outcome_recorded`, `approval_revoked`, `expired`, `orphaned`, `stale`, `ingestion_degraded`, `proficiency.assessed`
- [X] T010 [P] Add 2 new event types to `apps/control-plane/src/platform/context_engineering/events.py`: `correlation.computed`, `correlation.strong_negative`
- [X] T011 [P] Add domain exceptions to `apps/control-plane/src/platform/agentops/exceptions.py`: `StaleProposalError`, `RollbackWindowExpiredError`, `OutcomeImmutableError`, `ApprovalRevokedError`
- [X] T012 Extend `AgentOpsRepository` in `apps/control-plane/src/platform/agentops/repository.py` with: `create_snapshot`, `get_snapshot_by_proposal`, `create_outcome`, `get_outcome_by_proposal`, `list_proposals_past_ttl`, `list_orphaned_proposals`, `list_proposals_pending_outcome`, `list_snapshots_past_retention`
- [X] T013 [P] Add correlation CRUD queries to `apps/control-plane/src/platform/context_engineering/repository.py`: `upsert_correlation_result`, `get_latest_by_agent`, `list_fleet_by_classification`

**Checkpoint**: All models, schemas, repository queries, events, and exceptions are in place — user story phases can begin.

---

## Phase 3: User Story 1 — Operator Receives a Proposal with Rationale and Expected Improvement (Priority: P1) 🎯 MVP

**Goal**: Pipeline analyzes performance signals, produces a structured proposal with `expected_improvement`, `signal_source`, and rationale; nothing changes on the live agent.

**Independent Test**: `POST /api/v1/agentops/billing-agent/adapt` → response contains `expected_improvement.target_delta`, `signals[0].rule_type`, `signal_source`; `GET /api/v1/registry/agents/billing-agent` shows no change. Second invocation for same agent returns identical proposal ID (S3).

### Tests for User Story 1

- [X] T014 [P] [US1] Write unit test for `_analyze_convergence_regression` rule in `apps/control-plane/tests/unit/agentops/test_adaptation_analyzer.py` — covers: loops doubled → signal returned; loops stable → None returned
- [X] T015 [P] [US1] Write unit test for `expected_improvement` computation in `apps/control-plane/tests/unit/agentops/test_adaptation_pipeline.py` — covers: `signal_source=manual`, `signal_source=automatic`, `no_opportunities` path

### Implementation for User Story 1

- [X] T016 [US1] Add `_analyze_convergence_regression` rule to `BehavioralAnalyzer` in `apps/control-plane/src/platform/agentops/adaptation/analyzer.py` — reads `self_correction_loops` from ClickHouse over configured window, compares against baseline (first-half vs. second-half of window), returns `AdaptationSignal` with `rule_type="convergence_regression"` when loops-per-execution exceed baseline by threshold
- [X] T017 [US1] Extend proposal-creation path in `apps/control-plane/src/platform/agentops/adaptation/pipeline.py` to populate `expected_improvement` JSONB (`metric`, `baseline_value`, `target_value`, `target_delta`, `observation_window_hours`) and `signal_source` (`manual`/`automatic`/`scheduled`) on every new proposal; set `expires_at = now() + adaptation_proposal_ttl_hours`
- [X] T018 [US1] Extend `AgentOpsService.propose_adaptation` in `apps/control-plane/src/platform/agentops/service.py` to persist `expected_improvement`, `signal_source`, `expires_at` on the new `AdaptationProposal` row
- [X] T019 [US1] Update existing `POST /api/v1/agentops/{agent_fqn}/adapt` handler in `apps/control-plane/src/platform/agentops/router.py` to return extended `AdaptationProposalResponse` (new optional fields appear for new proposals; nil for historical)
- [X] T020 [US1] Add `GET /api/v1/agentops/adaptations/{proposal_id}/lineage` route + `AgentOpsService.get_adaptation_lineage` method in `apps/control-plane/src/platform/agentops/router.py` + `service.py` — assembles `AdaptationLineageResponse` from proposal, snapshot, outcome, and rollback fields

**Checkpoint**: `POST /adapt` returns proposals with `expected_improvement` and `signal_source`; lineage endpoint works; no existing tests broken.

---

## Phase 4: User Story 2 — Reviewer Approves or Rejects Before Anything Applies (Priority: P1)

**Goal**: Approval sets `status=approved` only (D-011 — decouple from auto-apply); new revoke-approval endpoint; TTL and orphan scanners automatically expire/orphan stale proposals.

**Independent Test**: `POST /review {approved}` → `status=approved`, agent unchanged. `POST /apply` on `proposed` proposal → 409. `POST /revoke-approval` → `status=proposed`, apply blocked. Wait for TTL → `status=expired`, review blocked (S7, S8, S9).

### Tests for User Story 2

- [X] T021 [P] [US2] Write unit tests for approval/revoke/TTL/orphan state transitions in `apps/control-plane/tests/unit/agentops/test_adaptation_pipeline.py` — covers: approve sets approved; revoke returns to proposed; apply on non-approved → 409; apply on expired → 409
- [X] T022 [P] [US2] Write unit tests for TTL scanner and orphan scanner in `apps/control-plane/tests/unit/agentops/test_adaptation_scanners.py` — covers: proposals past TTL → `expired`; agent archived → `orphaned`; events emitted

### Implementation for User Story 2

- [X] T023 [US2] **[D-011 — load-bearing]** Modify approval path in `apps/control-plane/src/platform/agentops/adaptation/pipeline.py` to set `status=approved` only — remove any automatic apply/ATE-test trigger that previously fired on approval; preserve existing `testing/passed/promoted` code paths for historical proposals untouched
- [X] T024 [US2] Add `POST /api/v1/agentops/adaptations/{proposal_id}/revoke-approval` route in `apps/control-plane/src/platform/agentops/router.py` + `AgentOpsService.revoke_adaptation_approval` in `service.py` — validates `status=approved`, transitions to `status=proposed`, sets `revoked_at/by/reason`, publishes `approval_revoked` event
- [X] T025 [US2] Add `ttl_scanner_task` to `AgentOpsService` in `apps/control-plane/src/platform/agentops/service.py` — queries `list_proposals_past_ttl`, transitions each to `status=expired`, publishes `agentops.adaptation.expired` event per proposal
- [X] T026 [US2] Add `orphan_scanner_task` to `AgentOpsService` in `apps/control-plane/src/platform/agentops/service.py` — queries open proposals, checks each agent's registry status via `registry_service`, transitions proposals for archived/deleted agents to `status=orphaned`, publishes `agentops.adaptation.orphaned` event

**Checkpoint**: Approval gate is enforced end-to-end; revoke, TTL, and orphan transitions work; `status=approved` no longer triggers auto-apply.

---

## Phase 5: User Story 3 — Applied Adaptation Is Audited and Post-Apply Outcome Is Measured (Priority: P1)

**Goal**: Explicit apply step with pre-apply snapshot, byte-identical rollback, post-apply outcome measurement, stale-detection at apply time, and auto-recovery on partial-apply failure.

**Independent Test**: Approve and apply a proposal → `status=applied`, snapshot row exists, `pre_apply_configuration_hash` in response. After observation window, `GET /outcome` returns `classification`. Rollback → `byte_identical_to_pre_apply=true`. Attempt rollback past retention → 410 (S5, S10, S12, S13).

### Tests for User Story 3

- [X] T027 [P] [US3] Write unit tests for `AdaptationApplyService` in `apps/control-plane/tests/unit/agentops/test_adaptation_apply_service.py` — covers: pre-apply snapshot creation; stale-field detection → `StaleProposalError`; apply mutates agent; partial-apply auto-recovery; `applied` event emitted
- [X] T028 [P] [US3] Write unit tests for `AdaptationRollbackService` in `apps/control-plane/tests/unit/agentops/test_adaptation_rollback_service.py` — covers: byte-identical hash verification; `RollbackWindowExpiredError` past retention; `rolled_back` event emitted
- [X] T029 [P] [US3] Write unit tests for `AdaptationOutcomeService` in `apps/control-plane/tests/unit/agentops/test_adaptation_outcome_service.py` — covers: improved/no_change/regressed/inconclusive classification; `OutcomeImmutableError` on duplicate persist; variance annotation when stddev > expected_delta
- [X] T030 [US3] Write integration test for full `proposed→approved→applied→outcome→rolled_back` lifecycle in `apps/control-plane/tests/integration/agentops/test_adaptation_lifecycle_integration.py`

### Implementation for User Story 3

- [X] T031 [US3] Create `AdaptationApplyService` in `apps/control-plane/src/platform/agentops/adaptation/apply_service.py` implementing: (1) validate `status=approved`; (2) load current agent config; (3) check target fields still exist → `StaleProposalError` → `status=stale`; (4) create pre-apply snapshot (JSONB + SHA-256 hash, `retention_expires_at = now() + rollback_retention_days`); (5) call `registry_service.update_agent_profile()` / `activate_revision()`; (6) capture post-apply hash; (7) transition `status=applied`; (8) publish `agentops.adaptation.applied` event; (9) on partial-apply failure: detect partial state, auto-rollback, record `recovery_path`
- [X] T032 [US3] Create `AdaptationRollbackService` in `apps/control-plane/src/platform/agentops/adaptation/rollback_service.py` implementing: (1) validate `status=applied`; (2) load pre-apply snapshot → check `retention_expires_at` → raise `RollbackWindowExpiredError` if expired; (3) restore profile fields + active revision via `registry_service`; (4) verify post-rollback hash matches pre-apply hash → raise `RollbackIntegrityError` if mismatch; (5) transition `status=rolled_back`; (6) publish `agentops.adaptation.rolled_back` event
- [X] T033 [US3] Create `AdaptationOutcomeService` in `apps/control-plane/src/platform/agentops/adaptation/outcome_service.py` implementing: query ClickHouse for performance metric over observation window; compute `observed_delta` and `observed_stddev`; classify (`improved`/`no_change`/`regressed`/`inconclusive`); add `variance_annotation` when stddev > expected_delta magnitude; persist `AdaptationOutcome` (immutable — `OutcomeImmutableError` if duplicate); publish `agentops.adaptation.outcome_recorded` event
- [X] T034 [US3] Add apply/rollback/outcome/lineage routes to `apps/control-plane/src/platform/agentops/router.py`: `POST /adaptations/{id}/apply` (200), `POST /adaptations/{id}/rollback` (200), `GET /adaptations/{id}/outcome` (200 / 425 Too Early)
- [X] T035 [US3] Extend `AgentOpsService` in `apps/control-plane/src/platform/agentops/service.py` with `apply_adaptation`, `rollback_adaptation`, `get_adaptation_outcome` methods delegating to the three new service classes; add `outcome_measurer_task` (scans `applied` proposals past observation window) and `snapshot_retention_gc_task` (deletes snapshots past `retention_expires_at`)

**Checkpoint**: Full apply→outcome→rollback lifecycle works end-to-end; byte-identical rollback passes hash verification; partial-apply auto-recovery confirmed.

---

## Phase 6: User Story 4 — Operator Sees Per-Agent Context Engineering Proficiency Level (Priority: P2)

**Goal**: Daily scheduler computes weighted-average proficiency level per agent; dwell-time gate prevents flapping; `undetermined` for agents below minimum observations; fleet query available.

**Independent Test**: `GET /api/v1/agentops/billing-agent/proficiency` returns `level=competent` with `dimension_values`; new agent returns `level=undetermined` + `missing_dimensions` list; `GET /proficiency?level_at_or_below=competent` returns both agents (S14, S15, S17, S18).

### Tests for User Story 4

- [X] T036 [P] [US4] Write unit tests for `ProficiencyService` in `apps/control-plane/tests/unit/agentops/test_proficiency_service.py` — covers: weighted-average derivation; `undetermined` when < min observations; dwell-time gate blocks flapping append; levels ordered consistently
- [X] T037 [US4] Write integration test for cross-agent proficiency queries in `apps/control-plane/tests/integration/agentops/test_proficiency_integration.py`

### Implementation for User Story 4

- [X] T038 [US4] Create `apps/control-plane/src/platform/agentops/proficiency/__init__.py` (empty package marker)
- [X] T039 [US4] Create `ProficiencyService` in `apps/control-plane/src/platform/agentops/proficiency/service.py` implementing: `compute_for_agent` (query `context_assembly_records` per-dimension, apply weighted average `RA×0.4 + IA×0.3 + CC×0.3`, apply dwell-time gate before appending row, map score to `proficiency_level`, return `undetermined` if any dimension < `min_observations_per_dimension`); `get_current`, `list_history`, `query_fleet`
- [X] T040 [US4] Create `ProficiencyRecomputerTask` in `apps/control-plane/src/platform/agentops/proficiency/scheduler.py` — daily scheduler that iterates all active agents per workspace and calls `ProficiencyService.compute_for_agent`; emits `agentops.proficiency.assessed` event with `previous_level`
- [X] T041 [US4] Add proficiency routes to `apps/control-plane/src/platform/agentops/router.py`: `GET /{agent_fqn}/proficiency` (200 / `undetermined` shape / 404), `GET /{agent_fqn}/proficiency/history` (cursor-paginated), `GET /proficiency` (fleet query with `level_at_or_below` filter)
- [X] T042 [US4] Extend `AgentOpsService` in `apps/control-plane/src/platform/agentops/service.py` with `get_proficiency`, `list_proficiency_history`, `query_proficiency_fleet` methods; add `proficiency_recomputer_task` entry-point delegating to `ProficiencyRecomputerTask`

**Checkpoint**: Proficiency computed, stored, and queryable; dwell-time prevents flapping; `undetermined` vs. `novice` distinction enforced.

---

## Phase 7: User Story 5 — Quality Engineer Sees Context-Performance Correlation (Priority: P2)

**Goal**: Daily scheduler computes Pearson correlation coefficients between context-quality dimensions and performance metrics per agent; `strong_negative` flagged; fleet-wide triage endpoint available.

**Independent Test**: Populate synthetic paired signals; `GET /api/v1/context-engineering/correlations/billing-agent?window_days=30` returns `coefficient=0.72, classification=strong_positive` for retrieval_accuracy and `classification=inconclusive` for an agent with < 30 data points (S19, S20).

### Tests for User Story 5

- [X] T043 [P] [US5] Write unit tests for `CorrelationService` in `apps/control-plane/tests/unit/context_engineering/test_correlation_service.py` — covers: Pearson computation matches known values; `inconclusive` below min data points; `strong_negative` event emitted; per-window unique constraint enforced
- [X] T044 [US5] Write integration test for end-to-end correlation compute + strong-negative event in `apps/control-plane/tests/integration/context_engineering/test_correlation_integration.py`

### Implementation for User Story 5

- [X] T045 [US5] Create `CorrelationService` in `apps/control-plane/src/platform/context_engineering/correlation_service.py` implementing: for each `(dimension, performance_metric)` pair — fetch paired observations from `context_assembly_records` × ClickHouse `analytics_usage_events` joined on `execution_id`; compute Pearson coefficient via `scipy.stats.pearsonr`; classify (`strong_positive ≥0.7`, `moderate_positive ≥0.4`, `weak ±0.4`, `moderate_negative ≤-0.4`, `strong_negative ≤-0.7`, `inconclusive` if `data_point_count < min_data_points`); upsert `CorrelationResult`; publish `correlation.computed` event; publish `correlation.strong_negative` event if applicable
- [X] T046 [US5] Create `CorrelationRecomputerTask` in `apps/control-plane/src/platform/context_engineering/correlation_scheduler.py` — daily scheduler per workspace/agent; delegates to `CorrelationService.compute_for_agent`; accepts `enqueue_recompute` for manual trigger
- [X] T047 [US5] Extend `ContextEngineeringService` in `apps/control-plane/src/platform/context_engineering/service.py` with `get_latest_correlation`, `query_fleet_correlations`, `enqueue_correlation_recompute` methods
- [X] T048 [US5] Add correlation routes to `apps/control-plane/src/platform/context_engineering/router.py`: `GET /correlations/{agent_fqn}` (200 / 404), `GET /correlations` (fleet query with `classification` filter), `POST /correlations/recompute` (202 Accepted)
- [X] T049 [US5] Update `apps/control-plane/src/platform/context_engineering/dependencies.py` to wire `CorrelationService` + `CorrelationRecomputerTask`

**Checkpoint**: Correlation computed via Pearson; `strong_negative` events emitted; fleet triage endpoint lists flagged agents.

---

## Phase 8: User Story 6 — Convergence Signal Ingestion Feeds Pipeline Automatically (Priority: P3)

**Goal**: Signal-poll scheduler automatically creates proposals when `convergence_regression` rule fires; ingestion-degraded event emitted after 5 consecutive failures; manual invocations still work during degradation.

**Independent Test**: Set `self_correction_loops` to 2× baseline; wait for `signal_poll_interval`; verify a proposal with `signal_source=automatic` and `signals[0].rule_type=convergence_regression` enters the review queue; verify no auto-apply (S21, S22).

### Tests for User Story 6

- [X] T050 [US6] Write unit tests for automatic signal polling and ingestion health in `apps/control-plane/tests/unit/agentops/test_adaptation_pipeline.py` — covers: convergence regression → proposal created with `signal_source=automatic`; 5 consecutive failures → `ingestion_degraded` event; recovery on next success → no degraded event

### Implementation for User Story 6

- [X] T051 [US6] Add `signal_poll_task` to `AgentOpsService` in `apps/control-plane/src/platform/agentops/service.py` — runs on `adaptation_signal_poll_interval_minutes` schedule; iterates active agents per workspace; calls `BehavioralAnalyzer` (including new `_analyze_convergence_regression` from T016); creates proposal with `signal_source=automatic` when any rule fires; idempotent (skips agents with existing open proposal)
- [X] T052 [US6] Add ingestion health tracking to `BehavioralAnalyzer` in `apps/control-plane/src/platform/agentops/adaptation/analyzer.py` — maintain consecutive-failure counter; emit `agentops.adaptation.ingestion_degraded` event after 5 failures; reset counter on success; expose `is_degraded` property for health endpoint

**Checkpoint**: Convergence regression → proposal auto-created → same approval gate as manual proposals; no auto-apply; degraded state observable.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Wire schedulers into lifespan, update dependency injection, backward-compat validation.

- [X] T053 Register all 6 new schedulers in `apps/control-plane/src/platform/main.py` lifespan: `adaptation_ttl_scanner`, `adaptation_orphan_scanner`, `adaptation_outcome_measurer`, `adaptation_signal_poll`, `proficiency_recomputer`, `correlation_recomputer`, `snapshot_retention_gc` — follow existing lifespan scheduler pattern
- [X] T054 Update `apps/control-plane/src/platform/agentops/dependencies.py` to wire `AdaptationApplyService`, `AdaptationRollbackService`, `AdaptationOutcomeService`, `ProficiencyService`, `ProficiencyRecomputerTask` via FastAPI dependency injection
- [X] T055 [P] Update `apps/control-plane/src/platform/agentops/trust_support.py` (or equivalent test support file) to expose `AgentOpsTestSupport` helpers for snapshot fixtures, outcome fixtures, and proficiency seed rows in `apps/control-plane/tests/trust_support.py`
- [X] T056 Run backward-compat validation per quickstart S24/S25: load a pre-feature proposal with `status=promoted`, confirm all pre-existing fields are intact and new fields are `null`; call all pre-existing endpoints and confirm response shapes are byte-identical except for added optional fields

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (config values must exist before models reference them)
- **Phases 3–8 (User Stories)**: All depend on Phase 2 completion
  - US1 (Phase 3) and US2 (Phase 4) are tightly coupled — implement US1 first, then US2 (approval gate decoupling in T023 depends on US1 proposal creation being stable)
  - US3 (Phase 5) depends on US2 completion (apply gate requires approved status from US2)
  - US4 (Phase 6) and US5 (Phase 7) are independent of each other; both depend only on Phase 2
  - US6 (Phase 8) depends on US1 (convergence rule added in T016 must exist before signal_poll_task in T051)
- **Phase 9 (Polish)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2 — independent
- **US2 (P1)**: Starts after US1 (T023 modifies approval path added in US1)
- **US3 (P1)**: Starts after US2 (apply validates `status=approved` set by US2)
- **US4 (P2)**: Starts after Phase 2 — independent of US1–US3
- **US5 (P2)**: Starts after Phase 2 — independent of US1–US4
- **US6 (P3)**: Starts after US1 (reuses `_analyze_convergence_regression` from T016)

### Within Each User Story

- Tests before implementation (TDD)
- Models → repository → service → router
- Core implementation before integration tests

### Parallel Opportunities

- T004, T005, T006 can run in parallel (different new models)
- T007, T008, T009, T010, T011 can run in parallel (different schema/event/exception files)
- US4 (Phase 6) and US5 (Phase 7) can be developed in parallel by different contributors after Phase 2
- Test tasks within each phase marked [P] can run in parallel

---

## Parallel Example: Phase 2

```bash
# Run simultaneously after T003:
Task T004: "Add AdaptationSnapshot + AdaptationOutcome models to agentops/models.py"
Task T005: "Add ProficiencyAssessment model to agentops/models.py"
Task T006: "Add CorrelationResult model to context_engineering/models.py"
Task T007: "Add new schemas to agentops/schemas.py"
Task T008: "Add correlation schemas to context_engineering/schemas.py"
Task T009: "Add 9 new events to agentops/events.py"
Task T010: "Add 2 new events to context_engineering/events.py"
Task T011: "Add 4 new exceptions to agentops/exceptions.py"
Task T013: "Add correlation CRUD to context_engineering/repository.py"
# T012 (repository) runs after T003-T006 to ensure model imports exist
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — the P1 stories)

1. Complete Phase 1 + Phase 2
2. Complete Phase 3 (US1 — proposal with rationale)
3. Complete Phase 4 (US2 — approval gate + revoke)
4. Complete Phase 5 (US3 — apply + outcome + rollback)
5. **STOP and VALIDATE**: Run integration test `test_adaptation_lifecycle_integration.py`; confirm S1–S13 in quickstart.md pass
6. Phase 9 partial: register TTL/orphan/outcome schedulers only

### Incremental Delivery

1. Setup + Foundational → migration + models landed
2. US1 + US2 + US3 → full adaptation lifecycle (MVP)
3. US4 → proficiency levels (fleet observability)
4. US5 → correlation (investment thesis validation)
5. US6 → automatic ingestion (operational maturity)
6. Polish → all schedulers wired, backward-compat confirmed

---

## Notes

- **[D-011 — load-bearing]**: T023 is the riskiest single task — decoupling approval from auto-apply changes existing behavior. Run all existing `agentops/` tests after T023 before proceeding.
- **Byte-identical rollback** (T032): Hash comparison is mandatory — `RollbackIntegrityError` must fire if hashes diverge; do not silently succeed.
- **Historical proposals** (`status=promoted/testing/passed/failed`): Must load via `GET /adaptation-history` unchanged after migration 055. Verify in T056.
- **`expires_at` index**: Migration 055 creates a partial index filtered on `status='proposed'` — ensure the TTL scanner query uses this index (check EXPLAIN ANALYZE in integration test).
- [P] tasks = different files, no dependencies on each other
- [USn] label maps each task to its user story for traceability
