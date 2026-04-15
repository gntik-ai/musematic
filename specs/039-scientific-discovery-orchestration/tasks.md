---
description: "Task list for Scientific Discovery Orchestration"
---

# Tasks: Scientific Discovery Orchestration

**Input**: Design documents from `specs/039-scientific-discovery-orchestration/`
**Branch**: `039-scientific-discovery-orchestration`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/ ✅, research.md ✅, quickstart.md ✅

**Tests**: Included — SC-008 requires ≥95% line coverage for all discovery modules.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: User story this task belongs to (US1–US7)
- File paths are absolute from repo root

---

## Phase 1: Setup

**Purpose**: Create the `discovery/` bounded context skeleton and register the runtime profile.

- [X] T001 Create `discovery/` package skeleton — all `__init__.py` files for `apps/control-plane/src/platform/discovery/`, `tournament/`, `critique/`, `gde/`, `experiment/`, `provenance/`, `proximity/`
- [X] T002 [P] Add `discovery` runtime profile entrypoint in `apps/control-plane/src/platform/main.py` — mount `/api/v1/discovery` router, start Kafka consumer for `workflow.runtime`, register APScheduler `proximity_clustering_task`
- [X] T003 [P] Add discovery PlatformSettings fields (`DISCOVERY_ELO_K_FACTOR`, `DISCOVERY_ELO_DEFAULT_SCORE`, `DISCOVERY_CONVERGENCE_THRESHOLD`, `DISCOVERY_CONVERGENCE_STABLE_ROUNDS`, `DISCOVERY_MAX_CYCLES_DEFAULT`, `DISCOVERY_MIN_HYPOTHESES`, `DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD`, `DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE`, `DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY`, `DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD`, `DISCOVERY_QDRANT_COLLECTION`, `DISCOVERY_EMBEDDING_VECTOR_SIZE`, `DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS`) in `apps/control-plane/src/platform/common/settings.py`
- [X] T004 [P] Add `execute_code` stub method to `apps/control-plane/src/platform/common/clients/sandbox_manager.py` — accepts `template: str`, `code: str`, `workspace_id: UUID`, `timeout_seconds: int`; returns `SandboxExecutionResult` with `execution_id`, `status`, `stdout`, `stderr`, `exit_code`, `artifacts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All shared data models, schemas, repository, exceptions, events, and DI must be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `apps/control-plane/src/platform/discovery/exceptions.py` — `DiscoveryError` base (500), `InsufficientHypothesesError` (412), `SessionAlreadyRunningError` (409), `ExperimentNotApprovedError` (409), `ProvenanceQueryError` (500)
- [X] T006 Create `apps/control-plane/src/platform/discovery/models.py` — all 8 SQLAlchemy models with correct mixin order (`Base`, `UUIDMixin`, `TimestampMixin`, `WorkspaceScopedMixin`): `DiscoverySession`, `Hypothesis`, `HypothesisCritique`, `TournamentRound`, `EloScore`, `DiscoveryExperiment`, `GDECycle`, `HypothesisCluster`; all JSONB columns, indexes, CheckConstraints, and UniqueConstraints per data-model.md
- [X] T007 [P] Create `apps/control-plane/src/platform/discovery/schemas.py` — Pydantic v2 schemas for all API sections: `DiscoverySessionCreateRequest`, `DiscoverySessionResponse`, `HypothesisResponse`, `HypothesisCritiqueResponse`, `LeaderboardEntryResponse`, `TournamentRoundResponse`, `GDECycleResponse`, `DiscoveryExperimentResponse`, `ProvenanceGraphResponse`, `HypothesisClusterResponse`; validators: `confidence` ∈ [0.0, 1.0], `k_factor` > 0, `convergence_threshold` ∈ (0.0, 1.0), `max_cycles` ∈ [1, 100]
- [X] T008 Create `apps/control-plane/src/platform/discovery/repository.py` — all async CRUD for 8 tables using `AsyncSession`; Redis sorted set methods: `zadd_elo(session_id, hypothesis_id, score)`, `zrevrange_leaderboard(session_id, limit)`, `zscore_hypothesis(session_id, hypothesis_id)`, `zrem_hypothesis(session_id, hypothesis_id)`; cursor pagination for all list queries using UUID cursor pattern
- [X] T009 Create `apps/control-plane/migrations/versions/039_scientific_discovery.py` — Alembic migration creating all 8 tables in dependency order: `discovery_sessions` → `discovery_hypotheses` → `discovery_critiques` → `discovery_tournament_rounds` → `discovery_elo_scores` → `discovery_experiments` → `discovery_gde_cycles` → `discovery_hypothesis_clusters`; all indexes and constraints
- [X] T010 [P] Create `apps/control-plane/src/platform/discovery/events.py` — Kafka publisher for `discovery.events` topic; async publish methods for all 10 event types: `session_started`, `hypothesis_generated`, `critique_completed`, `tournament_round_completed`, `cycle_completed`, `session_converged`, `session_halted`, `experiment_designed`, `experiment_completed`, `proximity_computed`; key: `session_id`
- [X] T011 [P] Create `apps/control-plane/src/platform/discovery/dependencies.py` — FastAPI DI: `get_discovery_service` using `Depends`; inject `AsyncSession`, `AsyncRedis`, `DiscoveryRepository`, and downstream service interfaces
- [X] T012 Create `apps/control-plane/src/platform/discovery/service.py` — `DiscoveryServiceInterface` protocol + `DiscoveryService` skeleton with constructor accepting repository, redis, kafka, workflow_service, policy_service, sandbox_client; stub methods to be filled per user story phase

**Checkpoint**: Foundation ready — all 8 tables migrated, schemas defined, repository wired; user story implementation can now proceed.

---

## Phase 3: User Story 1 — Generate and Rank Hypotheses via Tournament (Priority: P1) 🎯 MVP

**Goal**: Discovery sessions created; generation agents dispatch hypotheses; pairwise tournament runs with Elo ranking; leaderboard queryable via Redis.

**Independent Test**: POST /api/v1/discovery/sessions → start session. POST /sessions/{id}/cycle → generation agents produce ≥3 hypotheses. GET /sessions/{id}/leaderboard → hypotheses ordered by Elo score with win/loss/draw counts.

### Tests for US1

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T013 [P] [US1] Write unit tests for `EloRatingEngine` in `apps/control-plane/tests/unit/discovery/test_elo_engine.py` — deterministic tests: known Elo inputs/outputs for win/loss/draw; test `compute_new_ratings` symmetry (a+b sum conserved for draw); test K=32 formula; mock `AsyncRedis` ZADD/ZREVRANGE for `update_redis_leaderboard` and `get_leaderboard`; test Redis lock acquisition for batch update
- [X] T014 [P] [US1] Write unit tests for `TournamentComparator` in `apps/control-plane/tests/unit/discovery/test_tournament_comparator.py` — mock `WorkflowServiceInterface.create_execution`; test pairwise dispatch for 4-hypothesis set (6 pairs); test bye for odd count (5 hypotheses → 2 pairs + 1 bye); test `TournamentRound` row written; test `tournament_round_completed` event published

### Implementation for US1

- [X] T015 [P] [US1] Implement `EloRatingEngine` in `apps/control-plane/src/platform/discovery/tournament/elo.py` — `compute_new_ratings(elo_a, elo_b, outcome, k_factor) -> (float, float)` (pure, no I/O); `update_redis_leaderboard(session_id, hypothesis_id, new_score)`: async ZADD under `lock:discovery:elo:{session_id}` using `lock_acquire.lua`; `get_leaderboard(session_id, limit) -> list[LeaderboardEntry]`: ZREVRANGE with scores; `persist_elo_score(hypothesis_id, session_id, new_score, result)`: upsert `discovery_elo_scores` with `score_history` append
- [X] T016 [US1] Implement `TournamentComparator` in `apps/control-plane/src/platform/discovery/tournament/comparator.py` — `run_round(session_id, hypothesis_pairs)`: dispatch each pair via `WorkflowServiceInterface.create_execution` with both hypothesis texts as context; await results; map to `outcome`; call `EloRatingEngine.compute_new_ratings`; batch `update_redis_leaderboard` under Elo lock; write `TournamentRound`; publish `tournament_round_completed` event
- [X] T017 [US1] Add `start_session`, `run_tournament_round` to `apps/control-plane/src/platform/discovery/service.py` — `start_session`: create `DiscoverySession`, publish `session_started`; `run_tournament_round`: validate ≥2 active hypotheses (raise `InsufficientHypothesesError` otherwise), build pairs, handle bye for odd count, delegate to `TournamentComparator`
- [X] T018 [US1] Add session CRUD endpoints and tournament endpoints to `apps/control-plane/src/platform/discovery/router.py` — `POST /sessions` (201), `GET /sessions/{id}`, `GET /sessions` (cursor-paginated), `GET /sessions/{id}/leaderboard`, `GET /sessions/{id}/hypotheses` (cursor-paginated with `order_by=elo_desc|created_at`), `GET /sessions/{id}/tournament-rounds`
- [X] T019 [P] [US1] Write integration tests for session endpoints in `apps/control-plane/tests/integration/discovery/test_session_endpoints.py` — create session, get session, list sessions with status filter; SQLite in-memory + in-memory Redis dict
- [X] T020 [P] [US1] Write integration tests for tournament and hypothesis endpoints in `apps/control-plane/tests/integration/discovery/test_tournament_endpoints.py` and `test_hypothesis_endpoints.py` — run_round with mocked WorkflowServiceInterface; verify Elo updates; verify leaderboard ordering

**Checkpoint**: US1 independently testable — session creation, tournament execution, and leaderboard all functional.

---

## Phase 4: User Story 2 — Multi-Agent Critique of Hypotheses (Priority: P1)

**Goal**: Multiple independent reviewer agents evaluate each hypothesis across 5 structured dimensions; critiques aggregated with inter-reviewer disagreement detection.

**Independent Test**: Generate 3 hypotheses. POST critique → confirm structured evaluations from ≥2 agents with 5-dimension scores. GET critiques → confirm aggregated composite with disagreement flags.

### Tests for US2

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T021 [P] [US2] Write unit tests for `CritiqueEvaluator` in `apps/control-plane/tests/unit/discovery/test_critique_evaluator.py` — mock `WorkflowServiceInterface` returning structured critique JSON; test 5-dimension parsing; test `aggregate_critiques` per-dimension averaging; test disagreement detection (std dev > 0.3 on any dimension); test `is_aggregated=True` row written; test `critique_completed` event published

### Implementation for US2

- [X] T022 [P] [US2] Implement `CritiqueEvaluator` in `apps/control-plane/src/platform/discovery/critique/evaluator.py` — `critique_hypothesis(hypothesis, reviewer_agents)`: dispatch critique requests to each reviewer via `WorkflowServiceInterface.create_execution`; await structured responses; parse into `HypothesisCritiqueCreate` per reviewer; write individual critique rows; `aggregate_critiques(hypothesis_id)`: compute per-dimension averages, detect disagreements (std dev > 0.3), write aggregated `HypothesisCritique(is_aggregated=True)`; publish `critique_completed` event
- [X] T023 [US2] Add `submit_for_critique` to `apps/control-plane/src/platform/discovery/service.py`
- [X] T024 [US2] Add `GET /hypotheses/{id}/critiques` endpoint to `apps/control-plane/src/platform/discovery/router.py` — returns `{items: HypothesisCritiqueResponse[], aggregated: HypothesisCritiqueResponse | null}`; also add `GET /hypotheses/{id}` single hypothesis endpoint

**Checkpoint**: US2 independently testable — critique dispatch, per-dimension scoring, and aggregation all functional.

---

## Phase 5: User Story 3 — Generate-Debate-Evolve Cycles (Priority: P2)

**Goal**: Full iterative loop — generate → critique → tournament → debate → refine — with convergence detection and manual halt.

**Independent Test**: POST /sessions/{id}/cycle → cycle executes all phases. After 2 cycles with stable top-Elo, session status becomes `converged`. POST /sessions/{id}/halt → session marked `halted` after current phase.

### Tests for US3

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T025 [P] [US3] Write unit tests for `GDECycleOrchestrator` in `apps/control-plane/tests/unit/discovery/test_gde_cycle.py` — mock all downstream service interfaces; test full cycle phase sequence (generate → critique → tournament → debate → refine); test convergence detection at cycle N (delta < threshold for 2 consecutive rounds → `converged=True`); test iteration limit → `iteration_limit_reached`; test manual halt; test `GDECycle` row written; test `cycle_completed` / `session_converged` events published

### Implementation for US3

- [X] T026 [P] [US3] Implement `GDECycleOrchestrator` in `apps/control-plane/src/platform/discovery/gde/cycle.py` — `run_cycle(session_id)`: create `GDECycle(status='running')`; (1) dispatch generation agents via `WorkflowServiceInterface.create_execution`; (2) await hypothesis results; (3) call `CritiqueEvaluator` for new hypotheses; (4) run tournament round via `TournamentComparator`; (5) dispatch debate agents with top-pair context; (6) await debate results; write `debate_record`; (7) dispatch refinement agents; update `refinement_count`; (8) check convergence: compare top Elo delta vs previous cycle; set `converged=True` if delta < threshold for `DISCOVERY_CONVERGENCE_STABLE_ROUNDS` rounds; update session status; publish `cycle_completed` or `session_converged` event
- [X] T027 [US3] Add `run_gde_cycle`, `halt_session` to `apps/control-plane/src/platform/discovery/service.py` — `run_gde_cycle`: check session status is `active` and no running cycle (raise `SessionAlreadyRunningError`); delegate to `GDECycleOrchestrator` as background task; `halt_session`: update session status to `halted`, publish `session_halted` event
- [X] T028 [US3] Add GDE endpoints to `apps/control-plane/src/platform/discovery/router.py` — `POST /sessions/{id}/cycle` (202 async), `POST /sessions/{id}/halt`, `GET /cycles/{id}`

**Checkpoint**: US3 independently testable — full iterative cycle executes; convergence and halt work correctly.

---

## Phase 6: User Story 4 — Design and Execute Discovery Experiments (Priority: P2)

**Goal**: Experiment design agent produces structured plan; governance validation via PolicyServiceInterface; sandbox execution via gRPC; results linked to hypothesis with Elo evidence bonus.

**Independent Test**: POST /hypotheses/{id}/experiment → plan generated with all sections. Confirm governance status. POST /experiments/{id}/execute → sandbox executes; results linked to hypothesis.

### Tests for US4

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T029 [P] [US4] Write unit tests for `ExperimentDesigner` in `apps/control-plane/tests/unit/discovery/test_experiment_designer.py` — mock `WorkflowServiceInterface`, `PolicyServiceInterface`, `SandboxManagerClient`; test design flow: plan structured correctly; governance passes → `approved`; governance fails → `rejected` with violations; test execute: rejected experiment raises `ExperimentNotApprovedError`; approved experiment → sandbox call → results stored; successful results → `EloRatingEngine.apply_evidence_bonus` called; test `experiment_designed` and `experiment_completed` events

### Implementation for US4

- [X] T030 [P] [US4] Implement `ExperimentDesigner.design()` in `apps/control-plane/src/platform/discovery/experiment/designer.py` — dispatch experiment design workflow via `WorkflowServiceInterface`; await structured plan (objective, methodology, expected_outcomes, required_data, resources, success_criteria, code); insert `DiscoveryExperiment(governance_status='pending')`; call `PolicyServiceInterface.evaluate_conformance`; update `governance_status` (approved/rejected + violations); publish `experiment_designed` event
- [X] T031 [US4] Implement `ExperimentDesigner.execute()` in `apps/control-plane/src/platform/discovery/experiment/designer.py` — check `governance_status='approved'` (raise `ExperimentNotApprovedError` otherwise); call `SandboxManagerClient.execute_code(template='python3.12', code=plan.code, workspace_id=..., timeout_seconds=DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS)`; update `execution_status` and `results`; write `EvidenceNode` to Neo4j (`SUPPORTS`/`CONTRADICTS`/`INCONCLUSIVE_FOR` based on `exit_code` and result interpretation); if successful, call `EloRatingEngine.apply_evidence_bonus(hypothesis_id)`; publish `experiment_completed` event
- [X] T032 [US4] Add `design_experiment`, `execute_experiment` to `apps/control-plane/src/platform/discovery/service.py`
- [X] T033 [US4] Add experiment endpoints to `apps/control-plane/src/platform/discovery/router.py` — `POST /hypotheses/{id}/experiment` (201), `GET /experiments/{id}`, `POST /experiments/{id}/execute` (202)
- [X] T034 [P] [US4] Write integration tests for experiment endpoints in `apps/control-plane/tests/integration/discovery/test_experiment_endpoints.py` — mock gRPC client and PolicyServiceInterface; test design → governance approve/reject → execute flow

**Checkpoint**: US4 independently testable — experiment design, governance validation, and sandbox execution all functional.

---

## Phase 7: User Story 5 — Trace Evidence Provenance Chains (Priority: P3)

**Goal**: Full Neo4j provenance graph queryable from any hypothesis — generation events, refinements, critiques, debates, and experiment results linked in a directed graph.

**Independent Test**: Run 2-cycle GDE session with experiment. GET /hypotheses/{id}/provenance → directed graph with HypothesisNode, DiscoveryAgentNode, EvidenceNode and typed edges (GENERATED_BY, REFINED_FROM, SUPPORTS/CONTRADICTS/INCONCLUSIVE_FOR).

### Tests for US5

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T035 [P] [US5] Write unit tests for `ProvenanceGraph` in `apps/control-plane/tests/unit/discovery/test_provenance_graph.py` — use Neo4j local-mode fallback (PostgreSQL graph tables); test `write_generation_event`: HypothesisNode + DiscoveryAgentNode + GENERATED_BY edge created; test `write_refinement`: REFINED_FROM edge with cycle_number; test `write_evidence`: EvidenceNode + typed edge (all 3 relationship types); test `query_provenance`: returns nodes + edges up to depth 3; test cursor pagination for large chains; test workspace_id isolation (no cross-workspace leakage)

### Implementation for US5

- [X] T036 [P] [US5] Implement `ProvenanceGraph` in `apps/control-plane/src/platform/discovery/provenance/graph.py` — using `AsyncGraphDatabase` (neo4j-python-driver 5.x); `write_generation_event(hypothesis, agent_fqn)`: MERGE HypothesisNode + DiscoveryAgentNode + CREATE GENERATED_BY edge; `write_refinement(new_hyp, source_hyp, cycle_num)`: CREATE REFINED_FROM edge; `write_evidence(evidence, hypothesis, relationship_type)`: MERGE EvidenceNode + CREATE typed edge; `query_provenance(hypothesis_id, workspace_id, depth)`: Cypher MATCH with workspace_id filter + depth-bounded traversal returning nodes + edges; local PostgreSQL fallback mode for tests
- [X] T037 [US5] Add `get_hypothesis_provenance` to `apps/control-plane/src/platform/discovery/service.py`
- [X] T038 [US5] Add `GET /hypotheses/{id}/provenance` endpoint to `apps/control-plane/src/platform/discovery/router.py` — returns `ProvenanceGraphResponse` with nodes array and edges array; `?depth={n}` param (default 3, max 10)
- [X] T039 [P] [US5] Write integration tests for provenance endpoints in `apps/control-plane/tests/integration/discovery/test_provenance_endpoints.py` — Neo4j local mode; test full provenance after 2 cycles; test empty provenance for new hypothesis; test depth limiting

**Checkpoint**: US5 independently testable — provenance graph writes and queries functional in Neo4j (and local fallback).

---

## Phase 8: User Story 6 — Explore Hypothesis Landscape via Proximity Clustering (Priority: P3)

**Goal**: Hypothesis embeddings computed and stored in Qdrant; pairwise cosine distance matrix via scipy; hierarchical clustering identifies over-explored clusters and gap regions; landscape context fed to generation agent.

**Independent Test**: Generate 20+ hypotheses. POST /sessions/{id}/compute-proximity → clustering runs. GET /sessions/{id}/clusters → over-explored and gap clusters identified. Next generation cycle receives `LandscapeContext` with gap descriptions.

### Tests for US6

> **NOTE**: Write these tests FIRST and confirm they FAIL before implementation.

- [X] T040 [P] [US6] Write unit tests for `HypothesisEmbedder` in `apps/control-plane/tests/unit/discovery/test_hypothesis_embedder.py` — mock httpx embedding API call; mock Qdrant client upsert; test `embed_hypothesis`: point upserted with correct payload (workspace_id, session_id, status); test `fetch_session_embeddings`: Qdrant payload filter by workspace_id + session_id; test `qdrant_point_id` updated on hypothesis row
- [X] T041 [P] [US6] Write unit tests for `ProximityClustering` in `apps/control-plane/tests/unit/discovery/test_proximity_clustering.py` — synthetic 20-hypothesis embedding set (4 tight clusters + 1 gap region); test cluster count matches expected; test over-explored detection (density > threshold); test gap detection (centroid distance > `DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD`); test `HypothesisCluster` rows written; test `low_data` status returned for < 3 hypotheses; test `proximity_computed` event published

### Implementation for US6

- [X] T042 [P] [US6] Implement `HypothesisEmbedder` in `apps/control-plane/src/platform/discovery/proximity/embeddings.py` — `embed_hypothesis(hypothesis)`: POST text to `settings.memory.embedding_api_url` via httpx; upsert `PointStruct` to Qdrant `discovery_hypotheses` collection with full payload; update `hypothesis.qdrant_point_id`; `fetch_session_embeddings(session_id, workspace_id)`: retrieve all active hypothesis vectors via Qdrant payload filter scroll
- [X] T043 [P] [US6] Implement `ProximityClustering` in `apps/control-plane/src/platform/discovery/proximity/clustering.py` — `compute(session_id, workspace_id)`: fetch embeddings via `HypothesisEmbedder`; return `{status: "low_data"}` if < 3 hypotheses; compute pairwise cosine distance matrix via `scipy.spatial.distance.cdist`; apply `scipy.cluster.hierarchy.fclusterdata` with `DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD`; classify clusters (`over_explored` if count > `OVER_EXPLORED_MIN_SIZE` AND density > `OVER_EXPLORED_SIMILARITY`); detect gap regions (areas with centroid distance > `GAP_DISTANCE_THRESHOLD` from all centroids); write `HypothesisCluster` rows; update `hypothesis.cluster_id`; produce `LandscapeContext` with gap descriptions; publish `proximity_computed` event; add `proximity_clustering_task()` APScheduler function consuming `cycle_completed` Kafka event
- [X] T044 [US6] Add `get_proximity_clusters`, `trigger_proximity_computation` to `apps/control-plane/src/platform/discovery/service.py`
- [X] T045 [US6] Add proximity endpoints to `apps/control-plane/src/platform/discovery/router.py` — `GET /sessions/{id}/clusters` (returns `{items: HypothesisClusterResponse[], landscape_status: "normal|saturated|low_data"}`), `POST /sessions/{id}/compute-proximity` (202)
- [X] T046 [P] [US6] Write integration tests for proximity endpoints in `apps/control-plane/tests/integration/discovery/test_proximity_endpoints.py` — Qdrant local mode; test compute-proximity → cluster rows written; test clusters endpoint; test 409 when computation already running

**Checkpoint**: US6 independently testable — embeddings computed, clusters identified, gap context produced.

---

## Phase 9: User Story 7 — Visualize Hypothesis Proximity Network (Priority: P4)

**Goal**: Interactive @xyflow/react network graph with cluster-colored nodes, similarity edges, node detail panels, and cycle-snapshot selector. Frontend only — backend proximity API from US6 is the data source.

**Independent Test**: Navigate to `/discovery/{session_id}/network`. Confirm node graph renders. Click node → detail panel shows hypothesis title, Elo score, cluster. Filter by cluster → non-matching nodes hidden. Select different cycle snapshots → graph updates.

### Implementation for US7

- [X] T047 [P] [US7] Create discovery route group and session network page at `apps/web/app/(main)/discovery/[session_id]/network/page.tsx` — fetch proximity clusters + hypotheses via TanStack Query; pass data to `HypothesisNetworkGraph`
- [X] T048 [P] [US7] Implement `HypothesisNetworkGraph` component in `apps/web/components/features/discovery/HypothesisNetworkGraph.tsx` — `@xyflow/react` nodes from `HypothesisResponse[]`; edges from similarity (filter by `similarity_threshold` prop); cluster color-coding via CSS custom properties; HNSW layout via `@dagrejs/dagre`
- [X] T049 [P] [US7] Implement `NodeDetailPanel` in `apps/web/components/features/discovery/NodeDetailPanel.tsx` — shows title, Elo score, cluster assignment, confidence, links to critiques and experiments; triggered by node click via `onNodeClick` callback
- [X] T050 [P] [US7] Implement `ClusterLegend` and cluster filter bar in `apps/web/components/features/discovery/ClusterLegend.tsx` — color swatches per cluster label; toggle visibility of non-selected clusters in graph
- [X] T051 [US7] Implement `CycleSnapshotSelector` in `apps/web/components/features/discovery/CycleSnapshotSelector.tsx` + `apps/web/lib/hooks/use-discovery-network.ts` — fetch cycle list; on snapshot select, re-fetch proximity clusters and hypotheses at that cycle's `computed_at` timestamp; update graph

**Checkpoint**: US7 independently testable — proximity network renders correctly with full interactivity.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Reach ≥95% coverage; mypy strict; ruff clean; edge cases covered.

- [X] T052 [P] Add edge case tests across all unit test files: 2-hypothesis tournament (minimum viable, no bye); odd-count bye mechanism (5 hypotheses → 2 pairs + 1 bye, bye hypothesis Elo unchanged); experiment governance rejection (violations listed, execution blocked); convergence at cycle 1 (immediately stable Elo); empty session provenance query (empty graph, no error); clustering with < 3 hypotheses (returns `low_data` status, no scipy calls)
- [X] T053 [P] Add edge case test: near-duplicate hypothesis detection (>0.95 similarity → merge with provenance preserved for both originals) in `apps/control-plane/tests/unit/discovery/test_proximity_clustering.py`
- [X] T054 [P] Run `mypy --strict` across all discovery modules in `apps/control-plane/src/platform/discovery/` and fix all type errors
- [X] T055 [P] Run `ruff check apps/control-plane/src/platform/discovery/ apps/control-plane/tests/unit/discovery/ apps/control-plane/tests/integration/discovery/` and fix all violations
- [X] T056 Run `pytest apps/control-plane/tests/unit/discovery/ apps/control-plane/tests/integration/discovery/ --cov=platform.discovery --cov-report=term-missing` and close gaps to reach ≥95% line coverage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Requires Phase 1 completion — BLOCKS all user stories
- **Phase 3 (US1)** and **Phase 4 (US2)**: Both require Phase 2 — can proceed in parallel (different files)
- **Phase 5 (US3)**: Requires Phase 3 + Phase 4 (GDE cycle orchestrates generation, critique, and tournament)
- **Phase 6 (US4)**: Requires Phase 2 and Phase 3 (experiments link to hypotheses + Elo bonus)
- **Phase 7 (US5)**: Requires Phase 3 + Phase 4 + Phase 6 (provenance reads all produced data)
- **Phase 8 (US6)**: Requires Phase 3 (needs hypotheses in Qdrant)
- **Phase 9 (US7)**: Requires Phase 8 (frontend reads proximity API from US6)
- **Phase 10 (Polish)**: Requires all desired phases complete

### User Story Dependencies

- **US1 (P1)**: Foundational complete — no dependency on other stories
- **US2 (P1)**: Foundational complete — no dependency on other stories; can run parallel with US1
- **US3 (P2)**: Requires US1 + US2 — orchestrates both
- **US4 (P2)**: Requires US1 for Elo bonus; experiment design otherwise independent
- **US5 (P3)**: Reads data produced by US1, US2, US3, US4 — best after those phases
- **US6 (P3)**: Requires hypotheses from US1; otherwise independent of US2–US5
- **US7 (P4)**: Requires US6 proximity API; frontend only

### Within Each User Story

- Tests written and FAIL before implementation starts
- Models/Repository (Phase 2) before services
- Services before router endpoints
- Core implementation before integration tests

### Parallel Opportunities

- T002, T003, T004 (Phase 1) — run in parallel
- T007, T010, T011 (Phase 2) — run in parallel
- T013 + T014 (US1 unit tests) — run in parallel
- T015 + T016 (US1 implementation) — run in parallel while T015 has no blocking dep on T016
- T019 + T020 (US1 integration tests) — run in parallel
- US1 (Phase 3) and US2 (Phase 4) — run fully in parallel after Phase 2
- T035 + T040 + T041 (US5 + US6 tests) — run in parallel
- T036 + T042 + T043 (US5 + US6 implementations) — run in parallel
- T054 + T055 (Phase 10 mypy + ruff) — run in parallel

---

## Parallel Example: User Story 1 + User Story 2

```bash
# After Phase 2 completes, launch both stories together:

