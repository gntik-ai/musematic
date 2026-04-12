# Tasks: Evaluation Framework and Semantic Testing

**Input**: Design documents from `specs/034-evaluation-semantic-testing/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/evaluation-api.md ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- Exact file paths follow `apps/control-plane/src/platform/<context>/` convention

---

## Phase 1: Setup

**Purpose**: Directory scaffold and module initialization for both bounded contexts

- [X] T001 Create `apps/control-plane/src/platform/evaluation/` and `apps/control-plane/src/platform/testing/` directory structures with `__init__.py` files and `apps/control-plane/src/platform/evaluation/scorers/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 Create Alembic migration 034 in `apps/control-plane/migrations/versions/034_evaluation_testing_schema.py` — all 13 tables: evaluation_eval_sets, evaluation_benchmark_cases, evaluation_runs, evaluation_judge_verdicts, evaluation_ab_experiments, evaluation_ate_configs, evaluation_ate_runs, evaluation_robustness_runs, evaluation_human_grades, testing_generated_suites, testing_adversarial_cases, testing_coordination_results, testing_drift_alerts
- [X] T003 [P] Create `apps/control-plane/src/platform/evaluation/models.py` — 9 SQLAlchemy async models (EvalSet, BenchmarkCase, EvaluationRun, JudgeVerdict, AbExperiment, ATEConfig, ATERun, RobustnessTestRun, HumanAiGrade) with Base + UUIDMixin + TimestampMixin + WorkspaceScopedMixin/SoftDeleteMixin where applicable; 6 enums (EvalSetStatus, RunStatus, VerdictStatus, ExperimentStatus, ATERunStatus, ReviewDecision)
- [X] T004 [P] Create `apps/control-plane/src/platform/evaluation/schemas.py` — Pydantic v2 request/response schemas for EvalSet, BenchmarkCase, EvaluationRun, JudgeVerdict, AbExperiment, ATEConfig, ATERun, RobustnessTestRun, HumanAiGrade, ReviewProgressResponse
- [X] T005 [P] Create `apps/control-plane/src/platform/evaluation/events.py` — async Kafka producer helpers for `evaluation.events` topic using `EventEnvelope`; all 10 event types (run.started, run.completed, run.failed, verdict.scored, ab_experiment.completed, ate.run.completed, ate.run.failed, robustness.completed, drift.detected, human.grade.submitted)
- [X] T006 Create `apps/control-plane/src/platform/evaluation/repository.py` — async SQLAlchemy repository for all 9 evaluation models using `AsyncSession`; CRUD + query methods (list by workspace, list verdicts by run, get by id); depends on T003
- [X] T007 [P] Create `apps/control-plane/src/platform/evaluation/scorers/base.py` — abstract `Scorer` Protocol with `async def score(actual: str, expected: str, config: dict) -> ScoreResult`; `ScoreResult` Pydantic model (score: float | None, passed: bool | None, rationale: str | None, error: str | None, extra: dict)
- [X] T008 [P] Create `apps/control-plane/src/platform/evaluation/scorers/exact_match.py` — `ExactMatchScorer`: case-sensitive string equality; score=1.0 if match else 0.0; passed if score >= threshold (default 1.0)
- [X] T009 [P] Create `apps/control-plane/src/platform/evaluation/scorers/regex.py` — `RegexScorer`: compile pattern from `config["pattern"]`; score=1.0 if `re.search` finds match in actual_output else 0.0; error on invalid regex
- [X] T010 [P] Create `apps/control-plane/src/platform/evaluation/scorers/json_schema.py` — `JsonSchemaScorer`: parse actual_output as JSON; validate against `config["schema"]` using `jsonschema` library; score=1.0 if valid else 0.0; include validation errors in rationale
- [X] T011 Create `apps/control-plane/src/platform/evaluation/scorers/registry.py` — `ScorerRegistry` class with `register(scorer_type: str, scorer: Scorer)` and `get(scorer_type: str) -> Scorer`; pre-populate with ExactMatchScorer, RegexScorer, JsonSchemaScorer at module load; depends on T007-T010

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Evaluation Suites and Scorer Registry (Priority: P1) 🎯 MVP

