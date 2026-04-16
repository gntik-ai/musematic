# Implementation Plan: Simulation and Digital Twins

**Branch**: `040-simulation-digital-twins` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/040-simulation-digital-twins/spec.md`

## Summary

Build a greenfield `simulation/` bounded context in the Python control plane implementing: simulation run coordination via gRPC to the existing SimulationControlService satellite (port 50055), versioned digital twin creation (registry config snapshot + ClickHouse behavioral history), simulation isolation policy enforcement (action blocking/stubbing via PolicyServiceInterface), behavioral prediction (linear regression over 30-day ClickHouse time-series, scipy), and comparison analytics (Welch's t-test significance, per-metric diff reports). 5 PostgreSQL tables. No new Python packages required.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, grpcio 1.65+ (SimulationControllerClient), clickhouse-connect 0.8+ (behavioral history), scipy >= 1.13 (regression + t-test), numpy >= 1.26, redis-py 5.x async  
**Storage**: PostgreSQL 16 (5 tables) + Redis (simulation status cache `sim:status:{run_id}`) + ClickHouse (read-only: `execution_metrics_daily` from feature 020)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Kubernetes `platform-control` namespace, `simulation` runtime profile  
**Project Type**: Python modular monolith bounded context  
**Performance Goals**: Simulation status updates within 1s via WebSocket; twin creation < 30s (includes ClickHouse history fetch); behavioral prediction < 10s; comparison report < 15s  
**Constraints**: All async; no cross-boundary PostgreSQL access; SimulationControlService via gRPC only; ClickHouse used for behavioral reads only (no writes); isolation policy registered/deregistered per simulation lifecycle  
**Scale/Scope**: Up to 50 concurrent simulation runs per workspace; digital twins unbounded; behavioral predictions batched asynchronously

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| I. Modular Monolith | ✅ | New `simulation/` bounded context in control plane; already in repository structure |
| II. Go Reasoning Engine | ✅ | Not applicable — simulation coordination does not use reasoning engine |
| III. Dedicated Data Stores | ✅ | PostgreSQL (relational state) + Redis (status cache) + ClickHouse (behavioral history reads only) — each store used for its correct workload |
| IV. No Cross-Boundary DB Access | ✅ | Registry via RegistryServiceInterface; policy via PolicyServiceInterface; ClickHouse analytics reads are cross-context reads from the OLAP store (acceptable per platform pattern used in features 033, 034) |
| VII. Simulation Isolation | ✅ | This feature IS the simulation isolation layer; K8s-level isolation handled by SimulationControlService (feature 012); Python bounded context handles action-level interception and policy enforcement |
| All async | ✅ | All service, repository, router, gRPC, ClickHouse, and Redis calls are `async def` |

**New dependency justification**: None required. All dependencies already in the established stack.

**Post-Phase 1 re-check**: All design decisions comply. PolicyServiceInterface extension (two new methods for simulation-scoped bundle registration) is additive and non-breaking. ClickHouse read pattern matches features 033 and 034.

## Project Structure

### Documentation (this feature)

```text
specs/040-simulation-digital-twins/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-endpoints.md
│   └── service-interfaces.md
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   ├── main.py                               # Register simulation runtime profile
│   └── simulation/
│       ├── __init__.py
│       ├── models.py                         # 5 SQLAlchemy models
│       ├── schemas.py                        # Pydantic request/response schemas
│       ├── service.py                        # SimulationService + SimulationServiceInterface
│       ├── repository.py                     # Async DB + Redis status cache
│       ├── router.py                         # FastAPI router (/api/v1/simulations)
│       ├── events.py                         # Kafka publisher (simulation.events control-plane events)
│       ├── exceptions.py                     # SimulationError hierarchy
│       ├── dependencies.py                   # FastAPI DI: get_simulation_service
│       ├── coordination/
│       │   ├── __init__.py
│       │   └── runner.py                     # SimulationRunner: gRPC → SimulationControlService
│       ├── twins/
│       │   ├── __init__.py
│       │   └── snapshot.py                   # TwinSnapshotService: registry + ClickHouse snapshot
│       ├── isolation/
│       │   ├── __init__.py
│       │   └── enforcer.py                   # IsolationEnforcer: translate rules → policy bundle
│       ├── prediction/
│       │   ├── __init__.py
│       │   └── forecaster.py                 # BehavioralForecaster: ClickHouse + linear regression
│       └── comparison/
│           ├── __init__.py
│           └── analyzer.py                   # ComparisonAnalyzer: metric diff + Welch's t-test
│
├── migrations/versions/
│   └── 040_simulation_digital_twins.py       # All 5 PostgreSQL tables
│
└── tests/
    ├── unit/simulation/
    │   ├── test_simulation_runner.py
    │   ├── test_twin_snapshot.py
    │   ├── test_isolation_enforcer.py
    │   ├── test_behavioral_forecaster.py
    │   └── test_comparison_analyzer.py
    └── integration/simulation/
        ├── test_simulation_endpoints.py
        ├── test_twin_endpoints.py
        ├── test_isolation_policy_endpoints.py
        ├── test_prediction_endpoints.py
        └── test_comparison_endpoints.py
