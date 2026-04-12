# Implementation Plan: Evaluation Framework and Semantic Testing

**Branch**: `034-evaluation-semantic-testing` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/034-evaluation-semantic-testing/spec.md`

---

## Summary

Implement the evaluation and testing subsystem: `evaluation/` manages the full eval lifecycle (eval sets, benchmark cases, runs, verdicts, LLM-as-Judge, trajectory scoring, ATE integration, robustness testing, human-AI grading, A/B experiments); `testing/` handles test generation and operational observability (adversarial generation, test suite generation, drift detection, coordination testing). PostgreSQL for relational truth (13 tables, migration 034); Qdrant for semantic similarity embeddings (`evaluation_embeddings` collection); ClickHouse for behavioral drift time-series; MinIO for ATE evidence and large generated suite artifacts; Kafka `evaluation.events` topic produced.

---

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x (async), aiokafka 0.11+, qdrant-client 1.12+ (gRPC), clickhouse-connect 0.8+, httpx 0.27+ (LLM-as-Judge + adversarial gen), APScheduler 3.x (drift scanner), aioboto3 latest (MinIO ATE evidence), grpcio 1.65+ (SimulationControllerClient, ReasoningEngineClient)  
**Storage**: PostgreSQL 16 (13 tables), Qdrant (`evaluation_embeddings` collection), ClickHouse (`testing_drift_metrics` table), MinIO (`evaluation-ate-evidence`, `evaluation-generated-suites` buckets)  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Linux / Kubernetes (`api` + `agentops-testing` runtime profiles)  
**Project Type**: Python control plane bounded contexts (`evaluation/` + `testing/`)  
**Performance Goals**: Eval run of 100 cases < 30s (SC-001); semantic similarity < 500ms per comparison (SC-003); trajectory scoring < 5s per execution (SC-009)  
**Constraints**: No numpy/scipy (pure Python stdlib statistics); no cross-boundary DB access; simulation always delegated to SimulationControllerClient (gRPC); ClickHouse for all drift time-series  
**Scale/Scope**: 8 user stories, 30 FRs, 11 SCs, 13 PostgreSQL tables, ~26 source files, 36 REST endpoints

---

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| **I — Modular Monolith** | PASS | `evaluation/` and `testing/` are new bounded contexts within `apps/control-plane/`. No new service binary. |
| **II — Go Reasoning Engine** | PASS | TrajectoryScorer calls `ReasoningEngineClient` (gRPC) for traces. LLM-as-Judge does NOT route through reasoning engine — it is a scoring call, not a reasoning session. |
| **III — Dedicated Data Stores** | PASS | Semantic similarity → Qdrant. Drift time-series → ClickHouse. Eval relational truth → PostgreSQL. ATE artifacts → MinIO. No time-series in PostgreSQL. No vectors in PostgreSQL. |
| **IV — No Cross-Boundary DB Access** | PASS | `evaluation/` and `testing/` do not query other bounded contexts' tables. They use `ExecutionQueryInterface`, `AgentRegistryQueryInterface`, `FleetQueryInterface` (in-process service calls), and gRPC for external satellite services. |
| **V — Append-Only Journal** | PASS | Evaluation only reads journal events via `ExecutionQueryInterface`. No writes to the journal. |
| **VI — Policy Is Machine-Enforced** | N/A | No policy enforcement changes. |
| **VII — Simulation Isolation** | PASS | ATE execution delegates to `SimulationControllerClient.CreateSimulation()`. No direct Kubernetes namespace management. Simulation sandboxes run in `platform-simulation` namespace per simulation controller. |
| **VIII — FQN Agent Addressing** | PASS | All eval runs reference agents by FQN (`agent_fqn: str`). UUID stored as `agent_id` for pinned-revision evals. |
| **IX — Zero-Trust Visibility** | N/A | Evaluation does not modify agent visibility. |
| **X — GID Correlation** | N/A | No goal-scoped evaluation in v1. |
| **XI — Secrets Never in LLM Context** | PASS | LLM-as-Judge calls use model provider credentials injected at runtime. Benchmark case input/output data must not contain raw secrets (enforced by OutputSanitizer from `policies/`). |
| **XII — Task Plans as Auditable Artifacts** | PASS | TrajectoryScorer reads `TaskPlanRecord` via `ExecutionQueryInterface`. Does not create new task plans. |

**Re-check post-design**: All 12 applicable gates pass. No design decisions violate constitution principles.

---

## Project Structure

### Documentation (this feature)

```text
specs/034-evaluation-semantic-testing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── evaluation-api.md
└── tasks.md             # Phase 2 output (not yet created)
```

### Source Code

```text
apps/control-plane/src/platform/
├── evaluation/
│   ├── __init__.py
│   ├── models.py                    # 9 SQLAlchemy models + 6 enums
│   ├── schemas.py                   # Pydantic request/response schemas
│   ├── repository.py                # SQLAlchemy repository (all 9 models)
│   ├── service.py                   # EvalSuiteService + EvalRunnerService
│   ├── ate_service.py               # ATEService (pre-check + gRPC delegation)
│   ├── robustness_service.py        # RobustnessTestService (N-trial orchestration)
│   ├── ab_experiment_service.py     # AbExperimentService (statistics)
│   ├── human_grading_service.py     # HumanGradingService
│   ├── scorers/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract Scorer interface + ScoreResult
│   │   ├── exact_match.py           # ExactMatchScorer
│   │   ├── regex.py                 # RegexScorer
│   │   ├── json_schema.py           # JsonSchemaScorer
│   │   ├── semantic.py              # SemanticSimilarityScorer (Qdrant)
│   │   ├── llm_judge.py             # LLMJudgeScorer + RUBRIC_TEMPLATES
│   │   ├── trajectory.py            # TrajectoryScorer
│   │   └── registry.py              # ScorerRegistry (maps scorer_type → Scorer instance)
│   ├── router.py                    # FastAPI router — all evaluation/ endpoints
│   ├── events.py                    # Kafka event emission helpers
│   └── service_interfaces.py        # EvalSuiteServiceInterface (exported)
│
├── testing/
│   ├── __init__.py
│   ├── models.py                    # 4 SQLAlchemy models (3 PG + 1 ClickHouse schema ref)
│   ├── schemas.py                   # Pydantic request/response schemas
│   ├── repository.py                # SQLAlchemy repository
│   ├── adversarial_service.py       # AdversarialGenerationService (LLM via httpx)
│   ├── suite_generation_service.py  # TestSuiteGenerationService
│   ├── drift_service.py             # DriftDetectionService (ClickHouse + APScheduler)
│   ├── coordination_service.py      # CoordinationTestService
│   ├── router.py                    # FastAPI router — all testing/ endpoints
│   ├── events.py                    # Kafka event emission helpers
│   └── service_interfaces.py        # CoordinationTestServiceInterface (exported)
│
└── common/
    └── clients/
        # (already exist — used without modification)
        # qdrant.py, clickhouse.py, object_storage.py, simulation_controller.py,
        # reasoning_engine.py

