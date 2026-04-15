# Quickstart: Scientific Discovery Orchestration

## Prerequisites

- Python 3.12+, PostgreSQL 16, Redis 7, Neo4j 5.x, Qdrant, Kafka 3.7+
- Existing bounded contexts operational: policy (028), workflow execution (029), sandbox-manager (satellite service at port 50053)
- Alembic migration chain up to 038 applied
- `discovery_hypotheses` Qdrant collection will be auto-created on first run

## New Dependencies

No new Python packages required. All dependencies already in the tech stack (from features 033, 037):
- `scipy>=1.13` — proximity clustering (already added in feature 037)
- `numpy>=1.26` — embedding distance matrix (already added in feature 037)
- `qdrant-client[grpc] 1.12+` — hypothesis embeddings (already in stack)
- `neo4j-python-driver 5.x` — provenance graph (already in stack)
- `redis-py 5.x` — Elo sorted sets (already in stack)

## Running the Context

```bash
cd apps/control-plane

# Apply migration
make migrate

# Run with discovery profile
RUNTIME_PROFILE=discovery python -m platform.main
```

The `discovery` runtime profile starts:
1. FastAPI app with `/api/v1/discovery` router mounted
2. Kafka producer for `discovery.events` topic
3. Kafka consumer for `workflow.runtime` (execution completion events → GDE cycle state updates)
4. APScheduler: `proximity_clustering_task()` — triggered by `cycle_completed` event, computes embeddings + clusters

## Running Tests

```bash
cd apps/control-plane
pytest tests/unit/discovery/ -v
pytest tests/integration/discovery/ -v
```

Integration tests use:
- SQLite in-memory + local PostgreSQL graph tables (Neo4j fallback mode)
- In-memory dict for Redis sorted sets
- Qdrant local mode (in-process)
- Mock SandboxManagerClient and WorkflowServiceInterface

## Project Structure

```text
apps/control-plane/src/platform/discovery/
├── __init__.py
├── models.py              # 8 PostgreSQL tables
├── schemas.py             # Pydantic request/response schemas
├── service.py             # DiscoveryService (main orchestration)
├── repository.py          # Database access (PostgreSQL + Redis sorted sets)
├── router.py              # FastAPI router (/api/v1/discovery)
├── events.py              # Kafka publisher (discovery.events)
├── exceptions.py          # DiscoveryError hierarchy
├── dependencies.py        # FastAPI DI
├── tournament/
│   ├── __init__.py
│   ├── elo.py             # EloRatingEngine: K-factor calculation, Redis ZADD
│   └── comparator.py      # TournamentComparator: pairwise comparison dispatch
├── critique/
│   ├── __init__.py
│   └── evaluator.py       # CritiqueEvaluator: multi-agent critique orchestration + aggregation
├── gde/
│   ├── __init__.py
│   └── cycle.py           # GDECycleOrchestrator: full cycle with convergence check
├── experiment/
│   ├── __init__.py
│   └── designer.py        # ExperimentDesigner: plan generation + governance + sandbox
├── provenance/
│   ├── __init__.py
│   └── graph.py           # ProvenanceGraph: Neo4j write/query interface
└── proximity/
    ├── __init__.py
    ├── embeddings.py       # HypothesisEmbedder: compute + upsert to Qdrant
    └── clustering.py       # ProximityClustering: APScheduler task + DBSCAN + gap detection

migrations/versions/
└── 039_scientific_discovery.py   # All 8 PostgreSQL tables

tests/unit/discovery/
├── test_elo_engine.py
├── test_tournament_comparator.py
├── test_critique_evaluator.py
├── test_gde_cycle.py
├── test_experiment_designer.py
├── test_provenance_graph.py
├── test_hypothesis_embedder.py
└── test_proximity_clustering.py

tests/integration/discovery/
├── test_session_endpoints.py
├── test_hypothesis_endpoints.py
├── test_tournament_endpoints.py
├── test_experiment_endpoints.py
├── test_provenance_endpoints.py
└── test_proximity_endpoints.py
```

## Key Configuration (PlatformSettings additions)

```python
# Discovery
DISCOVERY_ELO_K_FACTOR: int = 32
DISCOVERY_ELO_DEFAULT_SCORE: float = 1000.0
DISCOVERY_CONVERGENCE_THRESHOLD: float = 0.05       # 5% change threshold
DISCOVERY_CONVERGENCE_STABLE_ROUNDS: int = 2         # Rounds without change to converge
DISCOVERY_MAX_CYCLES_DEFAULT: int = 10
DISCOVERY_MIN_HYPOTHESES: int = 3

# Proximity clustering
DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD: float = 0.3  # Cosine distance for same cluster
DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE: int = 5
DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY: float = 0.85
DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD: float = 0.5
DISCOVERY_QDRANT_COLLECTION: str = "discovery_hypotheses"
DISCOVERY_EMBEDDING_VECTOR_SIZE: int = 1536

# Experiments
DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS: int = 120
```
