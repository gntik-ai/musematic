# Tasks: Trajectory Evaluation and LLM-as-Judge Formalization

**Input**: Design documents from `specs/067-trajectory-judge-evaluation/`  
**Branch**: `067-trajectory-judge-evaluation`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

**Key context**: Both `trajectory.py` and `llm_judge.py` already exist and are registered. This feature extends them and adds persistence (Rubric entity, CalibrationRun entity), YAML templates, and new endpoints.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Config settings and database migration. These two tasks block all user story work.

- [x] T001 Add `EvaluationSettings` class to `apps/control-plane/src/platform/common/config.py` — fields: `EVALUATION_LLM_JUDGE_API_URL`, `EVALUATION_LLM_JUDGE_MODEL`, `EVALUATION_LLM_JUDGE_TIMEOUT_SECONDS=30`, `EVALUATION_LLM_JUDGE_MAX_RETRIES=2`, `EVALUATION_TRAJECTORY_MAX_STEPS=10000`, `EVALUATION_CALIBRATION_VARIANCE_ENVELOPE=0.2`; add `evaluation: EvaluationSettings` to `PlatformSettings`
- [x] T002 Create Alembic migration `apps/control-plane/migrations/versions/054_trajectory_evaluation_schema.py` — `down_revision="053_mcp_integration"`; creates `rubric_status` enum (`active`, `archived`), `calibration_run_status` enum (`pending`, `running`, `completed`, `failed`), `evaluation_rubrics` table (id UUID pk, workspace_id FK nullable, name text, description text, criteria JSONB, version int default 1, is_builtin bool default false, status rubric_status default active, created_by UUID nullable, deleted_at timestamptz, created_at, updated_at), `evaluation_calibration_runs` table (id UUID pk, rubric_id FK `evaluation_rubrics.id` RESTRICT, rubric_version int, judge_model text, reference_set_id text, status calibration_run_status default pending, distribution JSONB nullable, agreement_rate float nullable, calibrated bool nullable, error_grade_finding bool default false, started_at, completed_at nullable, created_by UUID nullable, created_at); add indexes on workspace_id, status, is_builtin, and unique index on name WHERE is_builtin=true

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared SQLAlchemy models, Pydantic schemas, repository methods, and Kafka events that all user stories depend on.

**⚠️ CRITICAL**: All four tasks here must complete before any user story phase can begin.

- [x] T003 [P] Add `RubricStatus` enum, `CalibrationRunStatus` enum, `Rubric` SQLAlchemy model, and `CalibrationRun` SQLAlchemy model to `apps/control-plane/src/platform/evaluation/models.py` — `Rubric`: mapped to `evaluation_rubrics`, inherits `Base, UUIDMixin, TimestampMixin, SoftDeleteMixin`; `CalibrationRun`: mapped to `evaluation_calibration_runs`, inherits `Base, UUIDMixin, TimestampMixin`; add relationships `Rubric.calibration_runs` → `CalibrationRun` list
- [x] T004 [P] Add Pydantic request/response schemas to `apps/control-plane/src/platform/evaluation/schemas.py` — `CriterionDefinition`, `RubricCreate`, `RubricUpdate`, `RubricResponse`, `RubricListResponse`, `CalibrationRunCreate`, `CalibrationRunResponse`, `CalibrationReport` (overall + per_criterion distribution), `AdHocJudgeRequest` (rubric_id OR inline rubric, output, judge_model), `AdHocJudgeResponse` (per_criterion_scores, overall_score, aggregation_method, rationale, rubric_version, principal_id, timestamp, duration_ms), `ScorerTypeInfo`, `ScorerListResponse`, `RubricTemplateSummary`, `RubricTemplateListResponse`
- [x] T005 Add rubric and calibration run repository methods to `apps/control-plane/src/platform/evaluation/repository.py` — `create_rubric`, `get_rubric`, `list_rubrics`, `update_rubric`, `soft_delete_rubric`, `get_builtin_rubric_by_name`, `count_inFlight_runs_for_rubric` (JSONB containment query on `evaluation_runs.scorer_config @> '{"llm_judge":{"rubric_id":"..."}}'` WHERE `status='running'`), `create_calibration_run`, `get_calibration_run`, `update_calibration_run`
- [x] T006 [P] Add 6 new Kafka event types to `apps/control-plane/src/platform/evaluation/events.py` — `RubricCreatedPayload`, `RubricUpdatedPayload`, `RubricArchivedPayload`, `CalibrationStartedPayload`, `CalibrationCompletedPayload`, `AdHocJudgePayload`; register event types `evaluation.rubric.created`, `evaluation.rubric.updated`, `evaluation.rubric.archived`, `evaluation.calibration.started`, `evaluation.calibration.completed`, `evaluation.judge.adhoc` with `EventEnvelope`