migrations/
└── versions/
    └── 034_evaluation_testing_schema.py   # Alembic migration — all 13 tables
```

**Structure Decision**: Two bounded contexts within the Python monolith (`evaluation/` + `testing/`), matching constitution repo structure exactly. No new Go services. No frontend in this feature (evaluation workbench is future work).

---

## Implementation Phases

### Phase 0 — Foundational Setup

**Goal**: All shared infrastructure in place before any bounded context code.

- Alembic migration 034 (13 tables: 9 in evaluation/, 4 in testing/)
- ClickHouse table `testing_drift_metrics` provisioned (run via `clickhouse_schema.sql` at startup)
- Qdrant collection `evaluation_embeddings` provisioned (1536-dim Cosine, created at app startup via lifespan hook)
- MinIO buckets `evaluation-ate-evidence` and `evaluation-generated-suites` created at startup
- Kafka topic `evaluation.events` created (configured via Strimzi if in Kubernetes, auto-created locally)

### Phase 1 — Scorer Engine (US1 + US2 prerequisite)

**Goal**: All scorer implementations available before eval runner.

- `evaluation/scorers/base.py`: abstract `Scorer` protocol, `ScoreResult` Pydantic model
- `evaluation/scorers/exact_match.py`: ExactMatchScorer (string equality)
- `evaluation/scorers/regex.py`: RegexScorer (pattern match against actual_output)
- `evaluation/scorers/json_schema.py`: JsonSchemaScorer (jsonschema library validation)
- `evaluation/scorers/semantic.py`: SemanticSimilarityScorer (embed via httpx → model provider, compare in Qdrant)
- `evaluation/scorers/llm_judge.py`: LLMJudgeScorer (httpx judge call × N calibration runs, statistics.mean/stdev/NormalDist), RUBRIC_TEMPLATES dict (6 built-ins)
- `evaluation/scorers/trajectory.py`: TrajectoryScorer (calls ExecutionQueryInterface + ReasoningEngineClient, computes 4 dimensions, optional LLM holistic)
- `evaluation/scorers/registry.py`: ScorerRegistry (maps scorer_type string → Scorer instance, loaded from scorer_config)

### Phase 2 — Evaluation Core (US1)

**Goal**: Eval sets, benchmark cases, runs, verdicts — the foundational evaluation pipeline.

- `evaluation/models.py`: EvalSet, BenchmarkCase, EvaluationRun, JudgeVerdict, AbExperiment, ATEConfig, ATERun, RobustnessTestRun, HumanAiGrade
- `evaluation/repository.py`: CRUD + query methods for all 9 models
- `evaluation/schemas.py`: all Pydantic request/response schemas
- `evaluation/service.py`: EvalSuiteService (CRUD) + EvalRunnerService (orchestrates scoring loop via ScorerRegistry, writes verdicts, updates run aggregates, emits Kafka events)
- `evaluation/events.py`: Kafka producer wrappers
- `evaluation/router.py`: eval-sets, cases, runs, verdicts endpoints

### Phase 3 — LLM-as-Judge (US2)

**Goal**: LLM-as-Judge scorer fully functional with calibration and custom rubrics.

- `evaluation/scorers/llm_judge.py` finalized: RUBRIC_TEMPLATES + custom rubric validation + N-trial calibration loop + score distribution computation
- Integration test: create eval set with llm_judge scorer, run calibration=5, verify distribution in verdict

### Phase 4 — Trajectory Scoring (US3)

**Goal**: TrajectoryScorer produces 5-dimensional scores from execution artifacts.

- `evaluation/scorers/trajectory.py` finalized: ExecutionQueryInterface injection, ReasoningEngineClient gRPC call, 4-metric computation, optional LLM holistic via LLMJudgeScorer
- Integration test: provide mock execution journal + traces + task plan, verify all 5 score dimensions

### Phase 5 — ATE Integration (US5)

**Goal**: ATE configuration, pre-check, simulation delegation, evidence collection.

- `evaluation/ate_service.py`: ATEService (create config, pre-check scenarios, call SimulationControllerClient.CreateSimulation(), poll simulation result, collect MinIO evidence, compile report)
- `evaluation/router.py` extended: ATE CRUD + run + results endpoints
- Integration test: T08 and T09 scenarios

### Phase 6 — Adversarial and Test Suite Generation (US4)

**Goal**: LLM-driven adversarial generation and importable test suites.

- `testing/models.py`: GeneratedTestSuite, AdversarialTestCase, CoordinationTestResult, DriftAlert
- `testing/repository.py`: CRUD for all 4 models
- `testing/schemas.py`: Pydantic schemas
- `testing/adversarial_service.py`: 6-category adversarial generation (LLM via httpx, agent profile from AgentRegistryQueryInterface), MinIO archive for large suites
- `testing/suite_generation_service.py`: orchestrates adversarial + positive generation, assembles GeneratedTestSuite
- `testing/router.py`: suites generate/list/get/cases/import endpoints

### Phase 7 — Statistical Robustness (US6 part 1)

**Goal**: N-trial robustness test runs with statistical distribution.

- `evaluation/robustness_service.py`: RobustnessTestService (spawn N EvaluationRuns in sequence via EvalRunnerService, collect scores, compute distribution via statistics stdlib, flag unreliable)
- `evaluation/router.py` extended: robustness-runs endpoints
- Integration test: T10, T11 scenarios

### Phase 8 — Behavioral Drift Detection (US6 part 2)

**Goal**: ClickHouse drift metric writes + APScheduler drift scanner + alerts.

- `testing/drift_service.py`: DriftDetectionService (write `testing_drift_metrics` to ClickHouse after each eval run completes, APScheduler job to query ClickHouse baseline per active agent+eval_set pair, compare current vs baseline mean−N×stddev, create DriftAlert + emit `evaluation.drift.detected`)
- Drift suppression: check if active RobustnessTestRun exists for agent before firing alert
- `testing/router.py` extended: drift-alerts list/acknowledge endpoints
- Integration test: T12, T13 scenarios

### Phase 9 — Coordination Testing (US7)

**Goal**: Multi-agent coordination evaluation from fleet execution data.

- `testing/coordination_service.py`: CoordinationTestService (reads per-agent execution journals via ExecutionQueryInterface, scores completion/coherence/goal-achievement, handles insufficient_members edge case)
- `testing/router.py` extended: coordination-tests endpoints
- Integration test: T14, T15 scenarios

### Phase 10 — Human-AI Grading (US8)

**Goal**: Human review workflow with audit trail.

- `evaluation/human_grading_service.py`: HumanGradingService (submit grade, update grade, review progress query, original score snapshot)
- `evaluation/router.py` extended: grading endpoints
- Integration test: T16, T17, T18 scenarios

### Phase 11 — A/B Experiments (US1 A/B)

**Goal**: Statistical comparison between two evaluation runs.

- `evaluation/ab_experiment_service.py`: AbExperimentService (fetch score arrays from both runs' verdicts, run Welch's t-test, compute Cohen's d, determine winner, write analysis summary)
- `evaluation/router.py` extended: experiments endpoints
- Integration test: T03 scenario

### Phase 12 — Polish and Cross-Cutting

- Wire `agentops-testing` runtime profile: register APScheduler jobs (drift scanner)
- Wire `api` profile: mount `evaluation/router.py` and `testing/router.py` in `main.py`
- Export `EvalSuiteServiceInterface` and `CoordinationTestServiceInterface` via DI
- OpenTelemetry spans on all service methods
- Full test coverage sweep to hit ≥95% (SC-011)
- ruff + mypy strict pass

---

## Complexity Tracking

No constitution violations. No entries required.