**Goal**: Create and run eval sets against agents; score benchmark cases using multiple scorer types (exact match, regex, JSON schema, semantic similarity); compare two runs via A/B experiment.

**Independent Test**: Create eval set with 5 cases, run against mock agent, verify 5 verdicts with scores from exact_match + semantic scorers; create A/B experiment comparing two completed runs (T01, T02, T03 from quickstart.md).

- [X] T012 [US1] Create `apps/control-plane/src/platform/evaluation/scorers/semantic.py` — `SemanticSimilarityScorer`: on app startup provision Qdrant collection `evaluation_embeddings` (1536-dim, Cosine distance) via `QdrantClient`; embed `actual_output` and `expected_output` via httpx call to model provider embedding endpoint; compute cosine similarity; return score between 0.0 and 1.0 with pass/fail based on `config["threshold"]` (default 0.8); update `evaluation/scorers/registry.py` to register SemanticSimilarityScorer
- [X] T013 [US1] Create `apps/control-plane/src/platform/evaluation/service.py` — `EvalSuiteService`: async CRUD for EvalSet + BenchmarkCase via repository; `EvalRunnerService`: create EvaluationRun (status=pending), iterate BenchmarkCase rows, call `ScorerRegistry` for each configured scorer, write JudgeVerdict per case with `scorer_results` JSONB, update EvaluationRun aggregates (passed/failed/error/aggregate_score), emit Kafka events via events.py
- [X] T014 [US1] Create `apps/control-plane/src/platform/evaluation/ab_experiment_service.py` — `AbExperimentService`: fetch `overall_score` arrays from both run's verdicts; Welch's t-test using Python `statistics.NormalDist` and manual t-statistic calculation; Cohen's d effect size; 95% confidence interval; determine winner ("a"/"b"/"inconclusive" at p < 0.05); write AbExperiment result; emit `evaluation.ab_experiment.completed`
- [X] T015 [US1] Implement eval-sets, benchmark cases, and experiments endpoints in `apps/control-plane/src/platform/evaluation/router.py` — POST/GET/PATCH/DELETE `/eval-sets`; POST/GET/DELETE `/eval-sets/{id}/cases`; GET `/eval-sets/{id}/cases/{case_id}`; POST/GET `/experiments`; GET `/experiments/{id}`; inject `EvalSuiteService` + `AbExperimentService` via FastAPI DI
- [X] T016 [US1] Add runs and verdicts endpoints to `apps/control-plane/src/platform/evaluation/router.py` — POST `/eval-sets/{id}/run` (creates EvaluationRun, starts `EvalRunnerService.run()` as `BackgroundTask`); GET/list `/runs`; GET `/runs/{id}`; GET `/runs/{id}/verdicts`; GET `/verdicts/{id}` (includes human_grade if present)
- [X] T017 [US1] Create `apps/control-plane/src/platform/evaluation/service_interfaces.py` — `EvalSuiteServiceInterface` Protocol with `get_run_summary(run_id)` and `get_latest_agent_score(agent_fqn, eval_set_id, workspace_id)` methods
- [X] T018 [US1] Register `evaluation/router.py` in `apps/control-plane/src/platform/api/evaluations.py` (include with prefix `/api/v1/evaluations`) and add include to `apps/control-plane/src/platform/main.py`; provision MinIO buckets `evaluation-ate-evidence` and `evaluation-generated-suites` in app lifespan hook

**Checkpoint**: User Story 1 fully functional — eval sets created, runs executed, verdicts scored with semantic + exact_match + regex + json_schema scorers, A/B experiments compared

---

## Phase 4: User Story 2 — LLM-as-Judge Scorer (Priority: P1)

**Goal**: Configurable LLM-as-Judge scorer with 6 built-in rubric templates, custom rubric support, and N-trial calibration producing score distributions.

