# Research: Trajectory Evaluation and LLM-as-Judge Formalization

**Feature**: 067-trajectory-judge-evaluation  
**Date**: 2026-04-19  
**Phase**: 0 — Research & Discovery

## Codebase Survey Findings

### Existing Implementation (Critical Discovery)

Both `trajectory.py` and `llm_judge.py` **already exist** in `evaluation/scorers/` and are already registered in `default_scorer_registry`. The feature formalizes, extends, and persists these capabilities — it does not create scorers from scratch.

```
apps/control-plane/src/platform/evaluation/
├── scorers/
│   ├── base.py          # Scorer Protocol + ScoreResult
│   ├── registry.py      # ScorerRegistry (dict-based)
│   ├── exact_match.py   # ✅ existing
│   ├── regex.py         # ✅ existing
│   ├── json_schema.py   # ✅ existing
│   ├── semantic.py      # ✅ existing
│   ├── llm_judge.py     # ✅ existing (calibration already in-memory)
│   └── trajectory.py    # ✅ existing (4 dimensions, execution_id-based)
├── models.py            # 9 existing tables
├── service.py           # EvalSuiteService + EvalRunnerService
├── repository.py        # EvaluationRepository
├── schemas.py           # LLMJudgeConfig, RubricConfig, CalibrationDistribution
├── router.py            # 15 existing routes
├── events.py            # 10 Kafka event types on evaluation.events
└── dependencies.py      # build_scorer_registry, build_eval_runner_service
```

### Scorer Base Protocol

```python
class Scorer(Protocol):
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult: ...

class ScoreResult(BaseModel):
    score: float | None = None
    passed: bool | None = None
    rationale: str | None = None
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
```

### Registry Pattern

```python
# registry.py
class ScorerRegistry:
    def __init__(self) -> None:
        self._scorers: dict[str, Scorer] = {}
    def register(self, scorer_type: str, scorer: Scorer) -> None: ...
    def get(self, scorer_type: str) -> Scorer: ...
    def registered_types(self) -> list[str]: return sorted(self._scorers)

# Already registered in dependencies.py:build_scorer_registry():
registry.register("exact_match", ExactMatchScorer())
registry.register("regex", RegexScorer())
registry.register("json_schema", JsonSchemaScorer())
registry.register("semantic", SemanticSimilarityScorer())
registry.register("llm_judge", LLMJudgeScorer())
registry.register("trajectory", TrajectoryScorer())
```

### Existing LLMJudgeScorer Calibration

Calibration already runs in-memory inside `LLMJudgeScorer.score()`:
- `calibration_runs: int` in `LLMJudgeConfig` (default 3, max 20)
- Produces `CalibrationDistribution(mean, stddev, confidence_interval, runs, low_confidence)`
- Result stored in `ScoreResult.extra["calibration_distribution"]` — **not persisted to DB**

### Existing TrajectoryScorer

`TrajectoryScorer` already computes: path efficiency, tool appropriateness, reasoning coherence, cost-effectiveness via `ExecutionEvent` + `ExecutionTaskPlanRecord` + `ExecutionReasoningTraceRecord`. No multi-agent cooperation mode. Comparison methods (exact, in-order, any-order, precision, recall) need explicit dispatch verification.

### Existing DB Tables (evaluation)

| Table | Key Columns |
|---|---|
| `evaluation_eval_sets` | id, workspace_id, scorer_config JSONB, pass_threshold |
| `evaluation_benchmark_cases` | id, eval_set_id, input_data JSONB, expected_output, scoring_criteria JSONB |
| `evaluation_runs` | id, eval_set_id, agent_fqn, status, aggregate_score |
| `evaluation_judge_verdicts` | id, run_id, benchmark_case_id, scorer_results JSONB, overall_score, passed |
| `evaluation_ab_experiments` | id, run_a_id, run_b_id, p_value |
| `evaluation_ate_configs` | id, workspace_id, scenarios JSONB |
| `evaluation_ate_runs` | id, ate_config_id, status, report JSONB |
| `evaluation_robustness_runs` | id, eval_set_id, distribution JSONB |
| `evaluation_human_grades` | id, verdict_id, reviewer_id, override_score |

