# Quickstart: AgentOps Lifecycle Management

## Prerequisites

- Python 3.12+, PostgreSQL 16, ClickHouse 24.3+, Redis 7, Kafka 3.7+
- Existing bounded contexts operational: trust (032), evaluation (034), fleet (033), analytics (020)
- Alembic migration chain up to 036 applied

## New Dependencies

Add to `apps/control-plane/pyproject.toml`:
```toml
"numpy>=1.26",    # Required by scipy for array operations
"scipy>=1.13",    # t-test, Mann-Whitney U for regression detection
```

## Running the Context

```bash
cd apps/control-plane

# Apply migration
make migrate

# Run with agentops profile (includes APScheduler background tasks)
RUNTIME_PROFILE=agentops python -m platform.main
```

The `agentops` runtime profile starts:
1. FastAPI app with `/api/v1/agentops` router mounted
2. APScheduler: health score computation task (configurable interval, default 15min)
3. APScheduler: canary monitoring task (every 5 minutes, scans active canaries)
4. APScheduler: retirement grace period scanner (every 1 hour)
5. APScheduler: recertification grace period scanner (every 1 hour)
6. Kafka consumer: `evaluation.events` → behavioral version ingestion + regression trigger

## Running Tests

```bash
cd apps/control-plane
pytest tests/unit/agentops/ -v
pytest tests/integration/agentops/ -v
```

Integration tests use:
- SQLite in-memory (local mode fallback)
- In-process asyncio queue for Kafka
- In-process dict for Redis
- Go reasoning engine mock (local subprocess)

## Project Structure

```
apps/control-plane/src/platform/agentops/
├── __init__.py
├── models.py             # 8 PostgreSQL tables (see data-model.md)
├── schemas.py            # Pydantic request/response schemas
├── service.py            # AgentOpsService (main orchestration)
├── repository.py         # Database access
├── router.py             # FastAPI router (/api/v1/agentops)
├── events.py             # Kafka event definitions + AgentOpsEventPublisher
├── exceptions.py         # AgentOpsError, CanaryConflictError, etc.
├── dependencies.py       # FastAPI dependency injection
├── health/
│   ├── scorer.py         # HealthScorer: compute composite score
│   └── dimensions.py     # Per-dimension data fetchers
├── regression/
│   ├── detector.py       # RegressionDetector: compare revision vs baseline
│   └── statistics.py     # StatisticalComparator: t-test / Mann-Whitney selection
├── cicd/
│   └── gate.py           # CiCdGate: run all 5 gates concurrently
├── canary/
│   ├── manager.py        # CanaryManager: start/promote/rollback, Redis writes
│   └── monitor.py        # CanaryMonitor: APScheduler task, metric polling
├── retirement/
│   └── workflow.py       # RetirementManager: initiation, grace period, deactivation
├── governance/
│   ├── triggers.py       # GovernanceTriggerProcessor: Kafka consumer callbacks
│   └── grace_period.py   # GracePeriodScanner: APScheduler task
└── adaptation/
    ├── pipeline.py        # AdaptationPipeline: orchestrate proposal → test → promote
    └── analyzer.py        # BehavioralAnalyzer: rule-based signal detection

migrations/versions/
└── 037_agentops_lifecycle.py   # All 8 PostgreSQL tables + ClickHouse DDL

tests/unit/agentops/
├── test_health_scorer.py
├── test_regression_detector.py
├── test_statistics.py
├── test_cicd_gate.py
├── test_canary_manager.py
├── test_retirement_workflow.py
├── test_governance_triggers.py
└── test_adaptation_analyzer.py

tests/integration/agentops/
├── test_health_endpoints.py
├── test_regression_endpoints.py
├── test_gate_endpoints.py
├── test_canary_endpoints.py
├── test_retirement_endpoints.py
└── test_adaptation_endpoints.py
```

## Key Configuration (PlatformSettings additions)

```python
# Health scoring
AGENTOPS_HEALTH_SCORING_INTERVAL_MINUTES: int = 15
AGENTOPS_DEFAULT_MIN_SAMPLE_SIZE: int = 50
AGENTOPS_DEFAULT_ROLLING_WINDOW_DAYS: int = 30

# Regression detection
AGENTOPS_REGRESSION_SIGNIFICANCE_THRESHOLD: float = 0.05
AGENTOPS_REGRESSION_NORMALITY_SAMPLE_MIN: int = 30

# Canary
AGENTOPS_CANARY_MONITOR_INTERVAL_MINUTES: int = 5
AGENTOPS_CANARY_MAX_TRAFFIC_PCT: int = 50

# Retirement
AGENTOPS_RETIREMENT_GRACE_PERIOD_DAYS: int = 14
AGENTOPS_RETIREMENT_CRITICAL_INTERVALS: int = 5

# Governance
AGENTOPS_RECERTIFICATION_GRACE_PERIOD_DAYS: int = 7
```
