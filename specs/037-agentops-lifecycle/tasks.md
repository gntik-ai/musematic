# Tasks: AgentOps Lifecycle Management

**Input**: Design documents from `/specs/037-agentops-lifecycle/`  
**Branch**: `037-agentops-lifecycle`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included — acceptance criteria requires ≥95% line coverage (pytest + pytest-asyncio 8.x, mypy strict, ruff).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task serves (US1–US7 from spec.md)

## Path Conventions

All paths relative to `apps/control-plane/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new packages, create bounded context directory skeleton, and register the runtime profile.

- [X] T001 Add `numpy>=1.26` and `scipy>=1.13` to `apps/control-plane/pyproject.toml` dependencies section and run `pip install -e .` to verify resolution
- [X] T002 Create `apps/control-plane/src/platform/agentops/` directory with empty `__init__.py`; create all sub-module directories: `health/`, `regression/`, `cicd/`, `canary/`, `retirement/`, `governance/`, `adaptation/` — each with empty `__init__.py`
- [X] T003 Register `agentops` runtime profile in `apps/control-plane/src/platform/main.py` — add conditional block that imports and mounts `agentops.router` and registers APScheduler tasks when `RUNTIME_PROFILE=agentops`

**Checkpoint**: `python -m platform.main` starts with `RUNTIME_PROFILE=agentops` without import errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All 9 SQLAlchemy models, Pydantic schemas, repository, Alembic migration, exceptions, Kafka events publisher, and FastAPI dependencies — required before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create `apps/control-plane/src/platform/agentops/models.py` — all 9 SQLAlchemy models in correct mixin order (`Base → UUIDMixin → TimestampMixin → WorkspaceScopedMixin → concrete columns`): `AgentHealthConfig`, `AgentHealthScore`, `BehavioralBaseline`, `BehavioralRegressionAlert`, `CiCdGateResult`, `CanaryDeployment`, `RetirementWorkflow`, `GovernanceEvent` (no `updated_at`, no update/delete), `AdaptationProposal`; indexes on `(agent_fqn, workspace_id)`; JSONB columns as `postgresql.JSONB`
- [X] T005 Create `apps/control-plane/src/platform/agentops/schemas.py` — Pydantic v2 request/response schemas for all 7 API sections (health, regression, gate, canary, retirement, governance, adaptation); field validators: weight sum = 100.0, traffic_percentage ∈ [1,50], observation_window_hours ≥ 1.0, decision ∈ {"approved","rejected"}
- [X] T006 Create `apps/control-plane/src/platform/agentops/repository.py` — `AgentOpsRepository` async class with methods for all models; `insert_governance_event()` with no update/delete counterpart; `upsert_health_score()` using `ON CONFLICT (agent_fqn, workspace_id) DO UPDATE`; cursor-based pagination for all list methods
- [X] T007 Create `apps/control-plane/src/platform/agentops/exceptions.py` — `AgentOpsError`, `CanaryConflictError` (409), `BaselineNotReadyError` (412), `RetirementConflictError` (409), `InsufficientSampleError` (412), `WeightSumError` (400), all inheriting from project's `PlatformError`
- [X] T008 Create `apps/control-plane/src/platform/agentops/events.py` — `AgentOpsEventPublisher` class with async `publish(event_type, agent_fqn, workspace_id, payload, actor)` method wrapping `EventEnvelope` and publishing to `agentops.events` Kafka topic (key: `agent_fqn`); `GovernanceEventPublisher.record(...)` wrapper for insert-only governance event creation
- [X] T009 Create `apps/control-plane/src/platform/agentops/dependencies.py` — FastAPI `Annotated[AgentOpsService, Depends(get_agentops_service)]` dependency; workspace scoping from JWT token; `get_agentops_service` factory wiring `AgentOpsRepository`, `AgentOpsEventPublisher`, all 5 service interface clients
- [X] T010 Create `apps/control-plane/migrations/versions/037_agentops_lifecycle.py` — Alembic migration creating all 9 tables with correct column types, constraints, indexes; include ClickHouse DDL for `agentops_behavioral_versions` as a comment block for separate application via `clickhouse-connect`
- [X] T011 Create `apps/control-plane/src/platform/agentops/service.py` stub — `AgentOpsService` class with empty method signatures for all operations from `contracts/service-interfaces.md` (exposed interface); constructor accepts repository + publisher + service interface clients

**Checkpoint**: `make migrate` applies migration cleanly; `mypy` finds no import errors in the agentops package; all models and schemas importable.

---

## Phase 3: User Story 1 — Monitor Agent Health (Priority: P1) 🎯 MVP

**Goal**: Composite health scores computed on schedule and queryable per agent with configurable dimension weights.

**Independent Test**: Configure weights (quality=50%, uptime=50%), trigger `score_all_agents_task()` with mock dimension data, confirm composite score = weighted average, confirm upsert to `agentops_health_scores`, confirm warning event fires when score drops below threshold.

### Tests for User Story 1

- [X] T012 [P] [US1] Write unit tests in `apps/control-plane/tests/unit/agentops/test_health_dimensions.py` — mock Redis/ClickHouse/service interface calls; test each dimension fetcher returns `DimensionResult(score, sample_count)`; test `None` return when sample count < minimum
- [X] T013 [P] [US1] Write unit tests in `apps/control-plane/tests/unit/agentops/test_health_scorer.py` — test composite score calculation with full dimensions; test weight redistribution when 1 or 2 dimensions return `None`; test `below_warning` and `below_critical` flags; test `insufficient_data` flag when all dimensions None

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement `apps/control-plane/src/platform/agentops/health/dimensions.py` — five async fetchers: `uptime_score()` reads Redis `fleet:member:avail:{fleet_id}:{fqn}` keys (uptime ratio); `quality_score()` queries ClickHouse `agentops_behavioral_versions` 30-day rolling average; `safety_score()` calls `TrustServiceInterface.get_guardrail_pass_rate()`; `cost_efficiency_score()` fetches cost-per-quality from ClickHouse `analytics_*`; `satisfaction_score()` calls `EvalSuiteServiceInterface` human grade aggregate; each returns `DimensionResult(score: float | None, sample_count: int)`
- [X] T015 [US1] Implement `apps/control-plane/src/platform/agentops/health/scorer.py` — `HealthScorer.compute(agent_fqn, workspace_id, config)`: calls all 5 dimension fetchers with `asyncio.gather`; redistribute weights proportionally for None dimensions; compute weighted composite; set `below_warning`/`below_critical`/`insufficient_data` flags; call `GovernanceEventPublisher.record` if threshold crossed; return `HealthScoreResult`; `score_all_agents_task()` APScheduler entry point that queries active agents and calls `compute` for each
- [X] T016 [US1] Add health score endpoints to `apps/control-plane/src/platform/agentops/router.py` — `GET /{agent_fqn}/health`, `GET /{agent_fqn}/health/history` (cursor pagination), `GET /health-config`, `PUT /health-config` (validate weight sum = 100.0); all workspace-scoped from JWT
- [X] T017 [P] [US1] Write integration tests in `apps/control-plane/tests/integration/agentops/test_health_endpoints.py` — test `GET /health` returns 200 with correct schema; test `PUT /health-config` rejects weights summing to ≠100 with 400; test `GET /health` returns `insufficient_data: true` when no score exists; use SQLite local mode + mock service interfaces

**Checkpoint**: Health score computes and persists; `GET /{agent_fqn}/health` returns correct composite; weight config update recalculates.

---

## Phase 4: User Story 2 — Detect Behavioral Regression (Priority: P1)

**Goal**: Statistical comparison between revision samples; regression alerts created and queryable; alerts block promotion.

**Independent Test**: Feed two synthetic arrays (one normal quality ~0.9, one degraded ~0.7) to `StatisticalComparator`; confirm Welch t-test selected for n≥30; confirm p < 0.05; confirm `BehavioralRegressionAlert` created with correct dimensions and statistics; confirm `get_active_regression_alerts()` service interface returns the alert.

### Tests for User Story 2

- [X] T018 [P] [US2] Write unit tests in `apps/control-plane/tests/unit/agentops/test_statistics.py` — test Welch t-test selected when n=50, both samples pass Shapiro-Wilk; test Mann-Whitney U selected when n=15 (< 30); test known p-values with synthetic scipy distributions; test `significant=True` when p < alpha; test `significant=False` when p ≥ alpha; test effect size calculation
- [X] T019 [P] [US2] Write unit tests in `apps/control-plane/tests/unit/agentops/test_regression_detector.py` — mock ClickHouse sample fetching; test alert created for regressed quality dimension; test no alert when within variance; test `InsufficientSampleError` when samples < minimum; test alert status `active` blocks `get_active_regression_alerts()`

### Implementation for User Story 2

- [X] T020 [P] [US2] Implement `apps/control-plane/src/platform/agentops/regression/statistics.py` — `StatisticalComparator.compare(sample_a: list[float], sample_b: list[float], alpha: float) -> ComparisonResult`: if both n≥30, run `scipy.stats.shapiro` on each — if both p>0.05 use `scipy.stats.ttest_ind(equal_var=False)` (Welch) else `scipy.stats.mannwhitneyu`; compute Cohen's d or rank-biserial; return `ComparisonResult(test_type, statistic, p_value, effect_size, significant)`
- [X] T021 [US2] Implement `apps/control-plane/src/platform/agentops/regression/detector.py` — `RegressionDetector.detect(new_revision_id, baseline_revision_id, agent_fqn, workspace_id)`: fetch ClickHouse `agentops_behavioral_versions` samples for both revisions per dimension (quality, latency, cost, safety); call `StatisticalComparator.compare` per dimension; if any significant → create `BehavioralRegressionAlert` via repository; call `GovernanceEventPublisher.record('regression_detected', ...)` + publish to Kafka
- [X] T022 [US2] Add Kafka consumer in `apps/control-plane/src/platform/agentops/governance/triggers.py` — consume `evaluation.events` topic; on `evaluation.run.completed` event: fetch `BehavioralBaseline` for evaluated revision; if baseline ready call `RegressionDetector.detect`; if baseline pending check sample count and materialize baseline if threshold reached
- [X] T023 [US2] Add `get_active_regression_alerts()` to `apps/control-plane/src/platform/agentops/service.py` — exposed `AgentOpsServiceInterface` method; queries repository for alerts with `status='active'` for the given revision
- [X] T024 [US2] Add regression endpoints to `apps/control-plane/src/platform/agentops/router.py` — `GET /{agent_fqn}/regression-alerts`, `GET /regression-alerts/{alert_id}`, `POST /regression-alerts/{alert_id}/resolve`; workspace-scoped
- [X] T025 [P] [US2] Write integration tests in `apps/control-plane/tests/integration/agentops/test_regression_endpoints.py` — test `GET /regression-alerts` filters by status; test `POST /resolve` changes status to `resolved`; test alert with `status='active'` appears in `get_active_regression_alerts()` interface

**Checkpoint**: `StatisticalComparator` produces correct results with synthetic data; regression detector creates alerts; active alerts visible via service interface.

---

## Phase 5: User Story 3 — Gate Agent Deployment via CI/CD Checks (Priority: P2)

**Goal**: All 5 gates run concurrently via `asyncio.gather`; gate result persisted; any failure blocks deployment.

**Independent Test**: Mock all 5 service interfaces — one returning failure (certification expired). Call `CiCdGate.evaluate()`; confirm all 5 gates ran (not short-circuited); confirm `overall_passed=False`; confirm gate result persisted; confirm `run_gate_check()` service interface returns correct summary.

### Tests for User Story 3

- [X] T026 [P] [US3] Write unit tests in `apps/control-plane/tests/unit/agentops/test_cicd_gate.py` — mock all 5 service interfaces; test all-pass → `overall_passed=True`; test single failure (cert expired) → `overall_passed=False` with all 5 gates still evaluated (no short-circuit); test multi-failure populates all failure details; test remediation text present for each failed gate

### Implementation for User Story 3

- [X] T027 [US3] Implement `apps/control-plane/src/platform/agentops/cicd/gate.py` — `CiCdGate.evaluate(agent_fqn, revision_id, workspace_id, requested_by)`: run `asyncio.gather(_policy_gate(), _eval_gate(), _cert_gate(), _regression_gate(), _trust_gate())` — each sub-coroutine calls appropriate service interface and returns `GateVerdict(passed, detail, remediation)`; assemble `CiCdGateResultCreate`; upsert `CiCdGateResult` via repository; record governance event; return response schema
- [X] T028 [US3] Add `run_gate_check()` method to `apps/control-plane/src/platform/agentops/service.py` — exposed `AgentOpsServiceInterface` method delegating to `CiCdGate.evaluate`
- [X] T029 [US3] Add gate endpoints to `apps/control-plane/src/platform/agentops/router.py` — `POST /{agent_fqn}/gate-check`, `GET /{agent_fqn}/gate-checks`; `POST` returns 200 with full gate report; workspace-scoped
- [X] T030 [P] [US3] Write integration tests in `apps/control-plane/tests/integration/agentops/test_gate_endpoints.py` — test `POST /gate-check` with all-mock-pass returns `overall_passed: true`; test with cert-mock-fail returns 200 (not 4xx) with `overall_passed: false` and `certification_gate_passed: false`

**Checkpoint**: `POST /{agent_fqn}/gate-check` evaluates all 5 gates concurrently and returns structured gate report; service interface usable by runtime controller.

---

## Phase 6: User Story 4 — Canary Deploy with Automatic Evaluation (Priority: P2)

**Goal**: Canary deployment starts with Redis routing key; APScheduler monitor auto-promotes or auto-rolls-back; manual overrides recorded.

**Independent Test**: Start a canary at 10% traffic; confirm Redis key written with correct TTL; mock metric polling returning degraded quality; confirm `monitor_active_canaries_task()` triggers rollback; confirm Redis key cleared; confirm `status='auto_rolled_back'` in DB.

### Tests for User Story 6

- [X] T031 [P] [US4] Write unit tests in `apps/control-plane/tests/unit/agentops/test_canary_manager.py` — test `start()` writes Redis key; test `start()` raises `CanaryConflictError` when active canary exists; test `promote()` clears Redis key and sets `status='auto_promoted'`; test `rollback()` clears Redis key and sets `triggered_rollback=True` on related regression alert
- [X] T032 [P] [US4] Write unit tests in `apps/control-plane/tests/unit/agentops/test_canary_monitor.py` — test metric fetch below tolerance → no action; test metric above tolerance threshold → triggers `rollback()`; test observation window elapsed with healthy metrics → triggers `promote()`

### Implementation for User Story 4

- [X] T033 [US4] Implement `apps/control-plane/src/platform/agentops/canary/manager.py` — `CanaryManager.start(create_request)`: query repository for active canary (raise `CanaryConflictError` if exists); write Redis key `canary:{workspace_id}:{agent_fqn}` with JSON payload and TTL (observation_window_end + 3600s) using `SET ... EX` atomic operation; insert `CanaryDeployment`; record governance event; `promote(canary_id, manual)`: `DEL` Redis key; update status; emit event; `rollback(canary_id, reason, manual)`: `DEL` Redis key; update status; if triggered by regression alert set `triggered_rollback=True`
- [X] T034 [US4] Implement `apps/control-plane/src/platform/agentops/canary/monitor.py` — `CanaryMonitor.monitor_active_canaries_task()` APScheduler task: query all `status='active'` canaries; for each, fetch ClickHouse metrics for canary revision (quality, latency, error rate, cost) and compare against production revision metrics; if any metric deviation > tolerance → call `manager.rollback(canary_id, reason='auto', manual=False)`; if observation window elapsed and all metrics within tolerance → call `manager.promote(canary_id, manual=False)`; update `latest_metrics_snapshot`
- [X] T035 [US4] Add canary endpoints to `apps/control-plane/src/platform/agentops/router.py` — all 6 endpoints per `contracts/api-endpoints.md`: `POST /{agent_fqn}/canary` (201, 409 on conflict), `GET /{agent_fqn}/canary/active`, `GET /canaries/{canary_id}`, `POST /canaries/{canary_id}/promote`, `POST /canaries/{canary_id}/rollback`, `GET /{agent_fqn}/canaries`
- [X] T036 [P] [US4] Write integration tests in `apps/control-plane/tests/integration/agentops/test_canary_endpoints.py` — test `POST /canary` returns 201 with correct schema; test second `POST /canary` for same agent returns 409; test `POST /canaries/{id}/rollback` changes status and records governance event; test `GET /{agent_fqn}/canary/active` returns null when none active

**Checkpoint**: Canary deployment creates Redis routing key; manual promote/rollback work via API; auto-monitor task runs and responds to metric thresholds.

---

## Phase 7: User Story 5 — Automate Agent Retirement (Priority: P3)

**Goal**: Retirement triggered automatically on sustained health degradation or certification expiry; dependency detection; grace period enforcement; high-impact confirmation required.

**Independent Test**: Simulate 6 consecutive `below_critical` health score updates; confirm `RetirementWorkflow` created with `trigger_reason='sustained_degradation'`; confirm `find_workflows_using_agent()` results captured in `dependent_workflows`; confirm `high_impact_flag=True` if any found; confirm grace period expiry calls `retire_agent()` and disables marketplace visibility.

### Tests for User Story 5

- [X] T037 [P] [US5] Write unit tests in `apps/control-plane/tests/unit/agentops/test_retirement_workflow.py` — test `initiate()` raises `RetirementConflictError` if active retirement exists; test `high_impact_flag=True` when `find_workflows_using_agent()` returns non-empty; test `operator_confirmed` required before retiring high-impact agent; test `halt()` sets `status='halted'`; test `retire_agent()` calls `RegistryService.set_marketplace_visibility(False)`
- [X] T038 [P] [US5] Write unit tests in `apps/control-plane/tests/unit/agentops/test_grace_period.py` — test grace period scanner skips retirement workflows where `grace_period_ends_at > now()`; test scanner calls `retire_agent()` when `grace_period_ends_at <= now()` and `status='grace_period'`

### Implementation for User Story 5

- [X] T039 [US5] Implement `apps/control-plane/src/platform/agentops/retirement/workflow.py` — `RetirementManager.initiate(agent_fqn, trigger_reason, workspace_id, triggered_by)`: query repository for active retirement (raise `RetirementConflictError` if exists); call `WorkflowServiceInterface.find_workflows_using_agent()`; set `high_impact_flag`; if `high_impact_flag` and not `operator_confirmed`, raise `PreconditionError`; insert `RetirementWorkflow(status='grace_period')`; publish notification via `AgentOpsEventPublisher`; record governance event; `retire_agent(workflow_id)`: call `RegistryServiceInterface.set_marketplace_visibility(False)`; update `status='retired'`; record `retirement_completed` governance event; `halt(workflow_id, reason)`: update `status='halted'`
- [X] T040 [US5] Implement APScheduler tasks in `apps/control-plane/src/platform/agentops/governance/grace_period.py` — `retirement_grace_period_scanner_task()`: query `RetirementWorkflow` where `status='grace_period'` and `grace_period_ends_at <= now()`; call `RetirementManager.retire_agent()` for each; `recertification_grace_period_scanner_task()`: scan `pending_recertification` agents with expired grace period (from trust service); call `TrustServiceInterface` to expire certification; emit governance event; optionally call `RegistryServiceInterface.set_marketplace_visibility(False)`
- [X] T041 [US5] Add consecutive critical interval tracking to `apps/control-plane/src/platform/agentops/health/scorer.py` — after computing health score: if `below_critical`, increment Redis counter `agentops:critical_intervals:{workspace_id}:{agent_fqn}` with TTL = 2 × scoring_interval; if counter ≥ `AGENTOPS_RETIREMENT_CRITICAL_INTERVALS`, publish `retirement_trigger` event to Kafka `agentops.events`; reset counter when score recovers above critical threshold
- [X] T042 [US5] Add retirement consumer in `apps/control-plane/src/platform/agentops/governance/triggers.py` — consume `agentops.events` `retirement_trigger` event type; call `RetirementManager.initiate(trigger_reason='sustained_degradation')`
- [X] T043 [US5] Add retirement endpoints to `apps/control-plane/src/platform/agentops/router.py` — `POST /{agent_fqn}/retire` (201), `GET /retirements/{workflow_id}`, `POST /retirements/{workflow_id}/halt`, `POST /retirements/{workflow_id}/confirm`; `POST /confirm` sets `operator_confirmed=True` for high-impact retirements
- [X] T044 [P] [US5] Write integration tests in `apps/control-plane/tests/integration/agentops/test_retirement_endpoints.py` — test `POST /retire` returns 201; test second `POST /retire` same agent returns 409; test `POST /confirm` enables retirement of high-impact agent; test `POST /halt` sets `status='halted'`

**Checkpoint**: Retirement workflow initiates automatically from health trigger and certification expiry; grace period scanner deactivates agents; high-impact confirmation works.

---

## Phase 8: User Story 6 — Enforce Continuous Governance (Priority: P3)

**Goal**: Recertification triggers fire on all 5 trigger types; governance events append-only; grace period scanner enforces certification expiry.

**Independent Test**: Publish a `trust.events` revision_change event for a certified agent; confirm agent marked `pending_recertification`; confirm `GovernanceEvent` inserted (not updated); confirm `recertification_grace_period_scanner_task()` expires certification after grace period; confirm `GET /{agent_fqn}/governance-events` shows full audit trail in order.

### Tests for User Story 6

- [X] T045 [P] [US6] Write unit tests in `apps/control-plane/tests/unit/agentops/test_governance_triggers.py` — test each of the 5 trigger types fires `TrustServiceInterface.trigger_recertification()`; test governance event inserted (never updated); test Kafka consumer idempotency (duplicate event does not double-trigger)
- [X] T046 [P] [US6] Write integration tests in `apps/control-plane/tests/integration/agentops/test_governance_endpoints.py` — test `GET /{agent_fqn}/governance-events` returns chronological list with correct cursor pagination; test `GET /{agent_fqn}/governance` returns current cert status, pending triggers, upcoming expirations

### Implementation for User Story 6

- [X] T047 [US6] Complete `apps/control-plane/src/platform/agentops/governance/triggers.py` — Kafka consumer group for `trust.events` and `agentops.events` topics: on `trust.agent_revision_changed`, `trust.policy_changed`, `trust.certification_expiring`, `trust.conformance_failed`, `agentops.regression_detected` → call `TrustServiceInterface.trigger_recertification(agent_fqn, revision_id, trigger_reason)` + call `GovernanceEventPublisher.record('recertification_triggered', ...)`; use `aiokafka` consumer with manual commit after successful processing for at-least-once delivery
- [X] T048 [US6] Add governance endpoints to `apps/control-plane/src/platform/agentops/router.py` — `GET /{agent_fqn}/governance-events` with `event_type`, `since`, `limit` filters and cursor pagination; `GET /{agent_fqn}/governance` returning `GovernanceSummaryResponse` (current cert status + pending triggers + upcoming expirations within 30 days)
- [X] T049 [US6] Verify `apps/control-plane/src/platform/agentops/repository.py` `insert_governance_event()` has no `update_governance_event()` or `delete_governance_event()` methods — and add a ruff rule comment asserting this invariant; add `GovernanceSummaryRepository.get_summary()` method joining governance events with trust service data

**Checkpoint**: All 5 recertification triggers fire correctly; governance events are insert-only; `GET /{agent_fqn}/governance-events` shows full audit trail; grace period scanner enforces expiry.

---

## Phase 9: User Story 7 — Agent Self-Improvement Pipeline (Priority: P4)

**Goal**: Rule-based adaptation proposals from 4 signal detectors; human approval gates revision creation; ATE test drives promotion.

**Independent Test**: Feed 14 days of mock declining quality data to `BehavioralAnalyzer`; confirm signal detected with correct type and supporting data; confirm `AdaptationProposal` created with `status='proposed'`; approve proposal; confirm revision candidate created via `RegistryServiceInterface`; submit mock ATE pass result; confirm status becomes `promoted`.

### Tests for User Story 7

- [X] T050 [P] [US7] Write unit tests in `apps/control-plane/tests/unit/agentops/test_adaptation_analyzer.py` — test each of 4 signal rules: quality trend slope < -0.005/day → signal detected; cost-quality > 2× workspace average → signal detected; failure pattern count > 20% → signal detected; tool utilization < 10% → signal detected; test no signals when all metrics within normal range → empty list returned
- [X] T051 [P] [US7] Write unit tests in `apps/control-plane/tests/unit/agentops/test_adaptation_pipeline.py` — test `propose()` with signals → creates `AdaptationProposal` with `status='proposed'`; test `propose()` with no signals → creates proposal with special `no_opportunities` note; test `review()` with `approved` → calls `RegistryServiceInterface` + `EvalSuiteServiceInterface.submit_to_ate`; test `review()` with `rejected` → status `rejected`, no revision created; test `handle_ate_result(passed=True)` → status `promoted`; test `handle_ate_result(passed=False)` → status `failed`

### Implementation for User Story 7

- [X] T052 [US7] Implement `apps/control-plane/src/platform/agentops/adaptation/analyzer.py` — `BehavioralAnalyzer.analyze(agent_fqn, workspace_id)`: fetch 14-day quality score array from ClickHouse, compute linear regression slope with `numpy.polyfit`; fetch 7-day failure event types from `agentops_behavioral_versions`; compute cost-quality ratio vs workspace average; count tool invocations per available tool; apply 4 rules; return `list[AdaptationSignal]` (empty if no opportunities); each `AdaptationSignal` includes rule type, supporting metric values, and a human-readable rationale string
- [X] T053 [US7] Implement `apps/control-plane/src/platform/agentops/adaptation/pipeline.py` — `AdaptationPipeline.propose(agent_fqn, workspace_id, triggered_by)`: call `BehavioralAnalyzer.analyze()`; map signals to proposed adjustments (each signal type → specific adjustment: quality→context_profile, cost→model_params, failures→approach_text, tools→tool_selection); insert `AdaptationProposal(status='proposed')`; record governance event; `review(proposal_id, decision, reason, reviewed_by)`: if `approved` → call `RegistryServiceInterface.get_agent_revision()` + create candidate + call `EvalSuiteServiceInterface.submit_to_ate()` → set `status='testing'`; if `rejected` → set `status='rejected'`; `handle_ate_result(ate_run_id, passed)`: find proposal by `ate_run_id`; if `passed` → `status='promoted'`; if not → `status='failed'`; both record governance event
- [X] T054 [US7] Add ATE result consumer in `apps/control-plane/src/platform/agentops/governance/triggers.py` — consume `evaluation.events` `ate.run.completed`; call `AdaptationPipeline.handle_ate_result(ate_run_id, passed)`
- [X] T055 [US7] Add adaptation endpoints to `apps/control-plane/src/platform/agentops/router.py` — `POST /{agent_fqn}/adapt` (201, triggers analysis and proposal creation), `POST /adaptations/{proposal_id}/review` (decision required), `GET /{agent_fqn}/adaptation-history` (cursor pagination)
- [X] T056 [P] [US7] Write integration tests in `apps/control-plane/tests/integration/agentops/test_adaptation_endpoints.py` — test `POST /adapt` creates proposal with `status='proposed'`; test `POST /adaptations/{id}/review` with `approved` transitions to `testing`; test `POST /adaptations/{id}/review` with `rejected` transitions to `rejected`; test `GET /adaptation-history` returns all proposals with correct status

**Checkpoint**: Adaptation proposal cycle works end-to-end: analyze → propose → approve → ATE submit → promote.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Coverage closure, strict type checking, lint, and final integration validation.

- [X] T057 [P] Run `pytest apps/control-plane/tests/unit/agentops/ --cov=platform/agentops --cov-report=term-missing` and add targeted unit tests for any uncovered branches; focus on error paths (database failures, service interface failures, Kafka publish failures)
- [X] T058 [P] Run `mypy --strict apps/control-plane/src/platform/agentops/` and fix all type errors; pay special attention to `JSONB` column typing, `asyncio.gather` return type unpacking, and `scipy.stats` return type annotations
- [X] T059 [P] Run `ruff check apps/control-plane/src/platform/agentops/` and fix all lint errors; ensure all public functions have docstrings per constitution coding conventions
- [X] T060 [P] Add `agentops` runtime profile configuration to `apps/control-plane/src/platform/common/config.py` (PlatformSettings) — all 8 `AGENTOPS_*` settings with defaults from `quickstart.md`
- [X] T061 Validate full feature integration: run `make migrate` against clean DB; start with `RUNTIME_PROFILE=agentops`; confirm all 4 APScheduler tasks register; confirm `GET /api/v1/agentops/health-config` returns 200; run `pytest tests/integration/agentops/ -v --tb=short` and confirm all pass

**Checkpoint**: `pytest --cov` reports ≥95% coverage; `mypy --strict` and `ruff check` both exit 0; integration test suite passes against local DB.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1)**: Depends on Phase 2 — no dependency on US2–US7
- **Phase 4 (US2)**: Depends on Phase 2 — no dependency on US1; requires ClickHouse `agentops_behavioral_versions` table (from migration T010)
- **Phase 5 (US3)**: Depends on Phase 2 + Phase 4 (regression gate calls `get_active_regression_alerts`)
- **Phase 6 (US4)**: Depends on Phase 2 + Phase 5 (canary needs gate check before start)
- **Phase 7 (US5)**: Depends on Phase 2 + Phase 3 (health scorer triggers retirement)
- **Phase 8 (US6)**: Depends on Phase 2 — governance triggers are independent; grace period scanner extends Phase 7
- **Phase 9 (US7)**: Depends on Phase 2 — adaptation pipeline is largely independent
- **Phase 10 (Polish)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: After Foundation — independent
- **US2 (P1)**: After Foundation — independent of US1; parallel with US1
- **US3 (P2)**: After US2 (regression gate consumes `get_active_regression_alerts`)
- **US4 (P2)**: After US3 (canary start should validate gate check passed)
- **US5 (P3)**: After US1 (health scorer retirement trigger); independent of US2/US3/US4
- **US6 (P3)**: After Foundation — largely independent; grace period scanner completes Phase 7 retirement flow
- **US7 (P4)**: After Foundation — independent; requires ATE service interface from evaluation (feature 034)

### Within Each User Story

- Unit tests → implementation → integration tests
- Models/exceptions (Phase 2) before services, services before endpoints
- Kafka consumers before APScheduler tasks (consumers provide data for tasks)

### Parallel Opportunities

- US1 and US2 can run in parallel after Foundation (both P1, different files)
- US5, US6, US7 can run in parallel after their prerequisites (all different files)
- All `[P]` test tasks within each phase run concurrently
- Foundation tasks T004–T011 have sequential dependencies within them (models before schemas before repository)

---

## Parallel Example: Foundation Phase (Phase 2)

```bash
# Sequential order within foundation:
T004 → models.py           # First
T005 → schemas.py          # After models (schemas import model enums)
T006 → repository.py       # After models
T007 → exceptions.py       # Parallel with T005/T006
T008 → events.py           # Parallel with T005/T006
T009 → dependencies.py     # After service.py stub exists
T010 → migration           # After models.py
T011 → service.py stub     # After repository + exceptions
```

## Parallel Example: US1 + US2 (simultaneous after Foundation)

```bash
# Developer A: US1 (health scoring)
T012 → test_health_dimensions.py
T013 → test_health_scorer.py
T014 → health/dimensions.py
T015 → health/scorer.py
T016 → router.py (health endpoints)
T017 → test_health_endpoints.py