**Independent Test**: Create eval set with `llm_judge` scorer (rubric=correctness, judge_model=claude-sonnet-4-6, calibration_runs=5), run against 3 cases, verify each verdict's `scorer_results.llm_judge` has `calibration_distribution.mean/stddev/confidence_interval` and individual run scores (T04, T05 from quickstart.md).

- [X] T019 [US2] Create `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` — `RUBRIC_TEMPLATES: dict[str, dict]` with 6 built-in rubrics (correctness, helpfulness, safety, style, faithfulness_to_source, instruction_following); `LLMJudgeScorer`: validate rubric config (template or custom_criteria), build judge prompt with rubric + benchmark input/output, call model provider via httpx `calibration_runs` times sequentially, parse per-criterion scores and rationale, compute distribution with `statistics.mean()`, `statistics.stdev()`, `statistics.NormalDist` for 95% CI; flag "low_confidence" when stdev > 1.0; update `evaluation/scorers/registry.py` to register LLMJudgeScorer
- [X] T020 [US2] Add `LLMJudgeConfig`, `RubricConfig`, `RubricCriterion` Pydantic models to `apps/control-plane/src/platform/evaluation/schemas.py`; add `CalibrationDistribution` response schema (mean, stddev, confidence_interval, runs list, low_confidence flag)

**Checkpoint**: US1 + US2 both work independently — eval sets can use any combination of exact_match, regex, json_schema, semantic, and llm_judge scorers

---

## Phase 5: User Story 3 — Trajectory-Based Evaluation (Priority: P2)

**Goal**: TrajectoryScorer evaluates full execution trajectories (journal + reasoning traces + task plan) producing 5-dimensional scores.

**Independent Test**: Provide BenchmarkCase with `input_data.execution_id`, run eval set with trajectory scorer, verify verdict has `scorer_results.trajectory` with all 5 score dimensions (efficiency, tool_appropriateness, reasoning_coherence, cost_effectiveness, overall) (T06 from quickstart.md).

