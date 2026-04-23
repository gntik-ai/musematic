# Data Model: Hypothesis Proximity Graph

**Feature**: 069-hypothesis-proximity-graph  
**Date**: 2026-04-20  
**Migration**: `056_proximity_graph_workspace.py` (down_revision: `055_adaptation_pipeline_and_proficiency`)

## Overview

One new table, one new column on an existing table, one partial index. No new enums, no Qdrant or Neo4j schema changes. All changes additive.

---

## Existing Table Extensions

### `discovery_hypotheses` — 1 new column + 1 partial index

```sql
ALTER TABLE discovery_hypotheses
  ADD COLUMN embedding_status VARCHAR(16) NOT NULL DEFAULT 'pending';

-- Backfill: rows that already have a qdrant_point_id are indexed; others remain pending.
UPDATE discovery_hypotheses
  SET embedding_status = 'indexed'
  WHERE qdrant_point_id IS NOT NULL;

CREATE INDEX ix_discovery_hypotheses_embedding_pending
  ON discovery_hypotheses (workspace_id)
  WHERE embedding_status = 'pending';
```

**Values**: `pending` | `indexed` | `failed`.

- `pending` — hypothesis persisted; Qdrant upsert not yet attempted or currently retrying.
- `indexed` — Qdrant upsert succeeded; `qdrant_point_id` populated.
- `failed` — embedding-provider rejected the content (non-transient); requires manual retry.

**State transitions**:
```
(new row) ──insert──▶ pending ──sync embed ok──▶ indexed
                         │
                         ├──sync embed fails──▶ pending (scheduled retry)
                         └──retry exhausted──▶ failed
```

Existing `Hypothesis.qdrant_point_id` column is unchanged. Existing `Hypothesis.cluster_id` column is unchanged.

---

## New Table

### `discovery_workspace_settings`

Per-workspace discovery configuration. One row per workspace, lazy-created on first proximity-graph access.

```sql
CREATE TABLE discovery_workspace_settings (
    workspace_id                 UUID        PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    bias_enabled                 BOOLEAN     NOT NULL DEFAULT TRUE,
    recompute_interval_minutes   INTEGER     NOT NULL DEFAULT 15,
    last_recomputed_at           TIMESTAMPTZ,
    last_transition_summary      JSONB,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`bias_enabled`**: when `FALSE`, `ProximityGraphService.derive_bias_signal()` returns `None` and generation proceeds without bias context (parity with pre-feature behavior).

**`recompute_interval_minutes`**: per-workspace override for the global `proximity_graph_recompute_interval_minutes` default.

**`last_recomputed_at`**: updated by the scheduler on each successful workspace recomputation; read by the proximity-graph endpoint to compute a staleness annotation.

**`last_transition_summary`** JSONB schema (set after each recomputation):
```json
{
  "clusters_newly_saturated": ["cluster-uuid-1"],
  "gaps_filled": ["gap-label-a"],
  "total_clusters": 12,
  "total_gaps": 3,
  "saturation_ratio": 0.25
}
```

---

## No Changes to These Entities

| Table / Store | Used By |
|---|---|
| `discovery_hypothesis_clusters` | Read for graph response; continues to be populated by existing `ProximityClustering` and new workspace-scope task — no schema change |
| `discovery_sessions` | Read for session-scoped filter; no schema change |
| Qdrant collection `discovery_hypotheses` | Reused; `HypothesisEmbedder.embed_hypothesis()` continues to populate it |
| Neo4j | Not used by this feature — see D-003 |
| `context_assembly_records` | Not involved |

---

## Derived / In-Memory Entities

The following are **not persisted**. They are computed at request time from the tables above plus Qdrant top-k neighbor queries.

### `ProximityGraph` (response-only)

```python
class ProximityGraph:
    workspace_id: UUID
    session_id: UUID | None          # populated when session_id filter applied
    status: Literal["pre_proximity", "computed"]
    nodes: list[NodeEntry]
    edges: list[EdgeEntry]
    clusters: list[ClusterEntry]
    gap_regions: list[GapRegion]
    saturation_indicator: Literal["normal", "saturated", "low_data"]
    computed_at: datetime
    staleness_warning: str | None    # populated if last_recomputed_at > staleness_warning_minutes
    pending_embedding_count: int     # number of hypotheses with embedding_status='pending'
    truncated: bool                  # true if node count exceeded scale ceiling
