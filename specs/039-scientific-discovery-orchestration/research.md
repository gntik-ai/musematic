# Research: Scientific Discovery Orchestration

**Feature**: 039-scientific-discovery-orchestration  
**Date**: 2026-04-15  
**Branch**: `039-scientific-discovery-orchestration`

---

## Decision 1: Elo Ranking via Redis Sorted Sets

**Decision**: Use Redis sorted sets with the key pattern `leaderboard:{session_id}` for real-time Elo score tracking. Pairwise Elo calculation is pure in-process Python. Scores are atomically updated in Redis after each comparison using `ZADD`. The PostgreSQL `discovery_elo_scores` table persists historical snapshots and win/loss/draw counts.

**Rationale**: The platform already has a Redis leaderboard pattern (`leaderboard:{tournament_id}`) using ZADD/ZREVRANGE/ZSCORE/ZREVRANK. Discovery tournaments follow the same pattern. Redis sorted sets provide O(log N) rank lookups and atomic score updates at the frequency needed during tournament rounds. Elo calculations (pure arithmetic) are done in-process — no external service needed.

**Elo formula**:
```python
# Expected score for hypothesis A vs B
expected_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
# New score
new_elo_a = elo_a + K * (actual_a - expected_a)  # K = 32 default
```

**Alternatives considered**:
- PostgreSQL for Elo storage only: Rejected — Redis sorted sets give O(1) rank queries which are needed during active tournament rounds; PostgreSQL is too slow for concurrent comparison updates.
- A separate ranking microservice: Rejected — over-engineering; the existing Redis client already supports sorted set operations.

---

## Decision 2: Hypothesis Embeddings in Qdrant

**Decision**: New `discovery_hypotheses` Qdrant collection, 1536-dimensional Cosine distance (matching `platform_memory` collection). Payload indexes on `workspace_id` (KEYWORD), `session_id` (KEYWORD), `cluster_id` (KEYWORD). The `HypothesisEmbedder` class computes embeddings via the platform's existing embedding API endpoint (`settings.memory.embedding_api_url` — same httpx pattern as memory subsystem). Point ID = hypothesis UUID.

**Rationale**: Consistent with the platform's Qdrant collection setup: HNSW (m=16, ef_construct=128), Cosine distance, 1536-dim. Workspace-scoped filtering prevents cross-workspace hypothesis leakage. The `embedding_api_url` config is already defined globally — no new config needed for embedding calls.

**Collection configuration**:
```python
VectorParams(size=1536, distance=Distance.COSINE)
hnsw_config: HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000)
```

**Alternatives considered**:
- Store embeddings in PostgreSQL (VECTOR type): Rejected — Constitution III mandates Qdrant for all vector operations; PostgreSQL must not be used for vector search.
- Compute embeddings synchronously during hypothesis creation: Accepted as primary path for small hypothesis counts; background re-embedding falls back to a Kafka-triggered job for bulk operations.

---

## Decision 3: Evidence Provenance Graph in Neo4j

**Decision**: Use Neo4j for provenance chains with the existing `AsyncGraphDatabase` pattern and local PostgreSQL fallback. Node labels: `HypothesisNode`, `AgentNode`, `EvidenceNode`, `CritiqueNode`, `DebateArgumentNode`. Relationship types: `GENERATED_BY`, `CRITIQUE_OF`, `REFINED_FROM`, `DEBATE_ARGUMENT_FOR`, `DEBATE_ARGUMENT_AGAINST`, `SUPPORTS`, `CONTRADICTS`, `INCONCLUSIVE_FOR`. All nodes carry `workspace_id` for workspace-scoped traversal.

**Rationale**: The platform's Neo4j async client (`AsyncGraphDatabase.driver()`) with Cypher is already established for knowledge graph operations. Evidence provenance is naturally a directed graph — chains from hypothesis → evidence → supporting data → producing agent. Constitution III mandates Neo4j for all graph traversals. Local mode fallback (PostgreSQL graph_nodes/graph_edges tables) preserves testability without Neo4j.

**Provenance traversal**:
```cypher
MATCH (h:HypothesisNode {hypothesis_id: $id, workspace_id: $ws})
  <-[:SUPPORTS|CONTRADICTS|INCONCLUSIVE_FOR]-(e:EvidenceNode)
  -[:DERIVED_FROM]->(exp:ExperimentNode)
RETURN h, e, exp
```

**Alternatives considered**:
- Store provenance as JSONB in PostgreSQL: Rejected — deep multi-hop provenance traversal (hypothesis → evidence → experiment → agent → refinements) degrades with recursive CTEs at scale. Neo4j handles this natively.

---

## Decision 4: Experiment Execution via Sandbox Manager