```

## Implementation Phases

### Phase 1 — Models, Schemas, Repository, Migration

**Goal**: All data models, Pydantic schemas, repository, and Alembic migration ready.

1. Create `models.py` — all 5 SQLAlchemy models per `data-model.md`; correct mixin order; JSONB columns; `simulation_runs` + `simulation_digital_twins` + `simulation_behavioral_predictions` + `simulation_isolation_policies` + `simulation_comparison_reports`; indexes and check constraints
2. Create `schemas.py` — Pydantic v2 schemas: `SimulationRunCreateRequest`, `SimulationRunResponse`, `DigitalTwinResponse`, `BehavioralPredictionResponse`, `SimulationIsolationPolicyCreateRequest`, `SimulationIsolationPolicyResponse`, `SimulationComparisonReportResponse`
3. Create `repository.py` — async CRUD for all 5 tables; Redis status cache: `set_status_cache(run_id, status_dict)`, `get_status_cache(run_id)`; cursor pagination
4. Create `exceptions.py` — `SimulationError`, `SimulationNotCancellableError` (409), `SimulationInfrastructureUnavailableError` (409), `IncompatibleComparisonError` (422), `InsufficientPredictionDataError` (200 with status field)
5. Create Alembic migration `040_simulation_digital_twins.py` — all 5 tables

---

### Phase 2 — Simulation Coordination + Digital Twins (US1 + US2)

**Goal**: Simulation runs created and coordinated via gRPC; digital twins snapshotted from registry with behavioral history from ClickHouse.

1. `coordination/runner.py` — `SimulationRunner.create(workspace_id, twin_configs, scenario_config, max_duration_seconds)`: call `SimulationControllerClient.create_simulation`; create `SimulationRun(status='provisioning')`; cache status in Redis; publish `simulation_run_created` event; `SimulationRunner.cancel(run_id)`: call `SimulationControllerClient.cancel_simulation`; update status; publish `simulation_run_cancelled` event
2. `twins/snapshot.py` — `TwinSnapshotService.create_twin(agent_fqn, workspace_id, revision_id)`: call `RegistryServiceInterface.get_agent_profile` + `get_agent_revision`; query ClickHouse `execution_metrics_daily` for 30-day history; compute behavioral summary (averages + trend direction via numpy diff); insert `DigitalTwin`; publish `twin_created` event; `TwinSnapshotService.modify_twin(twin_id, modifications)`: create new version with incremented `version`, set `parent_twin_id`; publish `twin_modified` event
3. Kafka consumer for `simulation.events` — receive `simulation_run_started`, `simulation_run_completed`, `simulation_run_failed`, `simulation_run_timeout` from SimulationControlService; update `SimulationRun.status` and `results` accordingly
4. `service.py` — `create_simulation_run`, `cancel_simulation_run`, `get_simulation_run`, `list_simulation_runs`, `create_digital_twin`, `modify_digital_twin`, `get_digital_twin`, `list_digital_twins` methods
5. `router.py` — simulation run endpoints (POST, GET, GET list, POST cancel) + twin endpoints (POST, GET, GET list, PATCH, GET versions)

---

### Phase 3 — Simulation Isolation Enforcement (US3)

**Goal**: Isolation policies created and enforced during simulation runs; actions blocked/stubbed; critical breaches halt simulation.

1. `isolation/enforcer.py` — `IsolationEnforcer.apply(simulation_run, policy)`: call `PolicyServiceInterface.register_simulation_policy_bundle` with translated rules (blocked actions → deny rules, stubbed actions → stub-response rules); store `bundle_fingerprint` on `SimulationRun`; `IsolationEnforcer.release(simulation_run)`: call `PolicyServiceInterface.deregister_simulation_policy_bundle`; `IsolationEnforcer.handle_breach(simulation_run, breach_event)`: if critical + `halt_on_critical_breach` → call `SimulationRunner.cancel`; publish `isolation_breach_detected` event; log to `SimulationRun.results.isolation_events_count`
2. Default strict policy: if no `isolation_policy_id` on simulation run and `SIMULATION_DEFAULT_STRICT_ISOLATION=True`, apply a system-generated policy blocking all external writes and stubbing all connector reads
3. `service.py` — `create_isolation_policy`, `get_isolation_policy`, `list_isolation_policies` methods
4. `router.py` — isolation policy endpoints (POST, GET, GET list)

---

### Phase 4 — Behavioral Prediction (US4)

**Goal**: Behavioral predictions generated from ClickHouse time-series with linear regression trend, confidence intervals, and condition modifier application.

1. `prediction/forecaster.py` — `BehavioralForecaster.forecast(twin_id, workspace_id, condition_modifiers)`: fetch behavioral history from ClickHouse for twin's `source_agent_fqn`; check minimum days (< 7 → update `BehavioralPrediction(status='insufficient_data')`); for each metric (quality_score, response_time_ms, error_rate): apply `scipy.stats.linregress` to 30-day values; compute confidence intervals from regression residuals; apply `condition_modifiers.load_factor` via linear scaling; classify trend: slope > 0.01 → "improving" (for quality) / "degrading" (for errors), |slope| < 0.01 → "stable"; set confidence_level based on R² value; update `BehavioralPrediction` with results; publish `prediction_completed` event
2. `service.py` — `create_behavioral_prediction`, `get_behavioral_prediction` methods
3. `router.py` — prediction endpoints (POST /twins/{id}/predict, GET /predictions/{id})
4. Background prediction worker: APScheduler task that processes `BehavioralPrediction(status='pending')` records

---

### Phase 5 — Comparison Analytics (US5)

**Goal**: Comparison reports generated with per-metric differences and Welch's t-test statistical significance.

1. `comparison/analyzer.py` — `ComparisonAnalyzer.analyze(primary_run_id, comparison_type, ...)`: validate compatibility (same agent set → compatible; mismatch → set `compatible=False`, populate `incompatibility_reasons`); fetch metric arrays from both runs' `results.execution_metrics`; for each metric: compute delta, direction (better/worse/unchanged based on metric semantics), Welch's t-test p-value via `scipy.stats.ttest_ind`; classify significance (p < 0.01 → "high", p < 0.05 → "medium", p >= 0.05 → "low"); set `overall_verdict`; for `prediction_vs_actual`: compare `predicted_metrics` with simulation actuals; compute `accuracy_pct` per metric; update `BehavioralPrediction.accuracy_report`; publish `comparison_completed` event
2. `service.py` — `create_comparison_report`, `get_comparison_report` methods
3. `router.py` — comparison endpoints (POST /{run_id}/compare, GET /comparisons/{id})

---

### Phase 6 — Tests, Linting, Type Checking

**Goal**: ≥95% coverage; mypy strict; ruff clean.

1. Unit tests — 5 test files with mocked service interfaces:
   - `test_simulation_runner.py`: mock `SimulationControllerClient`; test create/cancel/status update; test Redis cache; test `simulation_run_created` event
   - `test_twin_snapshot.py`: mock `RegistryServiceInterface` + ClickHouse; test config snapshot; test behavioral summary; test twin versioning (parent_twin_id set correctly)
   - `test_isolation_enforcer.py`: mock `PolicyServiceInterface`; test blocked action → bundle registration; test stubbed action → stub response; test critical breach → simulation cancelled; test default strict policy applied when none configured
   - `test_behavioral_forecaster.py`: synthetic 30-day metric series; test linear regression values; test confidence intervals; test trend classification (improving/degrading/stable); test insufficient_data for < 7 days; test load_factor modifier
   - `test_comparison_analyzer.py`: two synthetic metric arrays; test delta/direction/significance; test incompatible comparison (different agent sets); test prediction_vs_actual accuracy; test Welch's t-test significance classification
2. Integration tests — 5 test files with SQLite + in-memory Redis + mocked gRPC + mocked ClickHouse:
   - `test_simulation_endpoints.py`, `test_twin_endpoints.py`, `test_isolation_policy_endpoints.py`, `test_prediction_endpoints.py`, `test_comparison_endpoints.py`
3. Edge case tests: simulation infrastructure unavailable (409); twin from archived agent (warning in response); cancel already-completed simulation (409); comparison between incompatible configurations (422); prediction with partial ClickHouse data
4. Run coverage, close gaps, mypy strict, ruff
