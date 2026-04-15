# Implementation Plan: Scientific Discovery Orchestration

**Branch**: `039-scientific-discovery-orchestration` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/039-scientific-discovery-orchestration/spec.md`

## Summary

Build a greenfield `discovery/` bounded context in the Python control plane implementing: Elo-based hypothesis tournament ranking (Redis sorted sets, K=32), multi-agent hypothesis critique (5 structured dimensions), iterative generate-debate-evolve cycles with convergence detection, experiment design with governance validation and sandbox execution, Neo4j evidence provenance chains, and proximity-based hypothesis clustering (scipy hierarchical + Qdrant embeddings, APScheduler background task). No new Python packages required — all dependencies already in the stack.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, qdrant-client 1.12+ async gRPC, neo4j-python-driver 5.x async, grpcio 1.65+ (sandbox manager), scipy>=1.13 (clustering), numpy>=1.26, APScheduler 3.x  
**Storage**: PostgreSQL 16 (8 tables) + Redis sorted sets (`leaderboard:{session_id}`) + Neo4j 5.x (provenance graph) + Qdrant (discovery_hypotheses collection, 1536-dim Cosine)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Kubernetes `platform-control` namespace, `discovery` runtime profile  
**Project Type**: Python modular monolith bounded context  
**Performance Goals**: Discovery session start <5s; provenance query <5s; proximity clustering background (not user-blocking); Elo leaderboard updates after each tournament round (Redis O(log N))  
**Constraints**: All async; Elo updates protected by Redis lock; Neo4j provenance (local PostgreSQL fallback for tests); no cross-boundary DB access; sandbox experiments via gRPC only (Constitution VII)  
**Scale/Scope**: Up to 100 hypotheses per session; up to 50 active sessions per workspace; provenance graph unbounded (cursor-paginated traversal)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| I. Modular Monolith | ✅ | New `discovery/` bounded context in control plane |
| II. Go Reasoning Engine | ✅ | Discovery does NOT use the reasoning engine for GDE cycles — uses workflow execution engine instead; reasoning engine is for hot-path tree-of-thought, not multi-step orchestration |
| III. Dedicated Data Stores | ✅ | PostgreSQL (relational state) + Redis (Elo hot state) + Neo4j (provenance graph) + Qdrant (hypothesis embeddings) — each store used for its correct workload |
| IV. No Cross-Boundary DB Access | ✅ | Policy via PolicyServiceInterface; sandbox via gRPC SandboxManagerClient; workflow via WorkflowServiceInterface; no direct queries to other bounded context tables |
| VII. Simulation Isolation | ✅ | Experiments execute in sandbox manager (port 50053); no direct subprocess or production namespace access |
| All async | ✅ | All service, repository, router, Neo4j, Qdrant, Redis, and gRPC calls are `async def` |

**New dependency justification**: None required. `scipy>=1.13` and `numpy>=1.26` were added in feature 037; `qdrant-client`, `neo4j-python-driver`, `redis-py`, `grpcio`, `APScheduler` are all in the established tech stack.

**Post-Phase 1 re-check**: All design decisions comply. Redis sorted set Elo pattern matches existing leaderboard pattern. Neo4j provenance nodes carry `workspace_id` for cross-workspace isolation. Qdrant payload indexes on `workspace_id` prevent cross-workspace vector leakage.

## Project Structure

### Documentation (this feature)

```text
specs/039-scientific-discovery-orchestration/
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
│   ├── main.py                           # Register discovery runtime profile
│   └── discovery/
│       ├── __init__.py
│       ├── models.py                     # 8 SQLAlchemy models
│       ├── schemas.py                    # Pydantic request/response schemas
│       ├── service.py                    # DiscoveryService + DiscoveryServiceInterface
│       ├── repository.py                 # Async DB + Redis sorted set access
│       ├── router.py                     # FastAPI router (/api/v1/discovery)
│       ├── events.py                     # Kafka publisher (discovery.events)
│       ├── exceptions.py                 # DiscoveryError hierarchy
│       ├── dependencies.py               # FastAPI DI: get_discovery_service
│       ├── tournament/
│       │   ├── __init__.py
│       │   ├── elo.py                    # EloRatingEngine: K-factor calc + Redis ZADD
│       │   └── comparator.py             # TournamentComparator: pairwise dispatch
│       ├── critique/
│       │   ├── __init__.py
│       │   └── evaluator.py              # CritiqueEvaluator: multi-agent + aggregation
│       ├── gde/
│       │   ├── __init__.py
│       │   └── cycle.py                  # GDECycleOrchestrator: generate→critique→debate→refine
│       ├── experiment/
│       │   ├── __init__.py
│       │   └── designer.py               # ExperimentDesigner: plan + governance + sandbox
│       ├── provenance/
│       │   ├── __init__.py
│       │   └── graph.py                  # ProvenanceGraph: Neo4j write/query
│       └── proximity/
│           ├── __init__.py
│           ├── embeddings.py             # HypothesisEmbedder: httpx → Qdrant upsert
│           └── clustering.py             # ProximityClustering: scipy + gap detection + APScheduler
│
├── migrations/versions/
│   └── 039_scientific_discovery.py       # All 8 PostgreSQL tables
│
└── tests/
    ├── unit/discovery/
    │   ├── test_elo_engine.py
    │   ├── test_tournament_comparator.py
    │   ├── test_critique_evaluator.py
    │   ├── test_gde_cycle.py
    │   ├── test_experiment_designer.py
    │   ├── test_provenance_graph.py
    │   ├── test_hypothesis_embedder.py
    │   └── test_proximity_clustering.py
    └── integration/discovery/
        ├── test_session_endpoints.py
        ├── test_hypothesis_endpoints.py
        ├── test_tournament_endpoints.py
        ├── test_experiment_endpoints.py
        ├── test_provenance_endpoints.py
        └── test_proximity_endpoints.py