**Decision**: Experiment plans are executed by calling the `SandboxManagerClient` gRPC stub (`services/sandbox-manager/` at port 50053). The `ExperimentDesigner` submits a code execution request using the `python3.12` template. Results are captured and linked to the originating hypothesis in PostgreSQL. The `governance/policy` service validates the experiment plan before sandbox submission.

**Rationale**: The sandbox manager is the platform's established mechanism for sandboxed code execution. Using it for experiments ensures the same isolation guarantees and security posture. The `SandboxManagerClient` (`common/clients/sandbox_manager.py`) provides the async gRPC interface.

**Implementation note**: The SandboxManagerClient gRPC stub is initialized but method stubs are not yet defined in the control plane client wrapper. The discovery feature will need to add the `ExecuteCode` RPC call stub following the `RuntimeControllerClient` pattern.

**Alternatives considered**:
- Direct subprocess execution: Rejected — violates Constitution VII (sandbox isolation). Any code execution must go through the sandbox manager.
- Async job queue for experiment results: The sandbox gRPC call is synchronous from the control plane's perspective (awaited). Results polling (for long-running experiments) will use a configurable timeout with APScheduler follow-up check.

---

## Decision 5: GDE Cycle Orchestration Pattern

**Decision**: `GDECycleOrchestrator` runs as a coordinating service method (not APScheduler). Each cycle is triggered explicitly by `DiscoveryService.run_cycle(session_id)`. Within a cycle, agent invocations (generation, debate, refinement) are modeled as workflow execution triggers — the discovery service calls `ExecutionService.create_execution()` or dispatches Kafka `workflow.triggers` events to the execution engine. Results are returned via Kafka events on `discovery.events`.

**Rationale**: Cycle orchestration is a long-running multi-step process. The workflow execution engine (feature 029) already handles multi-step agent coordination with state persistence and checkpointing. Reusing it avoids duplicating orchestration logic. The discovery service acts as a workflow definition generator, not an orchestrator itself.

**Convergence check**:
```python
# After each cycle
abs(current_top_elo - prev_top_elo) / prev_top_elo < convergence_threshold
# If true for N consecutive rounds → converged
```

**Alternatives considered**:
- APScheduler for cycle coordination: Rejected — cycles are event-driven (user-triggered), not time-based. APScheduler is only appropriate for the background proximity clustering task.

---

## Decision 6: Proximity Clustering Algorithm

**Decision**: Use `scipy.cluster.hierarchy` (agglomerative clustering with average linkage) on cosine distance matrix computed from hypothesis embeddings fetched from Qdrant. Cluster count is automatically determined by a distance threshold (default 0.3). Gap detection: a region is a "gap" if no hypothesis centroid is within 0.5 cosine distance of any point in a configurable exploration direction (represented as a descriptor vector). Over-explored: cluster with density > 5 hypotheses and intra-cluster average similarity > 0.85.

**Rationale**: `scipy>=1.13` is already in the tech stack (added in feature 037 for statistical tests). Using the same dependency avoids adding `scikit-learn`. Agglomerative clustering with a distance threshold is appropriate for variable-size hypothesis sets without requiring a predetermined K.

**Implementation**: Runs as a background APScheduler task triggered by `discovery.cycle_completed` Kafka events. Results stored in PostgreSQL `discovery_hypothesis_clusters` table + Neo4j cluster membership edges.

**Alternatives considered**:
- k-means via numpy: Rejected — requires fixed K, inappropriate for growing hypothesis sets.
- scikit-learn DBSCAN: Rejected — would add a new dependency (scikit-learn) when scipy already provides equivalent functionality. Constitution Complexity Tracking requires justification for each new dependency.

---

## Decision 7: New Kafka Topic

**Decision**: Add `discovery.events` topic. Key: `session_id`. Producers: `discovery/events.py`. Consumers: ws_hub (real-time progress to frontend), analytics (discovery session metrics), notification service (cycle completion + convergence alerts).

**Event types**: `session_started`, `hypothesis_generated`, `critique_completed`, `tournament_round_completed`, `cycle_completed`, `session_converged`, `session_halted`, `experiment_designed`, `experiment_completed`, `proximity_computed`.

---

## New Service Interface Method Needed

`SandboxManagerClient` in `apps/control-plane/src/platform/common/clients/sandbox_manager.py` needs:
```python
async def execute_code(
    template: str, code: str, workspace_id: UUID, timeout_seconds: int
) -> SandboxExecutionResult: ...
    # Returns: {execution_id, status, stdout, stderr, exit_code, artifacts}
```
This mirrors the pattern in `RuntimeControllerClient`. If not yet implemented, `ExperimentDesigner` falls back to a "governance_approved_pending_execution" status.