**Checkpoint**: Foundation complete — migration applied, models importable, schemas defined, repository methods available. User story phases can now proceed.

---

## Phase 3: User Story 1 — Trajectory Scoring (Priority: P1) 🎯 MVP

**Goal**: Trajectory scorer returns a comparison score (one of 5 methods) plus 4 dimension scores for any agent execution. Handles edge cases: empty trajectory, oversized trajectory, missing cost data.

**Independent Test**: Author an expected trajectory with 3 tool calls. Run with `exact` → score 1.0. Run same tools reordered → `exact` score < 1.0. Run with `any_order` → score 1.0. Verify all 4 dimension scores returned. (Scenarios S1–S4, S19–S21)

- [x] T007 [US1] Add `_compare(actual_steps, expected_steps, method: Literal["exact","in_order","any_order","precision","recall"]) -> float` static method to `TrajectoryScorer` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — `exact`: full-sequence alignment score; `in_order`: LCS-based score allowing gaps; `any_order`: Jaccard/set membership score; `precision`: len(actual ∩ expected) / len(actual); `recall`: len(actual ∩ expected) / len(expected); called from `score()` based on `config.get("comparison_method", "any_order")`; zero-division returns 0.0 for empty actual/expected
- [x] T008 [US1] Extend `TrajectoryScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` to handle empty trajectories (zero actions) — for empty trajectory: comparison_score=0.0 with annotation, dimension scores=null with explicit "unscored" annotations; raise no exception (FR-003, S20)
- [x] T009 [US1] Add trajectory truncation to `TrajectoryScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — read `settings.evaluation.EVALUATION_TRAJECTORY_MAX_STEPS` (default 10000); if step count exceeds limit, truncate steps list for scoring; set `ScoreResult.extra["truncated"]=True`, `extra["original_step_count"]=N` (FR-025, SC-014, S19)
- [x] T010 [US1] Add missing cost data handling to `TrajectoryScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — when `accumulated_costs` absent or empty from execution checkpoint: set cost_effectiveness dimension=null, set `extra["cost_effectiveness_unscored"]=True`; exclude from overall_score aggregation rather than substituting zero (FR-026, SC-003, S21)

**Checkpoint**: TrajectoryScorer handles all 5 comparison methods, empty trajectories, truncation, and missing cost data. Can be tested independently via existing eval set + execution fixture.

---

## Phase 4: User Story 2 — LLM-as-Judge Rubric Scoring (Priority: P1)

**Goal**: Rubrics are first-class DB entities with versioning and lifecycle. LLMJudgeScorer accepts a `rubric_id` for DB lookup. Verdicts are immutable with full audit trail. Out-of-scale clamping and malformed-verdict classification work correctly.

**Independent Test**: Create a rubric via POST /rubrics. Run an evaluation referencing `rubric_id`. Inspect verdict — verify rubric_version, judge_model, principal_id, timestamp all present. Attempt DELETE while run is in-flight → 409. (Scenarios S5–S7, S12–S14, S22–S24)