# Developer B: US2 (regression detection) simultaneously
T018 → test_statistics.py
T019 → test_regression_detector.py
T020 → regression/statistics.py
T021 → regression/detector.py
T022 → governance/triggers.py (eval consumer)
T023 → service.py (interface method)
T024 → router.py (regression endpoints)
T025 → test_regression_endpoints.py
```

---

## Implementation Strategy

### MVP First (US1 Health Scoring Only)

1. Phase 1: Setup (T001–T003)
2. Phase 2: Foundation (T004–T011)
3. Phase 3: US1 Health Scoring (T012–T017)
4. **STOP and VALIDATE**: Health scores compute, persist, and return via API
5. Demo: operators can view per-agent health with dimension breakdown

### Incremental Delivery

1. Foundation ready → US1 + US2 in parallel (P1 stories)
2. US1 + US2 → **Health monitoring + regression detection live**
3. US3 + US4 → **Safe deployments + canary rollout**
4. US5 + US6 in parallel → **Automated retirement + governance**
5. US7 → **Self-improvement pipeline**
6. Polish → **Production-ready**

### Parallel Team Strategy (3 developers)

1. All: Phase 1 + Phase 2 (foundation)
2. After foundation:
   - **Dev A**: US1 (T012–T017), then US5 (T037–T044)
   - **Dev B**: US2 (T018–T025), then US3 (T026–T030), then US6 (T045–T049)
   - **Dev C**: US4 (T031–T036), then US7 (T050–T056)
3. All: Phase 10 (Polish)

---

## Notes

- `[P]` tasks = different files, safe to run in parallel
- `[Story]` label maps each task to its user story
- `agentops_governance_events` is insert-only — no update/delete methods may be added to repository
- Redis canary key must be written with atomic `SET ... EX` — no separate SET + EXPIRE
- `asyncio.gather` in gate check must NOT use `return_exceptions=False` — wrap each gate sub-coroutine in its own try/except to ensure all 5 gates complete regardless of individual errors
- `scipy` calls are synchronous — wrap in `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop for large sample arrays
- Commit after each task or logical group; each story phase produces a shippable increment