```

### `NodeEntry`

```python
class NodeEntry:
    hypothesis_id: UUID
    cluster_id: str | None           # references HypothesisCluster.id; null if hypothesis is a gap-region singleton
    embedding_status: Literal["pending", "indexed", "failed"]
```

### `EdgeEntry`

```python
class EdgeEntry:
    source_hypothesis_id: UUID
    target_hypothesis_id: UUID
    similarity: float                # 1.0 - cosine_distance; in [0, 1]
```

Edges are computed per node by calling Qdrant `search` with the node's embedding and `limit=proximity_graph_max_neighbors_per_node` (default 8). Self-edges removed. Edges are undirected but emitted once (lower-UUID-first convention).

### `ClusterEntry`

```python
class ClusterEntry:
    cluster_id: str
    centroid_description: str
    classification: Literal["under_explored", "normal", "over_explored"]
    hypothesis_ids: list[UUID]
    density: float                   # avg intra-cluster similarity
```

### `GapRegion`

```python
class GapRegion:
    label: str                       # topical descriptor derived from nearest hypothesis content
    center_hypothesis_id: UUID       # nearest singleton hypothesis (the centroid anchor)
    min_distance_to_nearest: float   # cosine distance to closest non-member
```

### `BiasSignal` (never persisted)

Derived at generation time by `ProximityGraphService.derive_bias_signal()`:

```python
class BiasSignal:
    workspace_id: UUID
    session_id: UUID | None
    explore_hints: list[str]         # gap-region labels — "explore these"
    avoid_hints: list[str]           # over_explored cluster descriptions — "avoid these"
    source: Literal["workspace_scope", "session_scope"]
    generated_at: datetime
    skipped: bool                    # true if below min-hypothesis threshold or bias disabled
    skip_reason: str | None          # "insufficient_data" | "bias_disabled" | "graph_stale"
```

---

## Kafka Events (Additive on `discovery.events` topic)

Existing events preserved: `discovery.proximity_computed`, `discovery.hypothesis.created`, etc.

### New events

| Event Type | Payload (extends `DiscoveryEventPayload`) | When |
|---|---|---|
| `discovery.proximity.cluster_saturated` | `workspace_id, cluster_id, classification_from, classification_to, member_count, density` | Cluster crosses from `normal` to `over_explored` between consecutive workspace recomputations |
| `discovery.proximity.gap_filled` | `workspace_id, former_gap_label, now_part_of_cluster_id` | Previously existing gap region no longer exists in current computation (hypotheses filled in around it) |

Transition detection runs inside the workspace recompute task: before upserting new `HypothesisCluster` rows, the task reads the previous cluster set and diffs classification and gap-region membership.

---

## Configuration (Additive on `DiscoverySettings`)

Existing fields preserved. New fields:

| Field | Default | Purpose |
|---|---|---|
| `proximity_graph_max_neighbors_per_node` | `8` | Edge fan-out cap per D-003 |
| `proximity_graph_recompute_interval_minutes` | `15` | Workspace-scope scheduler default; overridable per workspace |
| `proximity_graph_staleness_warning_minutes` | `60` | Read endpoint annotates response when stale beyond this |
| `proximity_bias_default_enabled` | `True` | Default `bias_enabled` for newly-created `DiscoveryWorkspaceSettings` rows |

---

## Retention

No new retention policies. `HypothesisCluster` rows are upserted in place (one set per workspace per scope). Old cluster rows are replaced on each recompute — no snapshot history is retained (spec Assumptions section).

`discovery_workspace_settings` rows persist until the workspace is deleted (cascade).