- [x] T011 [P] [US2] Add `rubric_id: UUID | None` parameter support to `LLMJudgeScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` — when `config["rubric_id"]` present, look up rubric via injected `rubric_service.get_rubric(rubric_id)`; record `rubric_version` from DB record into `ScoreResult.extra`; fall back to inline `config["rubric"]` if no rubric_id (existing path, unchanged — FR-020)
- [x] T012 [P] [US2] Add out-of-scale clamping to `LLMJudgeScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` — after parsing per-criterion judge scores: clamp each score to `[criterion.scale_min, criterion.scale_max]`; when clamped, set `extra["out_of_range_clamped"][criterion_name]={"original": raw, "clamped": clamped}`; retain raw judge output in `extra["raw_judge_output"]` (FR-011, SC-004, S22)
- [x] T013 [US2] Add malformed verdict retry logic to `LLMJudgeScorer.score()` in `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` — wrap API call + parse in try/except; classify exception as transient (httpx.TimeoutException, 5xx) or permanent (json parse error, schema mismatch); for transient: retry up to `settings.evaluation.EVALUATION_LLM_JUDGE_MAX_RETRIES` times with exponential back-off; after retries exhausted: set `ScoreResult.error="judge_failure_permanent"` or `"judge_failure_transient"`, set `extra["failure_classification"]`; do NOT record a synthetic score (FR-012, S23)
- [x] T014 [US2] Add `RubricService` class to `apps/control-plane/src/platform/evaluation/service.py` — methods: `create_rubric(payload, workspace_id, actor_id)` (validates contradictory examples, raises `RubricValidationError`), `get_rubric(rubric_id, workspace_id)`, `list_rubrics(*, workspace_id, status, include_builtins, page, page_size)`, `update_rubric(rubric_id, payload, actor_id)` (increments version, rejects builtin update, raises `RubricInFlightError` if criteria changed while runs are running), `archive_rubric(rubric_id, actor_id)` (raises `RubricInFlightError` on 409 condition from FR-024), `get_builtin_by_name(name)`; publishes `evaluation.rubric.*` Kafka events
- [x] T015 [US2] Add rubric CRUD exceptions to `apps/control-plane/src/platform/evaluation/service.py` (or a new `apps/control-plane/src/platform/evaluation/exceptions.py` if not already existing) — `RubricNotFoundError`, `RubricValidationError` (contradictory examples), `RubricInFlightError` (deletion blocked), `RubricBuiltinProtectedError` (cannot modify builtins), `CalibrationRunImmutableError`
- [x] T016 [US2] Add rubric CRUD routes to `apps/control-plane/src/platform/evaluation/router.py` — `POST /rubrics` → 201, `GET /rubrics` → paginated list, `GET /rubrics/{rubric_id}` → 200, `PATCH /rubrics/{rubric_id}` → 200 + incremented version, `DELETE /rubrics/{rubric_id}` → 204 (or 409 if in-flight); map `RubricNotFoundError` → 404, `RubricInFlightError` → 409, `RubricBuiltinProtectedError` → 403, `RubricValidationError` → 400
- [x] T017 [US2] Add `judge_adhoc(payload: AdHocJudgeRequest, actor_id: UUID) -> AdHocJudgeResponse` to `EvalRunnerService` in `apps/control-plane/src/platform/evaluation/service.py` — resolves rubric from `payload.rubric_id` or inline `payload.rubric`; calls `LLMJudgeScorer.score()`; publishes `evaluation.judge.adhoc` event; returns `AdHocJudgeResponse` with all audit fields; raises `JudgeUnavailableError` on 503
- [x] T018 [US2] Add `POST /judge` ad-hoc route to `apps/control-plane/src/platform/evaluation/router.py` — delegates to `eval_runner_service.judge_adhoc()`; same auth dependency as `POST /eval-sets/{id}/run`; map `JudgeUnavailableError` → 503, rate limit → 429 (reuse existing rate-limit dep if available)
- [x] T019 [US2] Expose `RubricService` dependency in `apps/control-plane/src/platform/evaluation/dependencies.py` — add `build_rubric_service(*, session, settings, producer)` factory; add `get_rubric_service` FastAPI dependency function that reads from `app.state`; inject `rubric_service` into `build_eval_runner_service` so `EvalRunnerService` and `LLMJudgeScorer` can call it

