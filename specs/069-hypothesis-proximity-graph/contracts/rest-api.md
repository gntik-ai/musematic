# REST API Contracts: Hypothesis Proximity Graph

**Feature**: 069-hypothesis-proximity-graph  
**Date**: 2026-04-20  
**Base path**: `/api/v1/discovery/`  
**Auth**: All endpoints require Bearer JWT. Authorization reuses existing discovery-bounded-context RBAC (workspace membership).

---

## Existing Endpoints (Reference — No Changes to Behavior)

These endpoints already exist and keep working byte-identically (SC-007, FR-017):

```
GET  /api/v1/discovery/sessions/{session_id}/clusters
     Returns: ClusterListResponse — unchanged
POST /api/v1/discovery/sessions/{session_id}/compute-proximity
     Returns: ClusterListResponse (HTTP 202) — unchanged; calls existing proximity_clustering_task
```

---

## New Endpoints

### `GET /api/v1/discovery/{workspace_id}/proximity-graph`

Return the workspace-scope proximity graph: nodes, edges (top-k neighbors per node via Qdrant), clusters, gap regions, saturation indicator, and pending-embedding count.

**Path params**:
- `workspace_id` (UUID, required) — workspace to query

**Query params**:
- `session_id` (UUID, optional) — restrict to a single session's hypotheses
- `include_edges` (bool, default `true`) — when `false`, omits edge computation (faster response for cluster-only views)
- `max_nodes` (int, default from config — typically 10,000) — truncate if exceeded; response includes `truncated: true`

**Response** `200 OK`:
```json
{
  "workspace_id": "uuid",
  "session_id": null,
  "status": "computed",
  "saturation_indicator": "saturated",
  "computed_at": "2026-04-20T10:15:00Z",
  "staleness_warning": null,
  "pending_embedding_count": 2,
  "truncated": false,
  "nodes": [
    {
      "hypothesis_id": "uuid",
      "cluster_id": "cluster-a",
      "embedding_status": "indexed"
    }
  ],
  "edges": [
    {
      "source_hypothesis_id": "uuid-a",
      "target_hypothesis_id": "uuid-b",
      "similarity": 0.91
    }
  ],
  "clusters": [
    {
      "cluster_id": "cluster-a",
      "centroid_description": "Retrieval augmentation over domain X",
      "classification": "over_explored",
      "hypothesis_ids": ["uuid-1", "uuid-2", "uuid-3"],
      "density": 0.88
    }
  ],
  "gap_regions": [
    {
      "label": "Multi-document synthesis in low-resource languages",
      "center_hypothesis_id": "uuid-99",
      "min_distance_to_nearest": 0.62
    }
  ]
}
```

**Response when below min-hypothesis threshold** `200 OK`:
```json
{
  "workspace_id": "uuid",
  "status": "pre_proximity",
  "min_hypotheses_required": 10,
  "current_embedded_count": 4,
  "pending_embedding_count": 0,
  "nodes": [],
  "edges": [],
  "clusters": [],
  "gap_regions": []
}
```

**Errors**:
- `404 Not Found` — workspace does not exist or caller has no access
- `422 Unprocessable Entity` — invalid `session_id` (not a UUID or session not in workspace)

**Performance contract** (SC-001): `<= 2 s` p95 for workspaces up to 1,000 hypotheses.

---

### `GET /api/v1/discovery/{workspace_id}/proximity-settings`

Return the workspace's proximity settings. Lazy-creates a row with defaults if none exists.

**Response** `200 OK`:
```json
{
  "workspace_id": "uuid",
  "bias_enabled": true,
  "recompute_interval_minutes": 15,
  "last_recomputed_at": "2026-04-20T10:00:00Z",
  "last_transition_summary": {
    "clusters_newly_saturated": ["cluster-uuid-1"],
    "gaps_filled": [],
    "total_clusters": 12,
    "total_gaps": 3,
    "saturation_ratio": 0.25
  }
}
```

---

### `PATCH /api/v1/discovery/{workspace_id}/proximity-settings`

Update the workspace's bias toggle and/or recompute interval.

**Request**:
```json
{
  "bias_enabled": false,
  "recompute_interval_minutes": 30
}
```

Both fields optional — partial updates allowed.

**Response** `200 OK`: updated `ProximityWorkspaceSettingsResponse` (same shape as GET).

**Errors**:
- `403 Forbidden` — caller lacks `discovery:configure` on the workspace
- `422 Unprocessable Entity` — `recompute_interval_minutes` outside allowed range `[5, 240]`

---

### `POST /api/v1/discovery/{workspace_id}/proximity-graph/recompute`

Manually trigger an immediate workspace-scope recomputation. Enqueues background work; returns immediately.

**Request**: empty body.

**Response** `202 Accepted`:
```json
{
  "enqueued": true,
  "estimated_completion_seconds": 15
}
```

**Errors**:
- `403 Forbidden` — caller lacks `discovery:configure`
- `409 Conflict` — a recomputation is already in flight for this workspace

---

## Internal Service Interfaces

### New `ProximityGraphService` (in `apps/control-plane/src/platform/discovery/proximity/graph.py`)

