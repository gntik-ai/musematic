# Implementation Plan: AgentOps Lifecycle Management

**Branch**: `037-agentops-lifecycle` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/037-agentops-lifecycle/spec.md`

## Summary

Build a greenfield `agentops/` bounded context in the Python control plane implementing: periodic composite health scoring (5 weighted dimensions, APScheduler), statistical behavioral regression detection (Welch t-test / Mann-Whitney U via scipy), 5-gate CI/CD deployment gate checks (all gates run concurrently), canary deployment management (Redis-based traffic routing + APScheduler monitoring), automated retirement workflows (dependency detection + grace periods), continuous governance (recertification triggers + grace period scanner), append-only governance audit trail, and a human-in-the-loop agent self-improvement adaptation pipeline.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, clickhouse-connect 0.8+, APScheduler 3.x, **numpy>=1.26** (new), **scipy>=1.13** (new)  
**Storage**: PostgreSQL 16 (9 tables), ClickHouse 24.3+ (1 new table: `agentops_behavioral_versions`)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Kubernetes `platform-control` namespace, `agentops` runtime profile  
**Project Type**: Python modular monolith bounded context  
**Performance Goals**: Gate check completes in <60s (5 concurrent in-process calls); health score update for 1000 agents within scoring interval; canary monitoring loop runs every 5 minutes  
**Constraints**: All async (no sync I/O); no cross-boundary DB access (use service interfaces); append-only governance_events; Redis canary routing key written atomically  
**Scale/Scope**: ~1000 active agents per workspace; up to 50 concurrent canary deployments; governance audit trail unbounded (cursor-paginated reads)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| I. Modular Monolith | ✅ | New `agentops/` bounded context in control plane |
| III. Dedicated Data Stores | ✅ | PostgreSQL for relational state; ClickHouse for behavioral time-series (not PostgreSQL) |
| IV. No Cross-Boundary DB Access | ✅ | Trust, evaluation, policy, workflow, registry accessed via service interfaces only (see `contracts/service-interfaces.md`) |
| V. Append-Only Journal | ✅ | `agentops_governance_events` is insert-only |
| XI. Secrets Never in LLM Context | ✅ | Adaptation proposals are rule-based, not LLM-generated |
| All async | ✅ | All service, repository, and router methods are `async def` |

**New dependency justification (Complexity Tracking)**:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| `numpy>=1.26` (new) | Required as scipy's array foundation; no alternative | scipy cannot function without it |
| `scipy>=1.13` (new) | Industry-standard t-test + Mann-Whitney U implementations; precise p-values and effect sizes | Rolling our own statistical tests would be brittle and unaudited; pingouin/statsmodels are heavier |

**Post-Phase 1 re-check**: All design decisions comply. Redis canary key is workspace+FQN scoped (no cross-workspace leakage). Behavioral version ClickHouse table is new; reads from existing `analytics_*` tables are aggregation queries only, not cross-boundary writes.

## Project Structure

### Documentation (this feature)

```text
specs/037-agentops-lifecycle/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-endpoints.md       # REST endpoint contracts
│   └── service-interfaces.md  # In-process service interface contracts
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/control-plane/
├── pyproject.toml                    # Add: numpy>=1.26, scipy>=1.13
├── src/platform/
│   ├── main.py                       # Register agentops runtime profile
│   └── agentops/
│       ├── __init__.py
│       ├── models.py                 # 9 SQLAlchemy models
│       ├── schemas.py                # Pydantic request/response schemas
│       ├── service.py                # AgentOpsService + exposed AgentOpsServiceInterface
│       ├── repository.py             # Async DB access (insert-only governance_events)
│       ├── router.py                 # FastAPI router (/api/v1/agentops)
│       ├── events.py                 # Kafka event types + AgentOpsEventPublisher
│       ├── exceptions.py             # CanaryConflictError, BaselineNotReadyError, etc.
│       ├── dependencies.py           # FastAPI DI: get_agentops_service
│       ├── health/
│       │   ├── scorer.py             # HealthScorer: compute composite from dimensions
│       │   └── dimensions.py         # Per-dimension data fetchers (5 dimensions)
│       ├── regression/
│       │   ├── detector.py           # RegressionDetector: comparison + alert creation
│       │   └── statistics.py         # StatisticalComparator: test selection + scipy wrappers
│       ├── cicd/
│       │   └── gate.py               # CiCdGate: 5 gates via asyncio.gather
│       ├── canary/
│       │   ├── manager.py            # CanaryManager: start/promote/rollback + Redis
│       │   └── monitor.py            # CanaryMonitor: APScheduler metric polling
│       ├── retirement/
│       │   └── workflow.py           # RetirementManager: initiation + grace period
│       ├── governance/
│       │   ├── triggers.py           # GovernanceTriggerProcessor: Kafka consumers
│       │   └── grace_period.py       # GracePeriodScanner: APScheduler tasks
│       └── adaptation/
│           ├── pipeline.py           # AdaptationPipeline: proposal → approve → ATE → promote
│           └── analyzer.py           # BehavioralAnalyzer: 4 rule-based signal detectors
│
├── migrations/versions/
│   └── 037_agentops_lifecycle.py     # All 9 PostgreSQL tables
│
└── tests/
    ├── unit/agentops/
    │   ├── test_health_scorer.py
    │   ├── test_health_dimensions.py
    │   ├── test_regression_detector.py
    │   ├── test_statistics.py
    │   ├── test_cicd_gate.py
    │   ├── test_canary_manager.py
    │   ├── test_canary_monitor.py
    │   ├── test_retirement_workflow.py
    │   ├── test_governance_triggers.py
    │   ├── test_grace_period.py
    │   ├── test_adaptation_analyzer.py
    │   └── test_adaptation_pipeline.py
    └── integration/agentops/
        ├── test_health_endpoints.py
        ├── test_regression_endpoints.py
        ├── test_gate_endpoints.py
        ├── test_canary_endpoints.py
        ├── test_retirement_endpoints.py
        ├── test_governance_endpoints.py
        └── test_adaptation_endpoints.py