**Checkpoint**: Rubric CRUD API fully functional. LLMJudgeScorer accepts rubric_id. Verdicts include rubric_version. Archival and deletion guards work correctly.

---

## Phase 5: User Story 3 — Pre-existing Scorer No-Regression (Priority: P1)

**Goal**: All 6 scorer types enumeratable. Pre-existing 4 scorer types produce byte-identical results. No code paths from new features reach `exact_match.py`, `regex.py`, `json_schema.py`, or `semantic.py`.

**Independent Test**: Call `GET /api/v1/evaluation/scorers` — verify exactly 6 types listed with correct names in sorted order. Run a pre-existing evaluation set (exact_match + semantic) before and after — verify byte-identical scores. (Scenario S15–S16)

- [x] T020 [US3] Add `GET /api/v1/evaluation/scorers` route to `apps/control-plane/src/platform/evaluation/router.py` — returns `ScorerListResponse` built from `scorer_registry.registered_types()` (in-memory, no DB); maps each registered type to a `ScorerTypeInfo(type, category, description)`; categories: exact_match/regex/json_schema → "deterministic", semantic → "semantic", trajectory → "trajectory", llm_judge → "judge"; no auth required (FR-019, SC-012, S16)

**Checkpoint**: Scorer enumeration endpoint live. Pre-existing scorer files confirmed untouched (no diff in exact_match.py, regex.py, json_schema.py, semantic.py).

---

## Phase 6: User Story 4 — Rubric Calibration (Priority: P2)

**Goal**: Quality engineer can trigger a calibration run, poll for completion, and receive an immutable report with distribution statistics and low-discrimination flags.

**Independent Test**: Create a rubric. POST /rubrics/{id}/calibrate with reference_set_id. Poll GET /calibration-runs/{id} until status=completed. Verify distribution.overall.* present, per_criterion.*.low_discrimination present. Run same calibration twice — verify statistics within CALIBRATION_VARIANCE_ENVELOPE. (Scenarios S8–S9, S25)

- [x] T021 [P] [US4] Add `CalibrationService` class to `apps/control-plane/src/platform/evaluation/service.py` — methods: `start_calibration(rubric_id, payload, actor_id)` (creates CalibrationRun record in "pending" status, publishes `evaluation.calibration.started`), `get_calibration_run(run_id)`, `run_calibration_background(run_id)` (called via BackgroundTasks: loads reference set from eval fixture, runs LLMJudgeScorer N times, computes CalibrationReport, checks error-grade condition per FR-015, sets `calibrated`, updates run to "completed", publishes `evaluation.calibration.completed`); enforces immutability by raising `CalibrationRunImmutableError` if `completed_at` is already set on any update attempt
- [x] T022 [US4] Add distribution statistics computation to `CalibrationService.run_calibration_background()` in `apps/control-plane/src/platform/evaluation/service.py` — for each criterion: compute min, max, mean, stddev, histogram (bucket by integer scale point), `low_discrimination` flag (when all verdicts cluster within ±0.5 of mean and range < 1.0); overall statistics across all criteria; agreement_rate (fraction of verdicts within reference score ranges); `low_confidence` flag when `stddev > settings.evaluation.EVALUATION_CALIBRATION_VARIANCE_ENVELOPE`; error-grade finding when judge disagrees with ALL reference labels (FR-015, SC-006–SC-007)
- [x] T023 [US4] Add calibration routes to `apps/control-plane/src/platform/evaluation/router.py` — `POST /rubrics/{rubric_id}/calibrate` → 202 with CalibrationRunResponse (async via BackgroundTasks); `GET /calibration-runs/{run_id}` → 200 CalibrationRunResponse; map `RubricNotFoundError` → 404, archived rubric → 409
- [x] T024 [US4] Expose `CalibrationService` dependency in `apps/control-plane/src/platform/evaluation/dependencies.py` — add `build_calibration_service(*, session, settings, producer, scorer_registry)` factory; add `get_calibration_service` FastAPI dependency
- [x] T025 [US4] Add `RubricNotFoundError` guard for archived rubric on calibration start to `CalibrationService.start_calibration()` in `apps/control-plane/src/platform/evaluation/service.py` — if `rubric.status == RubricStatus.archived` → raise `RubricArchivedError` (HTTP 409)

