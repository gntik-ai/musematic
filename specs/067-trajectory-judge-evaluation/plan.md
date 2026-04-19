# Implementation Plan: Trajectory Evaluation and LLM-as-Judge Formalization

**Branch**: `067-trajectory-judge-evaluation` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/067-trajectory-judge-evaluation/spec.md`

## Summary

Formalize and extend two already-existing scorer implementations (`trajectory.py`, `llm_judge.py`) in the `evaluation/` bounded context. **What exists**: Both scorers are registered in `ScorerRegistry`; `LLMJudgeScorer` already runs in-memory calibration; `TrajectoryScorer` already computes 4 dimensions from execution data. **What this feature adds**: (1) `Rubric` as a first-class DB entity with versioning, lifecycle management, and CRUD API; (2) `CalibrationRun` as a persisted, immutable DB entity with distribution reports; (3) six YAML rubric templates loaded as builtin DB records at startup; (4) explicit 5-method comparison dispatch in `TrajectoryScorer`; (5) multi-agent cooperation scoring mode; (6) ad-hoc judge endpoint + scorer enumeration endpoint; (7) `EvaluationSettings` in config. Migration 054.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, httpx 0.27+, PyYAML 6.x (already present) — all already in requirements.txt  
**Storage**: PostgreSQL 16 (2 new tables + 2 new enums via Alembic 054); no Redis, no MinIO, no ClickHouse  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux, Kubernetes  
**Project Type**: Web service — additive extension in existing FastAPI monolith  
**Performance Goals**: Ad-hoc judge latency ≤ 30s p95 (SC-013); pre-existing scorer paths zero added latency (SC-010)  
**Constraints**: Pre-existing scorers byte-identical (FR-020, SC-010); additive schema only (FR-021); never rewrite existing scorer files (Brownfield Rule 1); no new gate types (Brownfield Rule 4)  
**Scale/Scope**: Extensions to 7 existing files + 1 new service file + 6 YAML templates + 1 migration; ~10–12 source files total

## Constitution Check

*All principles checked against this feature design.*

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | All changes inside existing `evaluation/` bounded context; no new bounded context created |
| **Principle III** — Dedicated data stores | ✅ PASS | PostgreSQL for rubric + calibration records; no in-memory shared state |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `TrajectoryScorer` reads execution data via injected `execution_query` interface (not direct DB); `CalibrationService` reads only `evaluation_*` tables |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | Ad-hoc judge endpoint reuses existing eval auth + rate-limit surface (FR-022); no new auth primitives |
| **Principle VIII** — FQN addressing | ✅ PASS | Scorer types identified by string key in existing registry; rubric referenced by UUID |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Rubric CRUD endpoints workspace-scoped; builtin rubrics readable cross-workspace |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | Judge invocations pass only output + rubric criteria to LLM; no secrets in prompt |
| **Reminder 26** — Evaluate trajectories, not just outputs | ✅ PASS | Core mandate of this feature; TrajectoryScorer + cooperation mode directly addresses this |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | `trajectory.py` and `llm_judge.py` extended additively; no file replaced wholesale |
| **Brownfield Rule 2** — Alembic migrations | ✅ PASS | All DDL in migration 054 |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Pre-existing scorers untouched; SC-010 byte-identity regression test validates this |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | `RubricService` + `CalibrationService` follow `EvalSuiteService` + `EvalRunnerService` pattern; same repo/service/schema/event structure |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | All modified files cited below with exact paths |
| **Brownfield Rule 6** — Additive enum values | ✅ PASS | Two new enums (`rubric_status`, `calibration_run_status`) created fresh; no existing enum modified |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | All new endpoints are additive routes; existing 15 routes unchanged; `ScorerRegistry.registered_types()` already returns sorted list |
| **Reminder 29** — No MinIO in app code | ✅ PASS | No object storage needed; rubrics + calibration reports stored in PostgreSQL |

## Project Structure

### Documentation (this feature)

```text
specs/067-trajectory-judge-evaluation/
├── plan.md              ✅ This file
├── spec.md              ✅ Feature specification
├── research.md          ✅ Phase 0 output
├── data-model.md        ✅ Phase 1 output
├── quickstart.md        ✅ Phase 1 output
├── contracts/
│   └── rest-api.md      ✅ Phase 1 output
└── checklists/
    └── requirements.md  ✅ Spec validation (all pass)