# US1 stream:
Task: "T013 Write unit tests for EloRatingEngine (test_elo_engine.py)"
Task: "T014 Write unit tests for TournamentComparator (test_tournament_comparator.py)"
# → confirm both FAIL
Task: "T015 Implement EloRatingEngine in tournament/elo.py"
Task: "T016 Implement TournamentComparator in tournament/comparator.py"  # parallel with T015

# US2 stream (parallel with US1):
Task: "T021 Write unit tests for CritiqueEvaluator (test_critique_evaluator.py)"
# → confirm FAILS
Task: "T022 Implement CritiqueEvaluator in critique/evaluator.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3 (US1) + Phase 4 (US2) in parallel
4. **STOP and VALIDATE**: Hypothesis generation, tournament, and critique working end-to-end
5. Merge and demo

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 + US2 → Generate and rank hypotheses with critique → **MVP**
3. US3 → Full GDE cycle loop with convergence
4. US4 → Experiment design and sandbox execution
5. US5 → Provenance graph
6. US6 → Proximity clustering and landscape analysis
7. US7 → Frontend visualization

### Parallel Team Strategy

With multiple developers (after Phase 2):
- **Developer A**: US1 (tournament/elo.py, tournament/comparator.py)
- **Developer B**: US2 (critique/evaluator.py)
- **Developer C**: Migration + integration test infrastructure

---

## Notes

- [P] tasks = different files, no blocking inter-dependencies at time of execution
- [Story] label maps each task to its user story for traceability
- Tests are mandatory (SC-008: ≥95% coverage) — write them first and confirm FAIL
- Neo4j provenance uses local PostgreSQL fallback mode for integration tests (no Neo4j container required in CI)
- Qdrant uses in-process local mode for integration tests
- Redis uses in-memory dict mock for integration tests (`REDIS_TEST_MODE=standalone`)
- SandboxManagerClient and WorkflowServiceInterface are always mocked in unit and integration tests
- All service methods are `async def`; all repository calls use `AsyncSession`
- Elo batch updates under `lock:discovery:elo:{session_id}` using existing `lock_acquire.lua` pattern