**Checkpoint**: Calibration runs can be triggered, persisted, and retrieved with full distribution report. Immutability enforced.

---

## Phase 7: User Story 5 — Built-in Rubric Templates (Priority: P2)

**Goal**: Six built-in rubric templates available at feature launch, loaded from YAML files, accessible via API, copy-able as custom rubrics.

**Independent Test**: GET /rubric-templates → exactly 6 items. GET /rubric-templates/correctness → full criteria. Run an evaluation referencing correctness template rubric_id → verdicts produced without modification. (Scenarios S10–S11)

- [x] T026 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/correctness.yaml` — criteria: `factual_accuracy` (scale 1–5, examples at 1/3/5) and `completeness` (scale 1–5, examples at 1/3/5)
- [x] T027 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/helpfulness.yaml` — criteria: `relevance` (scale 1–5), `actionability` (scale 1–5), `clarity` (scale 1–5); each with examples at min/mid/max
- [x] T028 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/safety.yaml` — criteria: `harm_avoidance` (scale 1–5), `appropriate_refusal` (scale 1–5); examples for safe/borderline/harmful outputs at each scale point
- [x] T029 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/style.yaml` — criteria: `tone_appropriateness` (scale 1–5), `conciseness` (scale 1–5), `formatting` (scale 1–5); examples reflecting poor/acceptable/excellent style
- [x] T030 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/faithfulness.yaml` — criteria: `source_consistency` (scale 1–5), `hallucination_absence` (scale 1–5); examples for faithful/partially-faithful/unfaithful outputs; include metadata note about source document requirement at scoring time
- [x] T031 [P] [US5] Create `apps/control-plane/src/platform/evaluation/rubrics/instruction_following.yaml` — criteria: `instruction_compliance` (scale 1–5), `constraint_adherence` (scale 1–5); examples for full/partial/no compliance
- [x] T032 [US5] Create `apps/control-plane/src/platform/evaluation/rubric_templates.py` — `RubricTemplateLoader` class with `load_templates(rubric_service: RubricService)` async method: scans `evaluation/rubrics/*.yaml` directory, parses each YAML file, upserts via `rubric_service` as `is_builtin=True` records; idempotent (upsert by name); raises `TemplateLoadError` on YAML parse failure; logs count on completion
- [x] T033 [US5] Add template loading to application startup in `apps/control-plane/src/platform/evaluation/dependencies.py` — call `RubricTemplateLoader().load_templates(rubric_service)` inside `build_eval_runner_service` startup or equivalent lifespan hook; ensure it runs after DB migration applied
- [x] T034 [US5] Add template discovery routes to `apps/control-plane/src/platform/evaluation/router.py` — `GET /rubric-templates` → `RubricTemplateListResponse` (list of `RubricTemplateSummary` with name, description, criteria_count, rubric_id); `GET /rubric-templates/{template_name}` → full `RubricResponse`; sources from `rubric_service.list_rubrics(include_builtins=True, status=active, workspace_id=None)` filtered to `is_builtin=True`; 404 if template_name not found

**Checkpoint**: All 6 templates loadable from YAML, stored as builtin DB records, accessible via API. Copying works by POST /rubrics with copied criteria (standard create flow).

---

## Phase 8: User Story 6 — Multi-Agent Cooperation Scoring (Priority: P3)

**Goal**: Fleet operator can score cooperation across 2+ agent trajectories in the same workflow — returns per-agent scores plus cooperation dimensions (coordination overhead, hand-off timeliness, redundancy, joint path efficiency) with cycle detection.

**Independent Test**: Two-agent workflow execution. Run cooperation mode. Verify per_agent_scores for both agents + cooperation_scores dict present. Run cyclic workflow (A→B→A without progress) — verify cycle_flags non-empty and coordination_overhead lower. (Scenarios S17–S18)

- [x] T035 [US6] Add `score_cooperation(agent_execution_ids: list[UUID], config: dict[str, Any]) -> CooperationScoreResult` async method to `TrajectoryScorer` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — loads trajectory events for each agent_execution_id; computes per-agent scores via existing `score()` method; aggregates `CooperationScoreResult(per_agent_scores, coordination_overhead, handoff_timeliness, redundancy, joint_path_efficiency, cycle_flags)`; raises `CooperationModeTooFewAgentsError` if fewer than 2 execution IDs provided (FR-005)
- [x] T036 [US6] Add coordination cycle detection to `score_cooperation()` in `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — build directed handoff graph from `ExecutionEvent` records with `event_type=handoff`; detect cycles via DFS (back-edge detection); for each detected cycle: add to `cycle_flags` list with participating agent FQNs and timestamp window; penalise `coordination_overhead` score proportionally to number of cycles (FR-028, S18)
- [x] T037 [US6] Wire cooperation mode into the evaluation pipeline in `apps/control-plane/src/platform/evaluation/service.py` — in `EvalRunnerService.score_outputs()`: detect `config["trajectory"]["cooperation_mode"] == True`; extract `config["trajectory"]["agent_execution_ids"]` list; call `trajectory_scorer.score_cooperation(agent_execution_ids, config)` instead of `score()`; store `CooperationScoreResult` in `JudgeVerdict.scorer_results["trajectory"]`

**Checkpoint**: Cooperation mode accessible via standard evaluation pipeline by setting `cooperation_mode: true` in trajectory scorer config.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Observability, integration wiring, and end-to-end validation.

- [x] T038 Add invocation observability logging to `apps/control-plane/src/platform/evaluation/scorers/trajectory.py` — at start of `score()` and `score_cooperation()`: log `principal` (from config), `scorer_type="trajectory"`, `execution_id`, `comparison_method`; at end: log `duration_ms`, `outcome` ("success" / "failure"), `truncated` flag; use structlog or platform logger pattern (FR-023, SC-001)
- [x] T039 Add invocation observability logging to `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` — log `principal`, `scorer_type="llm_judge"`, `rubric_id` (if applicable), `rubric_version`, `judge_model`, `duration_ms`, `outcome` (success / transient_failure / permanent_failure); log each retry attempt with attempt number (FR-023, SC-004)
- [x] T040 Verify that `apps/control-plane/src/platform/evaluation/scorers/exact_match.py`, `regex.py`, `json_schema.py`, and `semantic.py` have zero modifications since last commit — run `git diff HEAD -- apps/control-plane/src/platform/evaluation/scorers/exact_match.py apps/control-plane/src/platform/evaluation/scorers/regex.py apps/control-plane/src/platform/evaluation/scorers/json_schema.py apps/control-plane/src/platform/evaluation/scorers/semantic.py`; if any diff found, investigate and revert; this is the byte-identity gate (FR-020, SC-010)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T001 and T002 are independent [P]
- **Phase 2 (Foundational)**: Depends on T002 (migration) for models; T003–T006 can run in parallel after T001 completes
- **Phase 3 (US1)**: Depends on Phase 2 completion; T007–T010 can run in parallel
- **Phase 4 (US2)**: Depends on Phase 2 completion; T011–T013 can run in parallel; T014 before T016/T017; T019 before endpoints are wired
- **Phase 5 (US3)**: Depends on Phase 2 completion; T020 is a single standalone route task
- **Phase 6 (US4)**: Depends on Phase 4 completion (CalibrationService calls RubricService); T021–T022 can run in parallel
- **Phase 7 (US5)**: Depends on Phase 4 completion (templates use RubricService); T026–T031 all parallel; T032 after T001; T033 after T032; T034 after T033
- **Phase 8 (US6)**: Depends on Phase 3 completion (cooperation extends trajectory.py); T035–T036 can run in parallel
- **Phase 9 (Polish)**: Depends on all above phases; T038–T039 parallel; T040 independent gate

### User Story Dependencies

| Story | Phase | Depends On | Blocks |
|---|---|---|---|
| US1 Trajectory | Phase 3 | Foundation (Phase 2) | US6 (cooperation extends US1) |
| US2 LLM Judge | Phase 4 | Foundation (Phase 2) | US4 (CalibrationService calls RubricService), US5 (templates use RubricService) |
| US3 No-regression | Phase 5 | Foundation (Phase 2) | Nothing |
| US4 Calibration | Phase 6 | US2 (Phase 4) | Nothing |
| US5 Templates | Phase 7 | US2 (Phase 4) | Nothing |
| US6 Cooperation | Phase 8 | US1 (Phase 3) | Nothing |

### Parallel Opportunities Within Phases

**Phase 2 (Foundational)**:
```
T003 Add Rubric/CalibrationRun models
T004 Add Pydantic schemas            } all parallel
T006 Add Kafka event types
T005 Add repository methods          → after T003
```

**Phase 3 (US1 — Trajectory)**:
```
T007 _compare() dispatch
T008 Empty trajectory handling  } all parallel (same file but different methods)
T009 Truncation
T010 Missing cost data
```

**Phase 4 (US2 — LLM Judge)**:
```
T011 rubric_id lookup in llm_judge.py
T012 out-of-scale clamping             } parallel
T013 retry + classification
T014 RubricService → T016 routes → T018 ad-hoc route (sequential)
T015 exceptions                        } parallel with T014
T019 dependencies wiring               → after T014
```

**Phase 7 (US5 — Templates)**:
```
T026 correctness.yaml
T027 helpfulness.yaml
T028 safety.yaml        } all parallel
T029 style.yaml
T030 faithfulness.yaml
T031 instruction_following.yaml
T032 RubricTemplateLoader → T033 startup wiring → T034 routes (sequential)
```

---

## Parallel Example: Phase 2

```bash
# All foundational tasks can run simultaneously:
Task: "Add Rubric + CalibrationRun models to models.py"           # T003
Task: "Add Pydantic schemas to schemas.py"                        # T004
Task: "Add 6 Kafka event types to events.py"                      # T006
# Then:
Task: "Add repository methods to repository.py"                   # T005 (after T003)
```

---

## Implementation Strategy

### MVP (P1 User Stories: US1 + US2 + US3)

1. Complete Phase 1 (Setup) — T001, T002
2. Complete Phase 2 (Foundation) — T003–T006
3. Complete Phase 3 (US1 Trajectory) — T007–T010
4. Complete Phase 4 (US2 LLM Judge) — T011–T019
5. Complete Phase 5 (US3 No-regression gate) — T020
6. **STOP AND VALIDATE**: GET /scorers returns 6 types; trajectory scorer 5 methods work; rubric CRUD works; ad-hoc judge returns verdict
7. Deploy MVP

### Incremental Delivery After MVP

1. Add Calibration (US4, Phase 6) — T021–T025 → calibration runs persisted and retrievable
2. Add Templates (US5, Phase 7) — T026–T034 → 6 built-in templates available
3. Add Cooperation (US6, Phase 8) — T035–T037 → multi-agent scoring available
4. Polish (Phase 9) — T038–T040

---

## Notes

- [P] tasks touch different files or independent methods — safe to parallelize
- Pre-existing scorer files (`exact_match.py`, `regex.py`, `json_schema.py`, `semantic.py`) must have **zero modifications** — T040 is the gate
- `trajectory.py` and `llm_judge.py` exist and must be extended additively — no rewrites
- New entry points in `trajectory.py` (`score_cooperation`) and `llm_judge.py` (`rubric_id` branch) must be isolated so pre-existing `score()` calls are unaffected
- Commit after each phase checkpoint before moving to next phase
- YAML templates (T026–T031) are simple files — fast to write, can all be done in one session