```

## Implementation Phases

### Phase 1 — Models, Schemas, Repository, Migration

**Goal**: All data models, Pydantic schemas, repository, and Alembic migration ready.

1. Create `models.py` — all 8 SQLAlchemy models per `data-model.md`; correct mixin order; JSONB columns; `discovery_sessions` + `discovery_hypotheses` + `discovery_critiques` + `discovery_tournament_rounds` + `discovery_elo_scores` + `discovery_experiments` + `discovery_gde_cycles` + `discovery_hypothesis_clusters`; indexes and check constraints
2. Create `schemas.py` — Pydantic v2 schemas for all API sections; `confidence` ∈ [0.0, 1.0]; `k_factor` > 0; `convergence_threshold` ∈ (0.0, 1.0); `max_cycles` ∈ [1, 100]
3. Create `repository.py` — all async CRUD; Redis sorted set methods: `zadd_elo`, `zrevrange_leaderboard`, `zscore_hypothesis`, `zrem_hypothesis`; cursor pagination for lists
4. Create `exceptions.py` — `DiscoveryError`, `InsufficientHypothesesError` (412), `SessionAlreadyRunningError` (409), `ExperimentNotApprovedError` (409), `ProvenanceQueryError` (500)
5. Create Alembic migration `039_scientific_discovery.py` — all 8 tables

---

### Phase 2 — Hypothesis Generation + Tournament Ranking (US1)

**Goal**: Hypotheses generated and ranked via Elo tournament; leaderboard queryable via Redis.

1. `tournament/elo.py` — `EloRatingEngine`: `compute_new_ratings(elo_a, elo_b, outcome, k_factor) -> (new_a, new_b)` (pure math); `update_redis_leaderboard(session_id, hypothesis_id, new_score)`: async ZADD; `get_leaderboard(session_id, limit) -> list[LeaderboardEntry]`: ZREVRANGE with scores; `persist_elo_score(hypothesis_id, session_id, new_score, result)`: upsert `discovery_elo_scores` with history append
2. `tournament/comparator.py` — `TournamentComparator.run_round(session_id, hypothesis_pairs)`: for each pair, dispatch comparison via `WorkflowServiceInterface.create_execution` with both hypotheses as context; await results; call `EloRatingEngine` with outcomes; write `TournamentRound`; publish `tournament_round_completed` event
3. `service.py` — `start_session`, `run_tournament_round` methods; validate min 2 active hypotheses; handle bye for odd count
4. `router.py` — session CRUD endpoints, `GET /sessions/{id}/leaderboard`, `GET /sessions/{id}/hypotheses`

---

### Phase 3 — Multi-Agent Critique (US2)

**Goal**: Multiple independent reviewer agents evaluate hypotheses along 5 structured dimensions.

1. `critique/evaluator.py` — `CritiqueEvaluator.critique_hypothesis(hypothesis, reviewer_agents)`: dispatch critique requests to each reviewer agent via workflow execution; await structured responses; parse into `HypothesisCritiqueCreate` per reviewer; `aggregate_critiques(hypothesis_id)`: compute per-dimension averages, detect disagreements (std dev > 0.3 on any dimension); write aggregated `HypothesisCritique` with `is_aggregated=True`; publish `critique_completed` event
2. `service.py` — `submit_for_critique(hypothesis_id, workspace_id)` method
3. `router.py` — `GET /hypotheses/{id}/critiques` endpoint

---

### Phase 4 — Generate-Debate-Evolve Cycles (US3)

**Goal**: Full iterative cycle: generate → critique → tournament → debate → refine → re-rank.

1. `gde/cycle.py` — `GDECycleOrchestrator.run_cycle(session_id)`: create `GDECycle(status='running')`; (1) dispatch generation agents via `WorkflowServiceInterface`; (2) wait for hypotheses; (3) run critiques; (4) run tournament round; (5) dispatch debate agents with top hypothesis pairs; (6) wait for debate results; (7) dispatch refinement agents; (8) update cycle `debate_record`, `refinement_count`; (9) check convergence: compare current top Elo with previous cycle; set `converged=True` if delta < threshold for N consecutive rounds; update session status; publish `cycle_completed` or `session_converged` event
2. `service.py` — `run_gde_cycle(session_id)`, `halt_session(session_id, reason)` methods
3. `router.py` — `POST /sessions/{id}/cycle` (202 async), `POST /sessions/{id}/halt`, `GET /cycles/{id}` endpoints

---

### Phase 5 — Experiment Design + Execution (US4)

**Goal**: Experiment plan generated by agent, governance-validated, sandbox-executed; results linked to hypothesis.

1. `experiment/designer.py` — `ExperimentDesigner.design(hypothesis, workspace_id)`: dispatch experiment design workflow to a design agent via `WorkflowServiceInterface`; await structured plan (objective, methodology, expected outcomes, required data, resources, success criteria, code); insert `DiscoveryExperiment(governance_status='pending')`; call `PolicyServiceInterface.evaluate_conformance` for governance check; update `governance_status` (approved/rejected + violations); publish `experiment_designed` event
2. `experiment/designer.py` — `ExperimentDesigner.execute(experiment_id)`: check `governance_status='approved'`; call `SandboxManagerClient.execute_code(template='python3.12', code=plan.code, timeout=DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS)`; update `execution_status` and `results`; write `EvidenceNode` in Neo4j (`SUPPORTS`/`CONTRADICTS`/`INCONCLUSIVE_FOR` based on results interpretation); if successful, call `EloRatingEngine.apply_evidence_bonus(hypothesis_id)`; publish `experiment_completed` event
3. `service.py` — `design_experiment`, `execute_experiment` methods
4. `router.py` — experiment endpoints (design, get, execute)

---

### Phase 6 — Evidence Provenance Graph (US5)

**Goal**: Full Neo4j provenance chain queryable from any hypothesis.

1. `provenance/graph.py` — `ProvenanceGraph.write_generation_event(hypothesis, agent_fqn)`: create `HypothesisNode`, `DiscoveryAgentNode`, `GENERATED_BY` edge; `write_refinement(new_hypothesis, source_hypothesis, cycle_num)`: `REFINED_FROM` edge; `write_evidence(evidence, hypothesis, relationship_type)`: `EvidenceNode` + typed edge; `query_provenance(hypothesis_id, workspace_id, depth)`: Cypher MATCH traversal returning nodes + edges up to `depth` hops; local mode fallback via PostgreSQL graph tables
2. `service.py` — `get_hypothesis_provenance(hypothesis_id, workspace_id, depth)` method
3. `router.py` — `GET /hypotheses/{id}/provenance` endpoint

---

### Phase 7 — Proximity Clustering (US6)

**Goal**: Hypothesis embeddings computed, clustered via scipy; gaps and over-explored areas identified; generation bias context produced.

1. `proximity/embeddings.py` — `HypothesisEmbedder.embed_hypothesis(hypothesis)`: POST hypothesis text to `settings.memory.embedding_api_url`; upsert to Qdrant `discovery_hypotheses` collection; update `hypothesis.qdrant_point_id`; `fetch_session_embeddings(session_id, workspace_id)`: retrieve all active hypothesis embeddings for a session via Qdrant payload filter
2. `proximity/clustering.py` — `ProximityClustering.compute(session_id, workspace_id)`: fetch embeddings; compute pairwise cosine distance matrix via `scipy.spatial.distance.cdist`; apply `scipy.cluster.hierarchy.fclusterdata` with distance threshold `DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD`; classify clusters (over_explored / gap / normal); write `HypothesisCluster` rows; update `hypothesis.cluster_id`; detect gap regions (areas far from all cluster centroids); produce `LandscapeContext` with gap descriptions for generation bias; publish `proximity_computed` event
3. `proximity/clustering.py` — `proximity_clustering_task()` APScheduler function: consume `discovery.cycle_completed` Kafka event; call `ProximityClustering.compute(session_id, workspace_id)`
4. `service.py` — `get_proximity_clusters`, `trigger_proximity_computation` methods
5. `router.py` — `GET /sessions/{id}/clusters`, `POST /sessions/{id}/compute-proximity` endpoints

---

### Phase 8 — Tests, Linting, Type Checking

**Goal**: ≥95% coverage; mypy strict; ruff clean.

1. Unit tests for all sub-modules with mock service interfaces (8 test files)
2. `test_elo_engine.py` — deterministic tests with known Elo inputs/outputs; test Redis mock ZADD/ZREVRANGE
3. `test_proximity_clustering.py` — synthetic 20-hypothesis embedding set; test cluster count, over-explored detection, gap detection
4. Integration tests for all endpoint groups (6 test files); Neo4j in local mode fallback
5. Edge case tests: 2-hypothesis tournament (minimum); duplicate hypothesis merge; experiment governance rejection; convergence at cycle 1; empty session provenance query; clustering with <3 hypotheses (skip, return low_data status)
6. Run coverage, close gaps, mypy strict, ruff