### LLM HTTP Client Pattern

```python
# All scorers use direct httpx.AsyncClient — no shared LLM wrapper
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.post(
        self.settings.composition.llm_api_url,
        json={"model": judge_model, "prompt": prompt},
    )
```

LLM API URL sourced from `settings.composition.llm_api_url` (CompositionSettings).

### No EvaluationSettings

Config has no `EvaluationSettings` class. Evaluation-specific settings live inline in scorer constructors pulling from `CompositionSettings` or hardcoded defaults.

### Migration Numbering

Latest migration: `053_mcp_integration.py` → next is **054**.  
Down revision for 054: `"053_mcp_integration"`.

---

## Decisions

### D-001: Extend existing scorers — never rewrite

- **Decision**: Extend `trajectory.py` and `llm_judge.py` additively. Add cooperation scoring as a new method on `TrajectoryScorer`. Add `rubric_id` parameter support to `LLMJudgeScorer.score()` for DB-backed rubric lookup alongside inline config.
- **Rationale**: Both scorers already exist and are in production. Brownfield Rule 1.
- **Alternatives**: Create `TrajectoryCooperationScorer` as a separate scorer — rejected; unnecessary split, cooperation is a mode of trajectory scoring not an independent scorer.

### D-002: Rubric as DB entity (`evaluation_rubrics` table)

- **Decision**: New `evaluation_rubrics` table (id, workspace_id, name, description, criteria JSONB, version int, is_builtin bool, status rubric_status enum, created_by UUID, deleted_at). Each schema-changing save increments `version`. Built-in templates loaded as `is_builtin=true` records at startup.
- **Rationale**: Spec requires rubric versioning, lifecycle management (archival, in-flight guard), and verdict-to-rubric-version traceability (FR-009, FR-010, FR-024). These require first-class DB records.
- **Alternatives**: Keep rubrics as JSONB in eval_set scorer_config — rejected; no lifecycle management possible.

### D-003: CalibrationRun as DB entity (`evaluation_calibration_runs` table)

- **Decision**: New `evaluation_calibration_runs` table (id, rubric_id FK, judge_model, reference_set_id, status calibration_run_status enum, distribution JSONB, agreement_rate float, calibrated bool, error_grade_finding bool, started_at, completed_at). Immutable after `completed_at` is set.
- **Rationale**: FR-013/FR-014 require immutable calibration reports referencing rubric version + timestamp. Current in-memory CalibrationDistribution in LLMJudgeScorer satisfies per-scoring-call use but not persistent calibration reports.
- **Alternatives**: Store in MinIO as JSON blob — rejected; requires separate fetch path; DB is cleaner for structured reports.

### D-004: New EvaluationSettings class in config.py

- **Decision**: Add `EvaluationSettings` with:
  - `EVALUATION_LLM_JUDGE_API_URL`: str (defaults to `COMPOSITION_LLM_API_URL`)
  - `EVALUATION_LLM_JUDGE_MODEL`: str = "gpt-4"
  - `EVALUATION_LLM_JUDGE_TIMEOUT_SECONDS`: int = 30
  - `EVALUATION_LLM_JUDGE_MAX_RETRIES`: int = 2
  - `EVALUATION_TRAJECTORY_MAX_STEPS`: int = 10000
  - `EVALUATION_CALIBRATION_VARIANCE_ENVELOPE`: float = 0.2
- **Rationale**: Spec documents these defaults as operator-configurable (Assumptions section). Without a settings class, they live as magic numbers in scorer code.
- **Alternatives**: Reuse CompositionSettings LLM settings — rejected; evaluation judge may use a different model/URL than composition.

### D-005: YAML rubric templates as files, loaded as DB records at startup

- **Decision**: 6 YAML files under `evaluation/rubrics/` directory (`correctness.yaml`, `helpfulness.yaml`, `safety.yaml`, `style.yaml`, `faithfulness.yaml`, `instruction_following.yaml`). `RubricTemplateLoader` (new file `rubric_templates.py`) scans the directory at application lifespan startup, upserts records in `evaluation_rubrics` with `is_builtin=true`. Templates are read-only at runtime — no UPDATE/DELETE permitted on builtin records.
- **Rationale**: YAML files are additive-only (FR-018) and version-controlled in git. Loading into DB at startup makes them queryable via the same rubric API without special-casing.
- **Alternatives**: Serve templates as static JSON from router without DB rows — rejected; cannot reference them by rubric_id in verdicts or calibration runs.