```

**Structure Decision**: Single `agentops/` bounded context following the canonical bounded context layout. Seven sub-modules group logic by domain (health, regression, cicd, canary, retirement, governance, adaptation) while routing all DB access through `repository.py` and all business coordination through `service.py`.

## Implementation Phases

### Phase 1 — Models, Schemas, Repository, Migration

**Goal**: All data models, Pydantic schemas, repository, and Alembic migration ready before any business logic.

1. Add `numpy>=1.26` and `scipy>=1.13` to `apps/control-plane/pyproject.toml`
2. Create `models.py` — all 9 SQLAlchemy models per `data-model.md`; correct mixin order; JSONB types; indexes on `(agent_fqn, workspace_id)`; `agentops_governance_events` has no `updated_at` (append-only)
3. Create `schemas.py` — Pydantic v2 schemas for all 7 API sections; field validators: weight sum = 100.0, traffic_percentage ∈ [1,50], observation_window_hours ≥ 1.0
4. Create `repository.py` — all async CRUD; `insert_governance_event` has no update/delete counterparts
5. Create `exceptions.py` — `CanaryConflictError`, `BaselineNotReadyError`, `RetirementConflictError`, `InsufficientSampleError`, `WeightSumError`
6. Create Alembic migration `037_agentops_lifecycle.py` — all 9 tables; ClickHouse DDL as comment for separate application

---

### Phase 2 — Health Scoring (US1)

**Goal**: Periodic composite health score computable and queryable for all active agents.

1. `health/dimensions.py` — five async fetchers: `uptime_score()` (Redis heartbeat keys), `quality_score()` (ClickHouse 30-day rolling avg), `safety_score()` (TrustService guardrail pass rate), `cost_efficiency_score()` (ClickHouse cost-per-quality), `satisfaction_score()` (EvalSuiteService human grade aggregate); each returns `DimensionResult(score: float | None, sample_count: int)`
2. `health/scorer.py` — `HealthScorer.compute()`: calls all 5 fetchers with `asyncio.gather`, redistributes weights for None dimensions, emits warning/critical events via `AgentOpsEventPublisher`
3. APScheduler task: `score_all_agents_task()` — query active agents per workspace, compute and upsert health scores
4. `router.py` health endpoints, `service.py` coordination

---

### Phase 3 — Behavioral Regression Detection (US2)

**Goal**: Statistical comparison between revision behavioral samples; regression alerts block deployment.

1. `regression/statistics.py` — `StatisticalComparator.compare(sample_a, sample_b, alpha)`: Shapiro-Wilk screen if n≥30 → Welch t-test or Mann-Whitney U; returns `ComparisonResult`
2. `regression/detector.py` — `RegressionDetector.detect()`: fetch ClickHouse samples per dimension for both revisions; run comparison per dimension; create `BehavioralRegressionAlert` if any regress; record `regression_detected` governance event
3. Kafka consumer trigger: on `evaluation.events` evaluation completion → `detector.detect()`
4. `router.py` regression endpoints

---

### Phase 4 — CI/CD Gate Checks (US3)

**Goal**: All 5 gates run concurrently; result persisted; gate summary exposed as service interface.

1. `cicd/gate.py` — `CiCdGate.evaluate()`: `asyncio.gather(policy_gate, eval_gate, cert_gate, regression_gate, trust_gate)` — each is a sub-coroutine calling the appropriate service interface; assemble `CiCdGateResultCreate`; upsert `CiCdGateResult`
2. `service.py` — expose `run_gate_check()` as `AgentOpsServiceInterface` method
3. `router.py` gate endpoints

---

### Phase 5 — Canary Deployment (US4)

**Goal**: Redis-based canary routing; APScheduler monitoring; auto-promote and auto-rollback.

1. `canary/manager.py` — `start()`: check for active canary (409); write Redis key with TTL; insert `CanaryDeployment`; `promote(canary_id, manual)`: clear Redis key; update status; emit event; `rollback(canary_id, reason, manual)`: clear Redis key; update status; set `triggered_rollback` on related regression alert if applicable
2. `canary/monitor.py` — APScheduler task: for each active canary, fetch ClickHouse metrics for canary revision vs production, check tolerances, trigger auto-rollback or auto-promote
3. `router.py` canary endpoints (all 6)

---

### Phase 6 — Automated Retirement (US5)

**Goal**: Health-triggered and expiry-triggered retirement; dependency detection; grace period enforcement.

1. `retirement/workflow.py` — `RetirementManager.initiate()`: dedup check; call `WorkflowService.find_workflows_using_agent`; set `high_impact_flag`; require `operator_confirmed` for high-impact; insert `RetirementWorkflow`; publish notifications via `agentops.events`; `retire_agent()`: call `RegistryService.set_marketplace_visibility(False)`; record `retirement_completed` governance event
2. `governance/grace_period.py` — APScheduler task: scan retirement workflows where `grace_period_ends_at < now()` and `status = 'grace_period'`; call `retire_agent()`
3. Health score post-processing in `health/scorer.py` — track consecutive critical intervals via Redis counter; emit `retirement_trigger` event at threshold
4. `governance/triggers.py` — consume `retirement_trigger` → call `RetirementManager.initiate`
5. `router.py` retirement endpoints (4)

---

### Phase 7 — Continuous Governance (US6)

**Goal**: Recertification triggers fire on all 5 trigger types; grace periods enforced; full audit trail.

1. `governance/triggers.py` — Kafka consumers: `trust.events` (revision change, policy change, cert expiry, conformance failure) → call `TrustService.trigger_recertification` + record `GovernanceEvent`; `agentops.events` regression_detected → trigger recertification
2. `governance/grace_period.py` — second APScheduler task: scan `pending_recertification` agents with expired grace periods; call trust service to expire certification; emit governance event; call `RegistryService.set_marketplace_visibility(False)` if configured
3. `events.py` — `GovernanceEventPublisher.record()` wrapper (insert-only)
4. `router.py` governance endpoints (2)

---

### Phase 8 — Adaptation Pipeline (US7)

**Goal**: Rule-based adaptation proposals; human approval required; ATE testing; promotion on pass.

1. `adaptation/analyzer.py` — `BehavioralAnalyzer.analyze()`: fetch ClickHouse 14-day quality trend, 7-day failure categories, cost-quality ratio, tool invocation rates; apply 4 rules; return `list[AdaptationSignal]`
2. `adaptation/pipeline.py` — `AdaptationPipeline.propose()`: call `BehavioralAnalyzer`, insert `AdaptationProposal` status=`proposed` (or return "no opportunities" if signals empty); `review()`: if approved, call `RegistryService` to create revision candidate, call `EvalSuiteService.submit_to_ate`, set status `testing`; `handle_ate_result()`: promote or fail based on ATE result
3. `governance/triggers.py` — ATE completion consumer
4. `router.py` adaptation endpoints (3)

---

### Phase 9 — Tests, Linting, Type Checking

**Goal**: ≥95% coverage; mypy strict; ruff clean.

1. Unit tests for all sub-modules with injected mock service interfaces (12 test files)
2. `test_statistics.py` — deterministic tests with synthetic distributions (large normal sample → t-test; small/skewed → Mann-Whitney; known p-values)
3. Integration tests for all 7 endpoint groups using SQLite local mode fallback (7 test files)
4. Edge case tests: missing dimension, insufficient samples, concurrent canary conflict (409), high-impact retirement confirmation required, zero grace period, empty adaptation proposals
5. Run coverage, close gaps, mypy strict, ruff