```

### Source Code

```text
apps/control-plane/
├── migrations/versions/
│   └── 054_trajectory_evaluation_schema.py              # NEW: 2 tables + 2 enums
└── src/platform/evaluation/
    ├── rubrics/                                         # NEW directory: 6 YAML templates
    │   ├── correctness.yaml
    │   ├── helpfulness.yaml
    │   ├── safety.yaml
    │   ├── style.yaml
    │   ├── faithfulness.yaml
    │   └── instruction_following.yaml
    ├── rubric_templates.py                              # NEW: RubricTemplateLoader
    ├── models.py                                        # MODIFY: add Rubric, CalibrationRun models + 2 enums
    ├── schemas.py                                       # MODIFY: add RubricCreate/Response, CalibrationRunCreate/Response, AdHocJudgeRequest/Response
    ├── repository.py                                    # MODIFY: add rubric + calibration run DB operations
    ├── service.py                                       # MODIFY: add RubricService + CalibrationService classes; extend EvalRunnerService with judge_adhoc()
    ├── events.py                                        # MODIFY: add 6 new event types
    ├── router.py                                        # MODIFY: add 10 new routes
    ├── dependencies.py                                  # MODIFY: expose RubricService + CalibrationService deps
    ├── scorers/
    │   ├── trajectory.py                                # MODIFY: explicit 5-method _compare dispatch; add score_cooperation()
    │   └── llm_judge.py                                 # MODIFY: accept rubric_id for DB lookup alongside inline config
    └── common/config.py                                 # MODIFY (path: apps/control-plane/src/platform/common/config.py): add EvaluationSettings

apps/control-plane/tests/
├── unit/evaluation/
│   ├── test_trajectory_scorer.py                        # NEW: 5 comparison methods, cooperation, edge cases
│   ├── test_llm_judge_scorer.py                         # NEW: rubric lookup, clamping, malformed output, retries
│   ├── test_rubric_service.py                           # NEW: CRUD, version increment, archival guard, builtin protection
│   └── test_calibration_service.py                      # NEW: distribution stats, low-discrimination, immutability
└── integration/evaluation/
    ├── test_rubrics_integration.py                      # NEW: create/update/archive/delete lifecycle
    └── test_calibration_integration.py                  # NEW: start + complete calibration run; report structure
```

## Complexity Tracking

No constitution violations. `trajectory.py` and `llm_judge.py` are the highest-risk files — the byte-identity guarantee (SC-010) requires the new code paths (cooperation mode, `rubric_id` lookup) to be isolated behind new entry points that cannot be reached by pre-existing scorer configs. Specifically: `score()` method signature and behavior must be unchanged; new capabilities enter via `score_cooperation()` and the `rubric_id` branch inside `score()` only when `rubric_id` is present in config.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: Extend existing scorers additively — both `trajectory.py` and `llm_judge.py` already exist; cooperation scoring added as `score_cooperation()` separate method
- **D-002**: `evaluation_rubrics` table — formal rubric entity with `version`, `is_builtin`, `status`, soft-delete
- **D-003**: `evaluation_calibration_runs` table — immutable after `completed_at`, stores full `CalibrationReport` as JSONB
- **D-004**: `EvaluationSettings` class added to `config.py` — `LLM_JUDGE_API_URL`, `LLM_JUDGE_MODEL`, `LLM_JUDGE_TIMEOUT_SECONDS=30`, `LLM_JUDGE_MAX_RETRIES=2`, `TRAJECTORY_MAX_STEPS=10000`, `CALIBRATION_VARIANCE_ENVELOPE=0.2`
- **D-005**: YAML templates as files loaded at startup by `RubricTemplateLoader` into `evaluation_rubrics` as `is_builtin=true` records (upsert by name)
- **D-006**: Migration 054, `down_revision = "053_mcp_integration"` — 2 tables + 2 enums, no column additions to existing tables
- **D-007**: Ad-hoc judge endpoint `POST /api/v1/evaluation/judge` — accepts `rubric_id` or inline rubric; reuses existing EvalRunnerService path; returns verdict within 30s p95
- **D-008**: Scorer enumeration `GET /api/v1/evaluation/scorers` — in-memory `ScorerRegistry.registered_types()`, no DB read
- **D-009**: Rubric in-flight guard — JSONB containment query on `evaluation_runs.scorer_config`; reject 409 if match on `status='running'`
- **D-010**: Cooperation scoring via `TrajectoryScorer.score_cooperation(agent_execution_ids, config)` — graph-traversal cycle detection on handoff events; returns `CooperationScoreResult`
- **D-011**: Comparison dispatch — `_compare(actual, expected, method: Literal["exact","in_order","any_order","precision","recall"])` static method added to `TrajectoryScorer`
- **D-012**: `RubricService` + `CalibrationService` — two new classes in existing `service.py` following `EvalSuiteService`/`EvalRunnerService` pattern

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 2 new tables, 2 new enums, YAML template schema, 6 new Kafka event types
- [contracts/rest-api.md](contracts/rest-api.md) — 10 new endpoints + 3 internal service interfaces
- [quickstart.md](quickstart.md) — 25 acceptance scenarios (S1–S25)
