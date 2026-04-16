---
description: "Task list for Simulation and Digital Twins"
---

# Tasks: Simulation and Digital Twins

**Input**: Design documents from `specs/040-simulation-digital-twins/`
**Branch**: `040-simulation-digital-twins`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/ ✅, research.md ✅, quickstart.md ✅

**Tests**: Included — SC-007 requires ≥95% line coverage for all simulation modules.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: User story this task belongs to (US1–US5)
- File paths are absolute from repo root

---

## Phase 1: Setup

**Purpose**: Create the `simulation/` bounded context skeleton and register the runtime profile.

- [X] T001 Create `simulation/` package skeleton — all `__init__.py` files for `apps/control-plane/src/platform/simulation/`, `coordination/`, `twins/`, `isolation/`, `prediction/`, `comparison/`
- [X] T002 [P] Add `simulation` runtime profile entrypoint in `apps/control-plane/src/platform/main.py` — mount `/api/v1/simulations` router, start Kafka consumer for `simulation.events`, register APScheduler `prediction_worker` background task
- [X] T003 [P] Add simulation PlatformSettings fields (`SIMULATION_MAX_DURATION_SECONDS`, `SIMULATION_BEHAVIORAL_HISTORY_DAYS`, `SIMULATION_MIN_PREDICTION_HISTORY_DAYS`, `SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA`, `SIMULATION_DEFAULT_STRICT_ISOLATION`) in `apps/control-plane/src/platform/common/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All shared data models, schemas, repository, exceptions, events, and DI must be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create `apps/control-plane/src/platform/simulation/exceptions.py` — `SimulationError` base (500), `SimulationNotCancellableError` (409), `SimulationInfrastructureUnavailableError` (409), `IncompatibleComparisonError` (422), `InsufficientPredictionDataError` (200 with `status='insufficient_data'` field)
- [X] T005 Create `apps/control-plane/src/platform/simulation/models.py` — all 5 SQLAlchemy models with correct mixin order (`Base`, `UUIDMixin`, `TimestampMixin`, `WorkspaceScopedMixin`): `SimulationRun`, `DigitalTwin`, `BehavioralPrediction`, `SimulationIsolationPolicy`, `SimulationComparisonReport`; all JSONB columns, indexes, CheckConstraints per data-model.md
- [X] T006 [P] Create `apps/control-plane/src/platform/simulation/schemas.py` — Pydantic v2 schemas: `SimulationRunCreateRequest`, `SimulationRunResponse`, `DigitalTwinResponse`, `SimulationIsolationPolicyCreateRequest`, `SimulationIsolationPolicyResponse`, `BehavioralPredictionResponse`, `SimulationComparisonReportResponse`; all validators per contracts/api-endpoints.md
- [X] T007 Create `apps/control-plane/src/platform/simulation/repository.py` — async CRUD for all 5 tables; Redis methods: `set_status_cache(run_id, status_dict)`, `get_status_cache(run_id)` (key: `sim:status:{run_id}`, TTL 24h); cursor pagination
- [X] T008 Create `apps/control-plane/migrations/versions/040_simulation_digital_twins.py` — Alembic migration creating all 5 tables in dependency order: `simulation_isolation_policies` → `simulation_runs` → `simulation_digital_twins` → `simulation_behavioral_predictions` → `simulation_comparison_reports`; all indexes and constraints
- [X] T009 [P] Create `apps/control-plane/src/platform/simulation/events.py` — Kafka publisher for `simulation.events` topic; async publish methods for all control-plane event types: `simulation_run_created`, `simulation_run_cancelled`, `twin_created`, `twin_modified`, `prediction_completed`, `comparison_completed`, `isolation_breach_detected`; key: `simulation_id`
- [X] T010 [P] Create `apps/control-plane/src/platform/simulation/dependencies.py` — FastAPI DI: `get_simulation_service` using `Depends`; inject `AsyncSession`, `AsyncRedis`, `SimulationRepository`, `RegistryServiceInterface`, `PolicyServiceInterface`, `SimulationControllerClient`
- [X] T011 Create `apps/control-plane/src/platform/simulation/service.py` — `SimulationServiceInterface` protocol + `SimulationService` skeleton with constructor accepting repository, redis, kafka, registry_service, policy_service, simulation_controller_client; stub methods to be filled per user story phase

**Checkpoint**: Foundation ready — all 5 tables migrated, schemas defined, repository wired; user story implementation can now proceed.

---

## Phase 3: User Story 1 — Create and Run Simulations (Priority: P1) 🎯 MVP

**Goal**: Simulation runs created, coordinated via gRPC to SimulationControlService, cancelled by operator, and status updated via Kafka consumer.

**Independent Test**: POST /api/v1/simulations → run created with status "provisioning". Confirm gRPC call dispatched to SimulationControlService. Confirm Kafka consumer updates status to "running" then "completed". POST /simulations/{id}/cancel → status becomes "cancelled".

### Tests for US1

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T012 [P] [US1] Write unit tests for `SimulationRunner` in `apps/control-plane/tests/unit/simulation/test_simulation_runner.py` — mock `SimulationControllerClient`; test `create`: gRPC called with correct twin_configs + scenario_config; `SimulationRun(status='provisioning')` created; Redis cache set; `simulation_run_created` event published; test `cancel`: gRPC cancel called; `simulation_run_cancelled` event published; test infrastructure unavailable → `SimulationInfrastructureUnavailableError` raised

### Implementation for US1

- [X] T013 [P] [US1] Implement `SimulationRunner` in `apps/control-plane/src/platform/simulation/coordination/runner.py` — `create(workspace_id, twin_configs, scenario_config, max_duration_seconds)`: call `SimulationControllerClient.create_simulation`; insert `SimulationRun(status='provisioning', controller_run_id=response.controller_run_id)`; set Redis status cache; publish `simulation_run_created` event; `cancel(run_id, workspace_id)`: fetch run; check status in (`provisioning`, `running`) → raise `SimulationNotCancellableError` otherwise; call `SimulationControllerClient.cancel_simulation`; update status to `cancelled`; publish `simulation_run_cancelled` event
- [X] T014 [US1] Add Kafka consumer in `apps/control-plane/src/platform/simulation/events.py` — consume `simulation.events` topic; handle `simulation_run_started` → update `SimulationRun.status` to `running` + update Redis cache; handle `simulation_run_completed` → update status to `completed` + store `results` JSONB; handle `simulation_run_failed` → status to `failed`; handle `simulation_run_timeout` → status to `timeout`
- [X] T015 [US1] Add `create_simulation_run`, `cancel_simulation_run`, `get_simulation_run`, `list_simulation_runs` to `apps/control-plane/src/platform/simulation/service.py`
- [X] T016 [US1] Add simulation run endpoints to `apps/control-plane/src/platform/simulation/router.py` — `POST /` (201), `GET /{run_id}`, `GET /` (cursor-paginated with `status` filter), `POST /{run_id}/cancel`
- [X] T017 [P] [US1] Write integration tests for simulation endpoints in `apps/control-plane/tests/integration/simulation/test_simulation_endpoints.py` — SQLite + in-memory Redis + mocked SimulationControllerClient; test create → get → cancel flow; test list with status filter

**Checkpoint**: US1 independently testable — simulation creation, status tracking, and cancellation all functional.

---

## Phase 4: User Story 2 — Create and Manage Digital Twins (Priority: P1)

**Goal**: Digital twins created as versioned agent config snapshots with ClickHouse behavioral history summary; modifications create new versions preserving originals.

**Independent Test**: POST /simulations/twins with agent_fqn → twin created with config_snapshot from registry + behavioral_history_summary from ClickHouse. PATCH /twins/{id} with modification → new version created, parent_twin_id set, original preserved. GET /twins/{id}/versions → all versions listed.

### Tests for US2

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T018 [P] [US2] Write unit tests for `TwinSnapshotService` in `apps/control-plane/tests/unit/simulation/test_twin_snapshot.py` — mock `RegistryServiceInterface.get_agent_profile` + `get_agent_revision`; mock ClickHouse query returning 30-day metric rows; test `create_twin`: config_snapshot populated correctly; behavioral_history_summary averages computed; `twin_created` event published; test `modify_twin`: new version created with incremented version, `parent_twin_id` set, `is_active=False` on old version; test agent not found → 404

### Implementation for US2

- [X] T019 [P] [US2] Implement `TwinSnapshotService` in `apps/control-plane/src/platform/simulation/twins/snapshot.py` — `create_twin(agent_fqn, workspace_id, revision_id)`: call `RegistryServiceInterface.get_agent_profile`; call `get_agent_revision(revision_id)` for full config (model, tools, policies, context_profile, connectors); query ClickHouse `execution_metrics_daily` for 30-day history; compute `behavioral_history_summary` (averages + numpy diff for trend: +/- > 5% → "improving/degrading", else "stable"); insert `DigitalTwin(version=1)`; publish `twin_created` event; `modify_twin(twin_id, modifications)`: fetch current twin; build new config_snapshot with modifications applied; set old twin `is_active=False`; insert new `DigitalTwin(version=current+1, parent_twin_id=current.id)` with `modifications` log; publish `twin_modified` event
- [X] T020 [US2] Add `create_digital_twin`, `modify_digital_twin`, `get_digital_twin`, `list_digital_twins`, `list_twin_versions` to `apps/control-plane/src/platform/simulation/service.py`
- [X] T021 [US2] Add twin endpoints to `apps/control-plane/src/platform/simulation/router.py` — `POST /twins` (201), `GET /twins/{twin_id}`, `GET /twins` (cursor-paginated with `agent_fqn` filter), `PATCH /twins/{twin_id}` (201 new version), `GET /twins/{twin_id}/versions`
- [X] T022 [P] [US2] Write integration tests for twin endpoints in `apps/control-plane/tests/integration/simulation/test_twin_endpoints.py` — mock RegistryServiceInterface + ClickHouse fallback (SQLite aggregate query); test create → get → modify (version increment) → list versions

**Checkpoint**: US1 + US2 independently testable — simulation runs and digital twins both functional.

---

## Phase 5: User Story 3 — Enforce Simulation Isolation (Priority: P2)

**Goal**: Isolation policies created; applied to simulation runs via PolicyServiceInterface bundle registration; forbidden actions blocked/stubbed; critical breaches halt simulation; policy deregistered on run completion.

**Independent Test**: Create isolation policy blocking "connector.send_message" (critical) and stubbing "connector.read_data". Create simulation run with this policy. Confirm PolicyServiceInterface bundle registered. Confirm `isolation_breach_detected` event published on violation. Confirm simulation cancelled on critical breach.

### Tests for US3

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T023 [P] [US3] Write unit tests for `IsolationEnforcer` in `apps/control-plane/tests/unit/simulation/test_isolation_enforcer.py` — mock `PolicyServiceInterface.register_simulation_policy_bundle` + `deregister_simulation_policy_bundle` + `SimulationRunner.cancel`; test `apply`: bundle registered with correct translated rules; test `release`: bundle deregistered by fingerprint; test `handle_breach` with critical severity + `halt_on_critical_breach=True` → `SimulationRunner.cancel` called + `isolation_breach_detected` event published; test `handle_breach` with warning severity → logged but simulation not cancelled; test default strict policy applied when no policy configured

### Implementation for US3

- [X] T024 [P] [US3] Implement `IsolationEnforcer` in `apps/control-plane/src/platform/simulation/isolation/enforcer.py` — `apply(simulation_run, policy)`: translate `blocked_actions` + `stubbed_actions` + `permitted_read_sources` into policy enforcement rule dicts; call `PolicyServiceInterface.register_simulation_policy_bundle(run_id, rules, workspace_id)`; store returned `bundle_fingerprint` on `SimulationRun`; `release(simulation_run)`: call `PolicyServiceInterface.deregister_simulation_policy_bundle(bundle_fingerprint)`; `handle_breach(simulation_run, breach_event)`: if `severity='critical'` and `halt_on_critical_breach=True` → call `SimulationRunner.cancel`; always publish `isolation_breach_detected` event; increment `results.isolation_events_count`; `apply_default_strict(simulation_run)`: if `SIMULATION_DEFAULT_STRICT_ISOLATION=True` and `isolation_policy_id is None` → generate strict policy (block all external writes, stub all connector calls)
- [X] T025 [US3] Add `create_isolation_policy`, `get_isolation_policy`, `list_isolation_policies` to `apps/control-plane/src/platform/simulation/service.py`; integrate `IsolationEnforcer.apply` into `create_simulation_run` flow (apply policy after provisioning); integrate `IsolationEnforcer.release` into Kafka status consumer (release on completed/failed/cancelled/timeout)
- [X] T026 [US3] Add isolation policy endpoints to `apps/control-plane/src/platform/simulation/router.py` — `POST /isolation-policies` (201), `GET /isolation-policies/{policy_id}`, `GET /isolation-policies` (workspace-scoped list)
- [X] T027 [P] [US3] Write integration tests for isolation policy endpoints in `apps/control-plane/tests/integration/simulation/test_isolation_policy_endpoints.py` — mock PolicyServiceInterface; test create policy → assign to run → confirm bundle registered; test critical breach → run cancelled

**Checkpoint**: US3 independently testable — isolation policies enforceable and simulation halting on critical breaches.

---

## Phase 6: User Story 4 — Predict Agent Behavior (Priority: P2)

**Goal**: Behavioral predictions generated asynchronously from ClickHouse 30-day time-series via scipy linear regression; confidence intervals and trend indicators computed; load-factor condition modifier applied.

**Independent Test**: Create twin for agent with 30+ days of history. POST /twins/{id}/predict with `load_factor=2.0`. Confirm prediction enters "pending" status. Confirm prediction_worker processes it asynchronously. GET /predictions/{id} → predicted_metrics populated with confidence intervals and trend indicators. Confirm "insufficient_data" returned for agent with < 7 days.

### Tests for US4

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T028 [P] [US4] Write unit tests for `BehavioralForecaster` in `apps/control-plane/tests/unit/simulation/test_behavioral_forecaster.py` — synthetic 30-day metric arrays (quality_score, response_time_ms, error_rate); test `forecast`: linregress called per metric; confidence intervals from residuals; trend: rising quality slope > 0.01 → "improving"; flat slope → "stable"; test `load_factor=2.0` scales response_time proportionally; test `confidence_level` derived from R² value (> 0.7 → "high", 0.4-0.7 → "medium", < 0.4 → "low"); test < 7 days history → prediction status set to `insufficient_data`; test ClickHouse unavailable → prediction status `failed`

### Implementation for US4

- [X] T029 [P] [US4] Implement `BehavioralForecaster` in `apps/control-plane/src/platform/simulation/prediction/forecaster.py` — `forecast(twin_id, workspace_id, condition_modifiers)`: fetch 30-day `execution_metrics_daily` from ClickHouse for `twin.source_agent_fqn`; check `< SIMULATION_MIN_PREDICTION_HISTORY_DAYS` → update `BehavioralPrediction(status='insufficient_data')` and return; for each metric: run `scipy.stats.linregress(day_indices, values)` → slope, intercept, r_value; extrapolate next value = slope * (N+1) + intercept; compute CI from residual std: `[value ± 1.96 * std]`; apply `condition_modifiers.load_factor` (multiply response_time, multiply error_rate, divide quality by sqrt(load)); classify trend per metric; set `confidence_level` from R²; update `BehavioralPrediction(status='completed', predicted_metrics=..., history_days_used=N)`; publish `prediction_completed` event
- [X] T030 [US4] Add APScheduler `prediction_worker` background task in `apps/control-plane/src/platform/simulation/prediction/forecaster.py` — poll `BehavioralPrediction(status='pending')` every 30s; process each via `BehavioralForecaster.forecast`; configurable concurrency limit
- [X] T031 [US4] Add `create_behavioral_prediction`, `get_behavioral_prediction` to `apps/control-plane/src/platform/simulation/service.py`
- [X] T032 [US4] Add prediction endpoints to `apps/control-plane/src/platform/simulation/router.py` — `POST /twins/{twin_id}/predict` (202 async), `GET /predictions/{prediction_id}`
- [X] T033 [P] [US4] Write integration tests for prediction endpoints in `apps/control-plane/tests/integration/simulation/test_prediction_endpoints.py` — SQLite ClickHouse fallback with synthetic metric rows; test 202 create → polling GET → completed status; test insufficient_data response

**Checkpoint**: US4 independently testable — behavioral predictions computed with confidence intervals and trend indicators.

---

## Phase 7: User Story 5 — Compare Simulation Results (Priority: P3)

**Goal**: Comparison reports generated with per-metric differences and Welch's t-test significance; prediction-vs-actual accuracy populated; incompatible comparisons rejected.

**Independent Test**: Run two simulations with different configs. POST /simulations/{id}/compare with comparison_type="simulation_vs_simulation". Confirm report shows per-metric delta, direction, and significance. Confirm overall_verdict set. Test incompatible comparison → 422 with incompatibility_reasons. Test prediction_vs_actual → BehavioralPrediction.accuracy_report populated.

### Tests for US5

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T034 [P] [US5] Write unit tests for `ComparisonAnalyzer` in `apps/control-plane/tests/unit/simulation/test_comparison_analyzer.py` — synthetic metric arrays for two runs; test `analyze`: `scipy.stats.ttest_ind` called per metric; p < 0.01 → "high" significance; p >= 0.05 → "low"; direction="better" when quality increases or error_rate decreases; test overall_verdict logic; test incompatible comparison (different agent_fqns) → `compatible=False` + reasons listed; test `prediction_vs_actual`: `accuracy_pct` = 100 - abs((predicted-actual)/actual * 100); test `BehavioralPrediction.accuracy_report` updated

### Implementation for US5

- [X] T035 [P] [US5] Implement `ComparisonAnalyzer` in `apps/control-plane/src/platform/simulation/comparison/analyzer.py` — `analyze(primary_run_id, comparison_type, secondary_run_id, production_baseline_period, prediction_id, workspace_id)`: fetch primary + secondary runs' `results.execution_metrics`; validate compatibility (same `digital_twin_ids` set → compatible; mismatch → set `compatible=False`, populate `incompatibility_reasons`); for each metric: compute delta; classify `direction` (quality: higher is better; response_time/error_rate: lower is better); run `scipy.stats.ttest_ind(primary_values, secondary_values, equal_var=False)`; classify significance by p-value vs `SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA`; determine `overall_verdict`; for `prediction_vs_actual`: load prediction, compute per-metric `accuracy_pct`, update `BehavioralPrediction.accuracy_report`; update `SimulationComparisonReport(status='completed')`; publish `comparison_completed` event
- [X] T036 [US5] Add `create_comparison_report`, `get_comparison_report` to `apps/control-plane/src/platform/simulation/service.py`; run `ComparisonAnalyzer.analyze` as background task (asyncio.create_task) after creating report with `status='pending'`
- [X] T037 [US5] Add comparison endpoints to `apps/control-plane/src/platform/simulation/router.py` — `POST /{run_id}/compare` (202 async), `GET /comparisons/{report_id}`
- [X] T038 [P] [US5] Write integration tests for comparison endpoints in `apps/control-plane/tests/integration/simulation/test_comparison_endpoints.py` — two synthetic completed simulation runs; test full comparison flow; test incompatible comparison returns 422; test prediction_vs_actual accuracy populated

**Checkpoint**: All 5 user stories independently testable — full simulation pipeline functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Reach ≥95% coverage; mypy strict; ruff clean; edge cases covered.

- [X] T039 [P] Add edge case tests across unit test files: simulation infrastructure unavailable (SimulationInfrastructureUnavailableError, 409); twin created from archived agent (warning flag in response, twin remains valid); cancel on `completed` status run (SimulationNotCancellableError, 409); incompatible comparison between mismatched agent sets (422 + incompatibility_reasons); prediction_worker with ClickHouse partial data (`insufficient_data` status)
- [X] T040 [P] Run `mypy --strict` across all simulation modules in `apps/control-plane/src/platform/simulation/` and fix all type errors
- [X] T041 [P] Run `ruff check apps/control-plane/src/platform/simulation/ apps/control-plane/tests/unit/simulation/ apps/control-plane/tests/integration/simulation/` and fix all violations
- [X] T042 Run `pytest apps/control-plane/tests/unit/simulation/ apps/control-plane/tests/integration/simulation/ --cov=platform.simulation --cov-report=term-missing` and close gaps to reach ≥95% line coverage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Requires Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)** and **Phase 4 (US2)**: Both require Phase 2 — can proceed in parallel (different sub-modules)
- **Phase 5 (US3)**: Requires Phase 2; integrates with Phase 3 (`IsolationEnforcer.apply` called inside `create_simulation_run`) — best after US1
- **Phase 6 (US4)**: Requires Phase 4 (BehavioralForecaster uses `DigitalTwin.source_agent_fqn`)
- **Phase 7 (US5)**: Requires Phase 3 (ComparisonAnalyzer reads `SimulationRun.results`); optionally Phase 6 for prediction_vs_actual accuracy
- **Phase 8 (Polish)**: Requires all desired phases complete

### User Story Dependencies

- **US1 (P1)**: Foundational complete — no dependency on other stories
- **US2 (P1)**: Foundational complete — no dependency on other stories; run parallel with US1
- **US3 (P2)**: Integrates with US1 simulation run lifecycle; best after US1 complete
- **US4 (P2)**: Requires US2 (twin provides source_agent_fqn for ClickHouse query)
- **US5 (P3)**: Requires US1 (simulation run results are the comparison input)

### Within Each User Story

- Tests written and FAIL before implementation starts
- Repository/models (Phase 2) before service methods
- Service methods before router endpoints
- Core sub-module implementation before service integration
- Unit tests before integration tests

### Parallel Opportunities

- T002 + T003 (Phase 1) — run in parallel
- T006 + T009 + T010 (Phase 2) — run in parallel
- T012 + T013 (US1 test + implementation) — run in parallel
- T018 + T019 (US2 test + implementation) — run in parallel
- US1 (Phase 3) and US2 (Phase 4) — run fully in parallel after Phase 2
- T023 + T028 (US3 + US4 tests) — run in parallel
- T024 + T029 (US3 + US4 implementations) — run in parallel
- T034 (US5 test) — run in parallel with US5 implementation setup
- T040 + T041 (Phase 8 mypy + ruff) — run in parallel

---

## Parallel Example: User Story 1 + User Story 2

```bash
# After Phase 2 completes, launch both stories together:

# US1 stream:
Task: "T012 Write unit tests for SimulationRunner (test_simulation_runner.py)"
# → confirm FAILS
Task: "T013 Implement SimulationRunner in coordination/runner.py"
Task: "T014 Add Kafka consumer for simulation.events status updates"

# US2 stream (parallel with US1):
Task: "T018 Write unit tests for TwinSnapshotService (test_twin_snapshot.py)"
# → confirm FAILS
Task: "T019 Implement TwinSnapshotService in twins/snapshot.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3 (US1) + Phase 4 (US2) in parallel
4. **STOP and VALIDATE**: Simulation runs created and digital twins snapshotted
5. Merge and demo

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 + US2 → Simulation runs + digital twins → **MVP**
3. US3 → Isolation enforcement (safety layer)
4. US4 → Behavioral predictions
5. US5 → Comparison analytics

### Parallel Team Strategy

With multiple developers (after Phase 2):
- **Developer A**: US1 (coordination/runner.py, Kafka consumer)
- **Developer B**: US2 (twins/snapshot.py, RegistryServiceInterface + ClickHouse)
- **Developer C**: Migration + repository integration test infrastructure

---

## Notes

- [P] tasks = different files, no blocking inter-dependencies at time of execution
- [Story] label maps each task to its user story for traceability
- Tests are mandatory (SC-007: ≥95% coverage) — write them first and confirm FAIL
- ClickHouse uses SQLite aggregate query fallback in integration tests
- Redis uses in-memory dict mock (`REDIS_TEST_MODE=standalone`)
- `SimulationControllerClient` and `RegistryServiceInterface` are always mocked in unit and integration tests
- `PolicyServiceInterface` always mocked; 2 new methods (`register_simulation_policy_bundle`, `deregister_simulation_policy_bundle`) are additive
- All service methods are `async def`; all repository calls use `AsyncSession`
- Default strict isolation policy applied automatically when no custom policy configured (`SIMULATION_DEFAULT_STRICT_ISOLATION=True`)
