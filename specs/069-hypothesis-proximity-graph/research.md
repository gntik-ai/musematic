# Research & Decisions: Hypothesis Proximity Graph

**Feature**: 069-hypothesis-proximity-graph  
**Date**: 2026-04-20

## Context

The discovery bounded context already has substantial proximity infrastructure at session scope. This feature extends it to workspace scope, wires per-hypothesis indexing into the generation path, and feeds the gap signal into the hypothesis-generator prompt. All decisions below are constrained by Brownfield Rule 1 (never rewrite) and Rule 4 (use existing patterns).

---

## Existing State (Baseline)

| Component | File / Location | Status |
|---|---|---|
| `HypothesisEmbedder` (Qdrant collection `discovery_hypotheses`, 1536-dim embedding via `settings.memory.embedding_api_url`) | `discovery/proximity/embeddings.py:14-120` | ✅ Exists |
| `ProximityClustering` (hierarchical cosine clustering, classifies `normal`/`over_explored`/`gap`) | `discovery/proximity/clustering.py:21-156` | ✅ Exists |
| `proximity_clustering_task(session_id, workspace_id)` | `discovery/proximity/clustering.py:158-163` | ✅ Exists (callable, not yet scheduled) |
| `HypothesisCluster` SQLAlchemy model (`classification`, `hypothesis_ids`, `centroid_description`, `computed_at`) | `discovery/models.py:338-369` | ✅ Exists |
| `Hypothesis.qdrant_point_id`, `Hypothesis.cluster_id` | `discovery/models.py:194-195` | ✅ Exists |
| `GET /api/v1/discovery/sessions/{session_id}/clusters` | `discovery/router.py:256-265` | ✅ Exists |
| `POST /api/v1/discovery/sessions/{session_id}/compute-proximity` | `discovery/router.py:269-282` | ✅ Exists |
| `ClusterListResponse` schema with `LandscapeStatus` | `discovery/schemas.py:208-225` | ✅ Exists |
| `discovery.events.proximity_computed` Kafka event on `discovery.events` | `discovery/events.py:203-214` | ✅ Exists |
| `_generate_hypotheses()` generator (does NOT embed; no bias hints) | `discovery/gde/cycle.py:117-196` | ⚠️ Needs extension |
| Workspace-level bias toggle | none | ❌ Missing |
| Workspace-level proximity graph endpoint | none | ❌ Missing |
| Sync embedding at generation time | none | ❌ Missing |
| Workspace-scoped scheduler wiring | none (only on-demand POST exists) | ❌ Missing |
| `embedding_status` field on `Hypothesis` | none | ❌ Missing |
| Saturation / gap-filled transition events | none | ❌ Missing |
| Neo4j edge store for proximity | none (Neo4j used only in `provenance/graph.py`) | Not used — follow existing Qdrant-only pattern |

**Next migration number**: `056`.

---

## Decisions

### D-001: Extend existing proximity module — do not create a new services/ directory

**Decision**: Add new code to `discovery/proximity/` (the existing subdirectory). Do not create `discovery/services/proximity_service.py` as the user-input implementation sketch suggests.

**Rationale**: The discovery bounded context uses a **flat layout** (`discovery/models.py`, `discovery/service.py`, `discovery/router.py`) with capability subpackages (`discovery/proximity/`, `discovery/gde/`, `discovery/critique/`, `discovery/tournament/`). There is no `discovery/services/` directory. Brownfield Rule 4 (use existing patterns) rules out introducing one. The existing `discovery/proximity/` package is the natural home for graph-service code next to `embeddings.py` and `clustering.py`.

**Alternatives considered**:
- `discovery/services/proximity_service.py` — rejected: inconsistent with every other discovery capability package.
- Inlining into `discovery/service.py` — rejected: would push `DiscoveryService` past reasonable size and couple workspace-graph logic to the unrelated tournament/critique methods.

---

### D-002: New file `discovery/proximity/graph.py` for the `ProximityGraphService`

**Decision**: Create `discovery/proximity/graph.py` exporting `ProximityGraphService` with three public methods:
- `compute_workspace_graph(workspace_id, session_id=None) → ProximityGraph` — returns nodes, edges, clusters, gap regions, saturation indicator.
- `index_hypothesis(hypothesis_id) → IndexResult` — synchronous embedding + Qdrant upsert; returns `indexed`/`pending` result.
- `derive_bias_signal(workspace_id, session_id) → BiasSignal | None` — returns gap regions and over-explored clusters formatted for prompt injection; returns `None` when below min-hypothesis threshold or when bias disabled.

**Rationale**: Single-responsibility service that composes existing `HypothesisEmbedder` and `ProximityClustering`. Keeps the graph-projection and bias-derivation logic in one reviewable unit.

---

### D-003: No Neo4j; in-memory edge computation from clustering output