- [X] T021 [US3] Create `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — `TrajectoryScorer`: inject `ExecutionQueryInterface` (in-process) + `ReasoningEngineClient` (gRPC) via constructor; extract `execution_id` from `input_data`; fetch journal events + `TaskPlanRecord` via `ExecutionQueryInterface`; fetch reasoning traces via `ReasoningEngineClient`; compute `efficiency_score` = optimal_steps / actual_steps (clamped 0.0-1.0); compute `tool_appropriateness_score` from TaskPlan tool selection rationale vs actual calls; compute `cost_effectiveness_score` = quality_score / token_cost_ratio; optionally call `LLMJudgeScorer` for `reasoning_coherence_score` and holistic assessment; return `TrajectoryScore` dict; update `evaluation/scorers/registry.py` to register TrajectoryScorer
- [X] T022 [US3] Add `TrajectoryScore` Pydantic model to `apps/control-plane/src/platform/evaluation/schemas.py` — efficiency_score, tool_appropriateness_score, reasoning_coherence_score, cost_effectiveness_score, overall_trajectory_score (float fields 0.0-1.0), llm_judge_holistic (optional dict); update `EvalRunnerService` in `service.py` to pass `execution_id` from `input_data` to TrajectoryScorer

**Checkpoint**: US3 independent — trajectory scoring works on any completed agent execution available via ExecutionQueryInterface

---

## Phase 6: User Story 4 — Adversarial and Test Case Generation (Priority: P2)

**Goal**: Auto-generate adversarial test suites (6 categories) from agent config; generate positive test scenarios; store as versioned, importable artifacts.

**Independent Test**: Call `POST /api/v1/testing/suites/generate` for a registered agent; verify suite contains ≥10 cases per adversarial category; import suite into an eval set and verify benchmark cases are created (T07, T20 from quickstart.md).

- [X] T023 [US4] Create `apps/control-plane/src/platform/testing/models.py` — 4 SQLAlchemy async models: `GeneratedTestSuite` (UUIDMixin + TimestampMixin + WorkspaceScopedMixin), `AdversarialTestCase` (UUIDMixin + TimestampMixin), `CoordinationTestResult` (UUIDMixin + TimestampMixin + WorkspaceScopedMixin), `DriftAlert` (UUIDMixin + TimestampMixin + WorkspaceScopedMixin); enums: `SuiteType`, `AdversarialCategory` (6 values)
- [X] T024 [P] [US4] Create `apps/control-plane/src/platform/testing/schemas.py` — Pydantic v2 schemas for GenerateSuiteRequest, GeneratedTestSuiteResponse, AdversarialCaseResponse, CoordinationTestRequest, CoordinationTestResultResponse, DriftAlertResponse, ImportSuiteRequest
- [X] T025 [P] [US4] Create `apps/control-plane/src/platform/testing/events.py` — Kafka event helpers for `evaluation.events` topic from testing context (drift.detected event; suite.generated event)
- [X] T026 [US4] Create `apps/control-plane/src/platform/testing/repository.py` — async SQLAlchemy repository for all 4 testing models; depends on T023
- [X] T027 [US4] Create `apps/control-plane/src/platform/testing/adversarial_service.py` — `AdversarialGenerationService`: fetch agent profile via `AgentRegistryQueryInterface` (in-process); build 6 category-specific generation prompts populated with agent domain + capabilities; call model provider via httpx for each category (configurable `cases_per_category`, default 10); store `SHA-256(generation_prompt)` as `generation_prompt_hash`; persist `AdversarialTestCase` rows; handle async batch generation
- [X] T028 [US4] Create `apps/control-plane/src/platform/testing/suite_generation_service.py` — `TestSuiteGenerationService`: orchestrate adversarial + positive generation via `AdversarialGenerationService`; create `GeneratedTestSuite` record with version auto-increment per `(agent_fqn, suite_type)`; archive to MinIO `evaluation-generated-suites` bucket when `case_count > 500`; `import_to_eval_set(suite_id, eval_set_id)` method creates `BenchmarkCase` rows in target eval set for each `AdversarialTestCase`
- [X] T029 [US4] Create `apps/control-plane/src/platform/testing/router.py` — suites endpoints: POST `/suites/generate` (BackgroundTask); GET `/suites`; GET `/suites/{id}`; GET `/suites/{id}/cases?category=`; POST `/suites/{id}/import`; inject `TestSuiteGenerationService` via DI; create `apps/control-plane/src/platform/api/testing.py` include with prefix `/api/v1/testing`; add include to `main.py`

**Checkpoint**: US4 independent — adversarial suites generated, cases browsable by category, importable into eval sets

---

## Phase 7: User Story 5 — Accredited Testing Environment Integration (Priority: P2)

**Goal**: Define reusable ATE configs (scenarios + golden pairs + scorers + thresholds + safety checks); execute ATE against any agent via simulation sandbox; collect structured evidence report.

**Independent Test**: Create ATE with 3 scenarios, run against two different agents, verify both produce structured reports with per-scenario pass/fail + latency percentiles + cost breakdown; verify pre-check failure for invalid config (T08, T09 from quickstart.md).

- [X] T030 [US5] Create `apps/control-plane/src/platform/evaluation/ate_service.py` — `ATEService`: `pre_check(ate_config)` validates scenario structure and scorer config completeness; `run_ate(ate_config_id, agent_fqn)` creates ATERun (status=pending), calls `SimulationControllerClient.CreateSimulation()` via gRPC (from `common/clients/simulation_controller.py`), polls simulation completion, collects per-scenario outputs, runs scorers via `EvalRunnerService`, computes performance metrics (latency percentiles, cost breakdown), validates safety checks, writes MinIO evidence JSON to `evaluation-ate-evidence/{run_id}/evidence.json`, compiles and stores structured report in `ATERun.report`; emits `evaluation.ate.run.completed` or `evaluation.ate.run.failed` Kafka event
- [X] T031 [US5] Add ATE endpoints to `apps/control-plane/src/platform/evaluation/router.py` — POST `/ate`; GET `/ate`; GET `/ate/{id}`; PATCH `/ate/{id}`; POST `/ate/{id}/run/{agent_fqn}` (BackgroundTask); GET `/ate/{id}/results` (all ATERun rows for this config — enables cross-agent comparison); GET `/ate/runs/{run_id}`; inject ATEService via DI

**Checkpoint**: US5 independent — ATEs created, executed via simulation, evidence stored, reports comparable across agents

---

## Phase 8: User Story 6 — Statistical Robustness and Drift Detection (Priority: P3)

**Goal**: Run same evaluation N times to produce statistical distribution; track drift via ClickHouse time-series; alert on >2 stddev deviation from baseline; suppress alerts during active robustness tests.

**Independent Test**: Run robustness test for 20 trials, verify distribution has mean/stddev/p5-p95; inject score deviation >2 stddev in ClickHouse, verify drift alert created within scanner interval; verify no alert when robustness test is active (T10-T13 from quickstart.md).

- [X] T032 [US6] Create `apps/control-plane/src/platform/evaluation/robustness_service.py` — `RobustnessTestService`: create `RobustnessTestRun`, spawn `trial_count` `EvaluationRun` instances sequentially via `EvalRunnerService`, collect `aggregate_score` per trial, compute distribution using `statistics.mean()`, `statistics.stdev()`, `statistics.quantiles(data, n=20)` for p5/p25/p50/p75/p95, flag `is_unreliable = stdev > variance_threshold`, persist distribution to `RobustnessTestRun.distribution`, emit `evaluation.robustness.completed`
- [X] T033 [US6] Add robustness endpoints to `apps/control-plane/src/platform/evaluation/router.py` — POST `/robustness-runs` (BackgroundTask); GET `/robustness-runs/{id}`
- [X] T034 [US6] Create `apps/control-plane/src/platform/testing/drift_service.py` — `DriftDetectionService`: `record_eval_metric(run_id, agent_fqn, eval_set_id, score)` writes row to ClickHouse `testing_drift_metrics` table via `ClickHouseClient` (on startup provision table from `testing/clickhouse_schema.sql`); `detect_drift(agent_fqn, eval_set_id, workspace_id)` queries ClickHouse `SELECT avg(score), stddevPop(score) FROM testing_drift_metrics WHERE ... AND measured_at > now() - INTERVAL 30 DAY`, compares current score vs `mean - threshold * stddev` (default threshold=2.0), creates `DriftAlert` + emits `evaluation.drift.detected`; `should_suppress(agent_fqn)` returns True if active `RobustnessTestRun` exists for agent
- [X] T035 [US6] Add drift-alerts endpoints to `apps/control-plane/src/platform/testing/router.py` — GET `/drift-alerts?agent_fqn=&acknowledged=false`; PATCH `/drift-alerts/{id}/acknowledge`; register APScheduler daily drift scanner job in `DriftDetectionService` for `agentops-testing` runtime profile; call `DriftDetectionService.record_eval_metric()` from `EvalRunnerService` after each completed run

**Checkpoint**: US6 independent — robustness distributions computed, drift alerts firing on ClickHouse deviation, suppressed during robustness tests

---

## Phase 9: User Story 7 — Multi-Agent Coordination Testing (Priority: P3)

**Goal**: Evaluate fleet-level coordination quality (completion, communication coherence, goal achievement) from fleet execution data; produce per-agent and fleet-level scores.

**Independent Test**: Provide fleet execution with 3 agents, run coordination evaluator, verify fleet-level and per-agent scores; run with 1-agent fleet, verify insufficient_members=true (T14, T15 from quickstart.md).

- [X] T036 [US7] Create `apps/control-plane/src/platform/testing/coordination_service.py` — `CoordinationTestService`: fetch fleet members via `FleetQueryInterface`; set `insufficient_members=True` if member count < 2; fetch per-agent execution journals via `ExecutionQueryInterface`; compute `completion_score` = completed_subtasks / total_subtasks (from journal events); compute `coherence_score` = non_redundant_messages / total_messages (from agent communication events in journal); compute `goal_achievement_score` via LLM-as-judge holistic assessment of collective output; compute `overall_score` as weighted average; persist `CoordinationTestResult`; emit `evaluation.events`; create `apps/control-plane/src/platform/testing/service_interfaces.py` with `CoordinationTestServiceInterface` Protocol
- [X] T037 [US7] Add coordination-tests endpoints to `apps/control-plane/src/platform/testing/router.py` — POST `/coordination-tests` (BackgroundTask); GET `/coordination-tests/{id}`; export `CoordinationTestServiceInterface` via FastAPI DI for `fleets/` bounded context consumption

**Checkpoint**: US7 independent — fleet coordination scored, per-agent breakdowns visible, insufficient_members edge case handled

---

## Phase 10: User Story 8 — Human-AI Collaborative Grading (Priority: P3)

**Goal**: Human reviewers can confirm or override automated scores; original score snapshotted; audit trail stored; review progress tracked per run.

**Independent Test**: Confirm one verdict (decision=confirmed), override another (decision=overridden, override_score=0.3, feedback), verify review progress shows reviewed=1/overridden=1, verify audit trail on verdict response (T16-T18 from quickstart.md).

- [X] T038 [US8] Create `apps/control-plane/src/platform/evaluation/human_grading_service.py` — `HumanGradingService`: `submit_grade(verdict_id, reviewer_id, decision, override_score, feedback)` snaps `original_score = verdict.overall_score`, creates `HumanAiGrade` (unique constraint: one per verdict), validates `override_score` required when `decision=overridden`; `update_grade(grade_id, override_score, feedback)` for corrections; `get_review_progress(run_id)` aggregates pending/reviewed/overridden counts; emit `evaluation.human.grade.submitted`
- [X] T039 [US8] Add human grading endpoints to `apps/control-plane/src/platform/evaluation/router.py` — GET `/runs/{run_id}/review-progress`; GET `/verdicts/{verdict_id}/grade`; POST `/verdicts/{verdict_id}/grade`; PATCH `/grades/{grade_id}`; RBAC check: require `evaluator` role or workspace admin; inject `HumanGradingService` via DI; update `JudgeVerdictResponse` schema to include nested `human_grade` field via `evaluation/schemas.py`

**Checkpoint**: All 8 user stories complete and independently testable

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Wire runtime profiles, observability, DI exports, test coverage

- [X] T040 [P] Wire `EvalSuiteServiceInterface` into FastAPI DI in `apps/control-plane/src/platform/common/dependencies.py` — provide bound `EvalSuiteServiceInterface` implementation for consumption by `analytics/` and `notifications/` contexts; similarly wire `CoordinationTestServiceInterface` from `testing/service_interfaces.py` for `fleets/` consumption
- [X] T041 [P] Add OpenTelemetry spans to all service methods in `apps/control-plane/src/platform/evaluation/` — `service.py` (EvalSuiteService + EvalRunnerService), `ate_service.py`, `robustness_service.py`, `ab_experiment_service.py`, `human_grading_service.py`; use `opentelemetry.trace.get_tracer(__name__)` with span names following `evaluation.<service>.<method>` convention
- [X] T042 [P] Add OpenTelemetry spans to all service methods in `apps/control-plane/src/platform/testing/` — `adversarial_service.py`, `suite_generation_service.py`, `drift_service.py`, `coordination_service.py`; follow `testing.<service>.<method>` naming convention
- [X] T043 Register APScheduler jobs for `agentops-testing` runtime profile in `apps/control-plane/entrypoints/agentops_testing_main.py` — daily drift scanner (calls `DriftDetectionService.run_drift_scan_all()` for all active agent+eval_set pairs); robustness orchestrator (polls pending RobustnessTestRun records and advances trials)
- [X] T044 Test coverage sweep: run `pytest --cov=platform/evaluation --cov=platform/testing --cov-report=term-missing` in `apps/control-plane/`; add missing unit/integration tests to reach ≥95% coverage (SC-011); run `ruff check apps/control-plane/src/platform/evaluation/ apps/control-plane/src/platform/testing/` and `mypy --strict` across both contexts; fix all violations

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — no other story dependencies; first two scorers are in foundational
- **US2 (Phase 4)**: Depends on Foundational + US1 scorer infrastructure (ScorerRegistry)
- **US3 (Phase 5)**: Depends on Foundational + US2 (TrajectoryScorer optionally calls LLMJudgeScorer)
- **US4 (Phase 6)**: Depends on Foundational only — independent of US1/US2/US3
- **US5 (Phase 7)**: Depends on Foundational + US1 (EvalRunnerService used by ATEService)
- **US6 (Phase 8)**: Depends on Foundational + US1 (EvalRunnerService used by RobustnessTestService)
- **US7 (Phase 9)**: Depends on Foundational only — independent of other stories
- **US8 (Phase 10)**: Depends on Foundational + US1 (requires JudgeVerdict rows from evaluation runs)
- **Polish (Phase 11)**: Depends on all user stories

### User Story Dependencies (Summary)

```
Foundational ──► US1 (P1) ──► US2 (P1) ──► US3 (P2)
            │            └──► US5 (P2)
            │            └──► US6 (P3)
            │            └──► US8 (P3)
            └──► US4 (P2)
            └──► US7 (P3)
