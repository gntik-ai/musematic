# Quickstart: Simulation and Digital Twins

## Prerequisites

- Python 3.12+, PostgreSQL 16, Redis 7, ClickHouse 24.3+, Kafka 3.7+
- Existing bounded contexts operational: registry (021), policy (028), simulation-controller satellite (012, port 50055)
- Alembic migration chain up to 039 applied
- ClickHouse `execution_metrics_daily` materialized view available (from feature 020)

## New Dependencies

No new Python packages required. All dependencies already in the tech stack:
- `grpcio 1.65+` — SimulationControllerClient calls (already in stack, feature 012)
- `clickhouse-connect 0.8+` — behavioral history queries (already in stack, feature 020)
- `scipy >= 1.13` — linear regression for prediction + Welch's t-test for comparison (already in stack, features 037, 039)
- `numpy >= 1.26` — metric arrays (already in stack, feature 037)
- `redis-py 5.x` async — simulation status cache (already in stack)

## Running the Context

```bash
cd apps/control-plane

# Apply migration
make migrate

# Run with simulation profile
RUNTIME_PROFILE=simulation python -m platform.main
```

The `simulation` runtime profile starts:
1. FastAPI app with `/api/v1/simulations` router mounted
2. Kafka producer for `simulation.events` topic (control-plane events)
3. Kafka consumer for `simulation.events` (to receive status updates from SimulationControlService)
4. Background task: `prediction_worker()` — processes pending behavioral predictions asynchronously

## Running Tests

```bash
cd apps/control-plane
pytest tests/unit/simulation/ -v
pytest tests/integration/simulation/ -v
```

Integration tests use:
- SQLite in-memory (PostgreSQL fallback)
- SQLite aggregate queries (ClickHouse fallback)
- In-memory dict for Redis
- Mock `SimulationControllerClient` and `PolicyServiceInterface`
- Mock `RegistryServiceInterface`

## Project Structure

```text
apps/control-plane/src/platform/simulation/
├── __init__.py
├── models.py              # 5 PostgreSQL tables
├── schemas.py             # Pydantic request/response schemas
├── service.py             # SimulationService (orchestration)
├── repository.py          # Database access (PostgreSQL + Redis)
├── router.py              # FastAPI router (/api/v1/simulations)
├── events.py              # Kafka publisher (simulation.events)
├── exceptions.py          # SimulationError hierarchy
├── dependencies.py        # FastAPI DI
├── coordination/
│   ├── __init__.py
│   └── runner.py          # SimulationRunner: gRPC to SimulationControlService
├── twins/
│   ├── __init__.py
│   └── snapshot.py        # TwinSnapshotService: registry config + ClickHouse behavioral history
├── isolation/
│   ├── __init__.py
│   └── enforcer.py        # IsolationEnforcer: translate policy rules → enforcement bundle
├── prediction/
│   ├── __init__.py
│   └── forecaster.py      # BehavioralForecaster: ClickHouse time-series + linear regression
└── comparison/
    ├── __init__.py
    └── analyzer.py        # ComparisonAnalyzer: metric diff + Welch's t-test significance

migrations/versions/
└── 040_simulation_digital_twins.py   # All 5 PostgreSQL tables

tests/unit/simulation/
├── test_simulation_runner.py
├── test_twin_snapshot.py
├── test_isolation_enforcer.py
├── test_behavioral_forecaster.py
└── test_comparison_analyzer.py

tests/integration/simulation/
├── test_simulation_endpoints.py
├── test_twin_endpoints.py
├── test_isolation_policy_endpoints.py
├── test_prediction_endpoints.py
└── test_comparison_endpoints.py
```

## Key Configuration (PlatformSettings additions)

```python
# Simulation
SIMULATION_MAX_DURATION_SECONDS: int = 1800          # 30 minutes default
SIMULATION_BEHAVIORAL_HISTORY_DAYS: int = 30          # Days of ClickHouse history for prediction
SIMULATION_MIN_PREDICTION_HISTORY_DAYS: int = 7       # Minimum days to attempt prediction
SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA: float = 0.05  # Welch's t-test alpha
SIMULATION_DEFAULT_STRICT_ISOLATION: bool = True       # Apply strict policy if none configured
```