### D-006: Migration 054, additive schema only

- **Decision**: Migration `054_trajectory_evaluation_schema.py`, `down_revision = "053_mcp_integration"`. Creates 2 new tables + 2 new enums. No changes to existing tables (FR-021 backward-compatibility). Expected trajectory data stored in existing `BenchmarkCase.scoring_criteria JSONB` under key `"trajectory"` — no new column needed.
- **Rationale**: Additive schema (Brownfield Rule 2). Expected trajectory as JSONB avoids DDL on production table.
- **Alternatives**: Add `expected_trajectory` column to `evaluation_benchmark_cases` — not needed; scoring_criteria already carries scorer-specific structured config.

### D-007: Ad-hoc judge endpoint — `POST /api/v1/evaluation/judge`

- **Decision**: New route in `router.py` that accepts `rubric_id: UUID | None`, optional inline `rubric: RubricCreate`, and `output: str`. Delegates to `EvalRunnerService.judge_adhoc()`. Auth, rate-limit, and output sanitization identical to `POST /eval-sets/{id}/run`.
- **Rationale**: FR-022 requires no eval-set setup overhead. Single endpoint; reuses all existing infrastructure.
- **Alternatives**: Separate ad-hoc router file — rejected; one new route does not warrant a new module.

### D-008: Scorer enumeration — `GET /api/v1/evaluation/scorers`

- **Decision**: Returns `ScorerRegistry.registered_types()` (in-memory list). No DB read needed. New route added to `router.py`.
- **Rationale**: FR-019. The in-memory registry is authoritative for available types; no separate DB table needed.

### D-009: Rubric lifecycle guard (in-flight deletion check)

- **Decision**: Before soft-delete of a rubric, query `evaluation_runs WHERE status = 'running'` and `scorer_config @> '{"llm_judge": {"rubric_id": "<id>"}}'` (JSONB containment). If any rows found → HTTP 409 with message. Archival (status=archived) blocks new runs but not deletion guard.
- **Rationale**: FR-024. Uses existing `evaluation_runs` table, JSONB containment operator — no new index needed beyond existing GIN on scorer_config.

### D-010: Multi-agent cooperation scoring via new method on TrajectoryScorer

- **Decision**: Add `async score_cooperation(agent_execution_ids: list[UUID], config: dict) -> CooperationScoreResult` to `TrajectoryScorer`. Separate from `score()` method to keep standard Protocol intact. Returns `CooperationScoreResult(per_agent_scores, coordination_overhead, handoff_timeliness, redundancy, joint_path_efficiency, cycle_flags)`.
- **Rationale**: FR-005, FR-028. Cooperation mode takes multiple execution_ids — cannot fit in the `score(actual, expected, config)` Protocol signature without breaking it.
- **Alternatives**: New `cooperation` flag in config — rejected; would make `score()` overloaded and complex.

### D-011: Comparison method dispatch in TrajectoryScorer

- **Decision**: Add explicit `_compare(actual_steps, expected_steps, method)` static method with match/case over 5 literals: `exact`, `in_order`, `any_order`, `precision`, `recall`. Called from `score()` based on `config.get("comparison_method", "any_order")`.
- **Rationale**: FR-002. Current implementation may only have partial comparison support; explicit dispatch makes it unambiguous and testable.

### D-012: RubricService and CalibrationService as additive methods in service.py

- **Decision**: Add `RubricService` class and `CalibrationService` class as separate classes in `service.py` (same file, different classes — following existing pattern of `EvalSuiteService` + `EvalRunnerService` in same file). Each takes `EvaluationRepository` + `EvaluationSettings`.
- **Rationale**: Brownfield Rule 4 (use existing patterns). Two classes in service.py is already the established pattern.
- **Alternatives**: New `rubric_service.py` and `calibration_service.py` files — rejected; the existing evaluation context keeps service classes together.