```

- **US1** and **US4** and **US7** can begin after foundational independently
- **US2** and **US3** require US1 scorer infrastructure
- **US5**, **US6**, **US8** require US1 evaluation run infrastructure
- **US2** and **US5** (both P1/P2) can work concurrently once US1 is done

### Within Each Phase: Execution Order

- [P]-marked tasks: run in parallel (different files, no cross-dependencies)
- Non-[P] tasks: run sequentially after their listed dependencies
- Services before routers; models before repositories; base before implementations

### Parallel Opportunities Per Story

```bash
# Phase 2 Foundational — parallel batch:
Task: "T003 evaluation/models.py"
Task: "T004 evaluation/schemas.py"
Task: "T005 evaluation/events.py"
Task: "T007 evaluation/scorers/base.py"
Task: "T008 evaluation/scorers/exact_match.py"
Task: "T009 evaluation/scorers/regex.py"
Task: "T010 evaluation/scorers/json_schema.py"
# Then T006 (needs T003), T011 (needs T007-T010)

# Phase 6 US4 — parallel batch:
Task: "T024 testing/schemas.py"
Task: "T025 testing/events.py"
# Then T023 first, T026 (needs T023), T027-T029 sequential
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (eval suites, scorers, runs, verdicts, A/B)
4. **STOP and VALIDATE**: Run T01-T03 quickstart scenarios
5. Full eval pipeline working with semantic + exact_match + regex + json_schema scorers