**Decision**: Proximity edges are computed in-memory at query time from the pairwise-distance output of `ProximityClustering` and are not persisted.

**Rationale**: The existing proximity implementation is Qdrant-only — clustering runs in-process via `scipy.cluster.hierarchy` with a pure-Python fallback (`clustering.py:188`). Neo4j is only wired in `provenance/graph.py` for a different concern (generation lineage, not semantic proximity). Adding Neo4j as a new dependency for this feature would violate Brownfield Rule 1 (never rewrite) and introduce operational load (StatefulSet, APOC plugin) for data that is already derivable in memory from Qdrant + existing clustering. The spec's Assumptions section explicitly allows this path ("Neo4j edge storage is used only if the existing session-level clustering task already uses it").

**Alternatives considered**:
- Persist edges in a new `discovery_proximity_edges` PostgreSQL table — rejected: violates Principle III (use specialist store for graph — Qdrant's similarity search already answers neighbor queries).
- Introduce Neo4j `ProximityEdge` relationship — rejected: scale of workspace (up to 10,000 nodes per SC-001) produces up to O(n²) edges; in-memory top-k neighbors from Qdrant is far cheaper.

**Implication**: Graph response returns **top-k neighbors per node** computed from Qdrant vector search, not an exhaustive edge list. New config `proximity_graph_max_neighbors_per_node` (default 8) caps fan-out.

---

### D-004: Workspace-level bias toggle lives in a new small table — not in `DiscoverySession.config`

**Decision**: Add new table `discovery_workspace_settings(workspace_id PRIMARY KEY, bias_enabled BOOLEAN, recompute_interval_minutes INT, created_at, updated_at)` via migration 056.

**Rationale**: Bias is a **workspace-level** setting per spec (FR-013) — it applies across sessions and must not be lost when a session ends. Storing it in `DiscoverySession.config` JSONB would require copying the flag into every new session, making "disable bias for this workspace" leaky and error-prone. A dedicated workspace-settings row with a `get_or_create` lookup is the least-coupled option.

**Alternatives considered**:
- Column on `workspaces` table — rejected: crosses the discovery-bounded-context boundary (Principle IV).
- Session-level flag only — rejected: contradicts spec FR-013.
- Feature flag in config — rejected: not per-workspace; can only be global.

---

### D-005: `embedding_status` column on `Hypothesis` for pending-embedding fallback

**Decision**: Migration 056 adds `discovery_hypotheses.embedding_status VARCHAR(16) DEFAULT 'pending' NOT NULL` with partial index `ix_discovery_hypotheses_embedding_pending ON (workspace_id) WHERE embedding_status = 'pending'`. Values: `pending`, `indexed`, `failed`.

**Rationale**: FR-009 requires that a generation call persists the hypothesis even when the embedding step fails and that the scheduled recomputation picks it up later. A single `embedding_status` column cleanly encodes the three states; the partial index makes the recomputation scan O(k) for k pending rows rather than O(n).

**Alternatives considered**:
- Use presence/absence of `qdrant_point_id` as implicit status — rejected: ambiguous (could also mean "embedding in flight"; breaks existing code that checks `qdrant_point_id is not None` after batch embedding).
- New `hypothesis_embedding_jobs` table — rejected: over-engineered for a single-field concern.

---

### D-006: Sync embedding in `_generate_hypotheses()` via `try/except`, generation never fails on embedding errors

**Decision**: After `_generate_hypotheses()` persists a new hypothesis, it calls `ProximityGraphService.index_hypothesis(id)` inside a `try/except`. On success → `embedding_status='indexed'`. On failure → `embedding_status='pending'` + log + metric emit (no exception propagated).

**Rationale**: FR-009 explicitly mandates generation MUST NOT fail because of embedding errors. Wrapping the call in try/except is the minimal intervention to `gde/cycle.py` that preserves existing behavior for success paths while adding the fallback.

**Alternatives considered**:
- Let embedding failures propagate — rejected: violates FR-009.
- Fire-and-forget via `asyncio.create_task` — rejected: FR-008 states the embedding MUST complete **before** generation response returns.

---

### D-007: Bias signal generated at prompt-build time, not precomputed

**Decision**: `ProximityGraphService.derive_bias_signal()` is called by `_generate_hypotheses()` **at the moment of hypothesis generation**, not precomputed and cached. The signal reads the latest `HypothesisCluster` rows (which are written by `proximity_clustering_task`).

**Rationale**: Bias signal size is O(k) where k = number of clusters (small — typically < 20 per workspace). Query cost is a single indexed read. Precomputing would add invalidation complexity (when does the precomputed signal become stale?) without measurable benefit.

**Alternatives considered**:
- Precompute into a Redis key — rejected: adds cache-coherence complexity; minimal perf gain.
- Precompute at each cluster recomputation and persist alongside `HypothesisCluster` — rejected: couples bias-prompt format to cluster storage; breaks if bias-signal schema evolves.

---

### D-008: Workspace-scope scheduler task added, session-scope `proximity_clustering_task` preserved byte-identical

**Decision**: Add new scheduler entry point `workspace_proximity_recompute_task(workspace_id)` in `discovery/proximity/scheduler.py`. Register in `main.py` lifespan with configurable interval (default 15 min). Existing `proximity_clustering_task(session_id, workspace_id)` is untouched and continues to serve the existing POST endpoint.

**Rationale**: SC-007 + FR-017 mandate byte-identical session-level behavior. Creating a new task for workspace scope keeps the session-level code path intact. The new task iterates active workspaces, calls `ProximityGraphService.compute_workspace_graph` per workspace, persists cluster rows, publishes events.

---

### D-009: Cluster-transition events emitted on state change, not on every recomputation

**Decision**: Add 2 new event types on existing `discovery.events` Kafka topic:
- `discovery.proximity.cluster_saturated` — fired when a cluster transitions `normal` → `over_explored` between consecutive recomputations.
- `discovery.proximity.gap_filled` — fired when a previously existing gap region no longer exists in the current computation.

Transition detection reads previous `HypothesisCluster` rows for the workspace before upserting new ones; the diff emits events.

**Rationale**: FR-016 requires observable signal on transitions — not on every recomputation. Event volume stays proportional to real change, matching existing `discovery.proximity_computed` event pattern.

---

### D-010: Response shape — `ProximityGraphResponse` is additive to existing schemas

**Decision**: `ProximityGraphResponse` extends `ClusterListResponse` with new fields (`nodes: list[NodeEntry]`, `edges: list[EdgeEntry]`, `gap_regions: list[GapRegion]`, `computed_at`, `graph_scope`). Existing `ClusterListResponse` and its endpoint are preserved verbatim for session-scoped callers.

**Rationale**: Brownfield Rule 7 (backward-compatible APIs). A new response type avoids silently changing the session-scoped endpoint.

---

### D-011: Config additions — extend existing `DiscoverySettings`, no new settings class

**Decision**: Add 4 fields to existing `DiscoverySettings` in `common/config.py`:
- `proximity_graph_max_neighbors_per_node: int = 8` (edge fan-out cap per D-003)
- `proximity_graph_recompute_interval_minutes: int = 15` (workspace scheduler cadence)
- `proximity_graph_staleness_warning_minutes: int = 60` (response adds "last-computed" annotation beyond this)
- `proximity_bias_default_enabled: bool = True` (default for new `DiscoveryWorkspaceSettings` rows)

**Rationale**: Brownfield Rule 6 (use existing enum/settings — don't recreate). `DiscoverySettings` already holds 5 proximity-related fields; adding 4 more keeps them co-located.

---

### D-012: Migration 056, `down_revision = "055_adaptation_pipeline_and_proficiency"`

**Decision**: Single Alembic migration `056_proximity_graph_workspace.py` performs:
1. `ALTER TABLE discovery_hypotheses ADD COLUMN embedding_status VARCHAR(16) DEFAULT 'pending' NOT NULL`
2. Backfill existing rows: `UPDATE discovery_hypotheses SET embedding_status = 'indexed' WHERE qdrant_point_id IS NOT NULL` then `UPDATE ... SET embedding_status = 'pending' WHERE qdrant_point_id IS NULL`
3. Partial index `ix_discovery_hypotheses_embedding_pending` on `(workspace_id) WHERE embedding_status = 'pending'`
4. `CREATE TABLE discovery_workspace_settings (...)`
5. `CREATE INDEX ix_discovery_workspace_settings_workspace_id` (implicit via PK — skipped)

**Rationale**: Atomic migration. Backfill avoids a state where existing already-indexed hypotheses appear "pending" after deploy.

---

## Resolved Unknowns

All spec NEEDS CLARIFICATION markers were resolved during spec authoring. No open unknowns remain.

---

## Risks

1. **Qdrant top-k latency for large workspaces** (SC-001 calls for < 2 s on 1,000 hypotheses): Qdrant vector search at k=8 per node yields ~8,000 queries. Mitigation: batch via Qdrant's `search_batch` API (already supported by `qdrant-client 1.12+`). Fallback: cap workspace scale in response and set `truncated=true`.
2. **Embedding provider outage during generation bursts**: Many hypotheses could accumulate with `embedding_status='pending'`. Mitigation: the scheduled recomputation batches pending rows on every tick.
3. **Cluster-transition false positives on borderline cases**: A cluster oscillating between `normal` and `over_explored` across recomputations would emit repeated events. Mitigation: tolerance band (configurable: `proximity_over_explored_similarity ± 0.02`) — transitions fire only when crossing the outer band.