```python
class ProximityGraphService:
    def __init__(
        self,
        embedder: HypothesisEmbedder,
        clustering: ProximityClustering,
        repository: DiscoveryRepository,
        event_publisher: DiscoveryEventPublisher,
        settings: DiscoverySettings,
    ): ...

    async def compute_workspace_graph(
        self,
        workspace_id: UUID,
        session_id: UUID | None = None,
        include_edges: bool = True,
    ) -> ProximityGraph:
        """
        1. Load embedded hypotheses for the workspace (optionally filtered by session_id).
        2. Return pre_proximity status if count < min_hypotheses.
        3. Delegate cluster computation to ProximityClustering.compute() — reuse existing logic.
        4. When include_edges: Qdrant batch search with k=max_neighbors_per_node.
        5. Map gap regions from clustering output.
        6. Build ProximityGraph response.
        """

    async def index_hypothesis(self, hypothesis_id: UUID) -> IndexResult:
        """
        Synchronously embed + upsert a single hypothesis.
        On success: update embedding_status='indexed', qdrant_point_id.
        On failure: update embedding_status='pending' or 'failed', log, emit metric.
        Never raises — caller (generation path) must not fail.
        """

    async def derive_bias_signal(
        self,
        workspace_id: UUID,
        session_id: UUID | None,
    ) -> BiasSignal:
        """
        1. Look up DiscoveryWorkspaceSettings.bias_enabled.
        2. Check min-hypothesis threshold for workspace (and session, if filtered).
        3. Load current HypothesisCluster rows.
        4. Build explore_hints (gap-region labels) and avoid_hints (over_explored cluster descriptions).
        5. Return BiasSignal with skipped=True + skip_reason if any gate fails.
        """

    async def recompute_workspace_graph(self, workspace_id: UUID) -> RecomputeResult:
        """
        1. Call compute_workspace_graph.
        2. Diff against previous HypothesisCluster rows — emit transition events.
        3. Upsert new HypothesisCluster rows (replacing previous).
        4. Update DiscoveryWorkspaceSettings.last_recomputed_at + last_transition_summary.
        5. Publish discovery.proximity_computed event (existing pattern).
        """
```

### Extended `DiscoveryRepository` (in `apps/control-plane/src/platform/discovery/repository.py`)

```python
# New methods:
async def get_workspace_settings(self, workspace_id: UUID) -> DiscoveryWorkspaceSettings | None
async def upsert_workspace_settings(
    self, workspace_id: UUID, **fields
) -> DiscoveryWorkspaceSettings
async def list_hypotheses_pending_embedding(
    self, workspace_id: UUID, limit: int = 100
) -> list[Hypothesis]
async def list_hypotheses_for_workspace(
    self, workspace_id: UUID, session_id: UUID | None = None,
    embedding_status: list[str] | None = None,
) -> list[Hypothesis]
async def replace_workspace_clusters(
    self, workspace_id: UUID, cluster_entries: list[HypothesisCluster]
) -> None
```

### Extended `DiscoveryService` (in `apps/control-plane/src/platform/discovery/service.py`)

```python
# New methods on existing DiscoveryService:
async def get_proximity_graph(
    self, workspace_id: UUID, session_id: UUID | None, include_edges: bool, max_nodes: int
) -> ProximityGraphResponse
async def get_workspace_proximity_settings(
    self, workspace_id: UUID
) -> ProximityWorkspaceSettingsResponse
async def update_workspace_proximity_settings(
    self, workspace_id: UUID, payload: ProximityWorkspaceSettingsUpdateRequest, actor: UUID
) -> ProximityWorkspaceSettingsResponse
async def enqueue_workspace_recompute(
    self, workspace_id: UUID, actor: UUID
) -> RecomputeEnqueuedResponse

# Scheduler entry point:
async def workspace_proximity_recompute_task(self) -> None
    """Iterates active workspaces and calls ProximityGraphService.recompute_workspace_graph."""
```

### Extended `_generate_hypotheses()` in `apps/control-plane/src/platform/discovery/gde/cycle.py`

Existing function extended with two additions (both guarded — on failure the generator still returns successfully):

1. **Before prompt assembly**: call `proximity_graph_service.derive_bias_signal(workspace_id, session_id)` and inject `bias_signal.explore_hints` + `bias_signal.avoid_hints` into the workflow execution's input context. Record `bias_signal` outcome on each created hypothesis's rationale metadata.
2. **After each hypothesis persist**: call `proximity_graph_service.index_hypothesis(hypothesis_id)` inside a try/except — never raises. Update `Hypothesis.embedding_status` accordingly.

### New scheduler task in `apps/control-plane/src/platform/discovery/proximity/scheduler.py`

```python
async def workspace_proximity_recompute_task(
    service: DiscoveryService,
    settings: DiscoverySettings,
) -> None:
    """
    Runs every proximity_graph_recompute_interval_minutes.
    For each active workspace with >=1 hypothesis:
      - Call service.workspace_proximity_recompute_task (wraps ProximityGraphService.recompute_workspace_graph).
      - Backfill pending embeddings in batches of N.
    """
```

Registered in `apps/control-plane/src/platform/main.py` lifespan alongside existing schedulers.

---

## Extended Schemas (`apps/control-plane/src/platform/discovery/schemas.py`)

Existing schemas preserved. New schemas added:

```python
class NodeEntry(BaseModel): ...
class EdgeEntry(BaseModel): ...
class GapRegionEntry(BaseModel): ...
class ProximityGraphResponse(BaseModel): ...            # workspace-scope graph
class ProximityWorkspaceSettingsResponse(BaseModel): ...
class ProximityWorkspaceSettingsUpdateRequest(BaseModel): ...
class RecomputeEnqueuedResponse(BaseModel): ...
```

Existing `ClusterListResponse`, `HypothesisClusterResponse`, `LandscapeStatus` are **unchanged** — session-scoped endpoints continue to return them byte-identically.