### Incremental Delivery

1. Setup + Foundational → scorer infrastructure ready
2. US1 → eval pipeline MVP (semantic similarity + basic scorers + A/B)
3. US2 → LLM-as-Judge with calibration
4. US4 → adversarial test generation
5. US5 → certification-grade ATE runs
6. US3 → trajectory scoring
7. US6 → robustness + drift detection
8. US7 → fleet coordination testing
9. US8 → human grading workflow

### Parallel Team Strategy

With multiple developers after Foundational completes:

- **Developer A**: US1 + US2 (P1 priority chain)
- **Developer B**: US4 (independent test generation, no dependency on US1 services)
- **Developer C**: US5 (depends on US1 — coordinate with Developer A)

---

## Notes

- [P] tasks write to different files — safe to run concurrently
- [Story] label maps each task to its user story for traceability (US1-US8)
- `evaluation/` context manages the eval lifecycle; `testing/` context handles test generation and observability
- Scorers are pluggable — added by creating a new scorer file + registering in `evaluation/scorers/registry.py`
- All new bounded context code runs under `api` (REST) + `agentops-testing` (APScheduler/background) runtime profiles
- ClickHouse table provisioned at `DriftDetectionService` startup (idempotent CREATE TABLE IF NOT EXISTS)
- Qdrant collection provisioned at `SemanticSimilarityScorer` startup (idempotent create_collection)
- MinIO buckets provisioned in app lifespan hook (idempotent make_bucket with exists_ok)
