# Quickstart & Acceptance Scenarios: Hypothesis Proximity Graph

**Feature**: 069-hypothesis-proximity-graph  
**Date**: 2026-04-20

## Setup Prerequisites

1. An active workspace with an ongoing discovery session.
2. Migration 056 applied.
3. Embedding provider reachable (`settings.memory.embedding_api_url`).
4. At least one operator principal with `discovery:configure` on the workspace.

---

## Scenario S1 — Query workspace proximity graph with ≥ min hypotheses

```bash
GET /api/v1/discovery/{workspace_id}/proximity-graph
```

With 50 embedded hypotheses across 3 known neighborhoods (25 in topic A, 15 in B, 10 spread in C).

Expected `200 OK`:
```json
{
  "workspace_id": "workspace-uuid",
  "status": "computed",
  "saturation_indicator": "saturated",
  "computed_at": "2026-04-20T10:15:00Z",
  "pending_embedding_count": 0,
  "clusters": [
    { "cluster_id": "cluster-a", "classification": "over_explored", "hypothesis_ids": [...] },
    { "cluster_id": "cluster-b", "classification": "normal", "hypothesis_ids": [...] }
  ],
  "gap_regions": [
    { "label": "...", "center_hypothesis_id": "..." }
  ],
  "edges": [ { "source_hypothesis_id": "...", "target_hypothesis_id": "...", "similarity": 0.87 } ]
}
```

---

## Scenario S2 — Pre-proximity status when workspace below threshold

```bash
# Workspace has 4 hypotheses; min_hypotheses=10.
GET /api/v1/discovery/{workspace_id}/proximity-graph
```

Expected `200 OK`:
```json
{
  "status": "pre_proximity",
  "min_hypotheses_required": 10,
  "current_embedded_count": 4,
  "nodes": [], "edges": [], "clusters": [], "gap_regions": []
}
```

---

## Scenario S3 — Session-scoped filter preserves existing behavior (backward compat)

```bash
# Session-scoped endpoint (existing):
GET /api/v1/discovery/sessions/{session_id}/clusters
# → returns ClusterListResponse byte-identical to pre-feature behavior (FR-017, SC-007)

# Same data via new endpoint with session filter:
GET /api/v1/discovery/{workspace_id}/proximity-graph?session_id={session_id}
# → returns ProximityGraphResponse scoped to that session's hypotheses only
```

---

## Scenario S4 — Bias-enabled generation injects gap hints into prompt

```bash
# Workspace has 30 hypotheses, 2 saturated clusters, 1 gap region.
# bias_enabled=true (default).
POST /api/v1/discovery/{session_id}/generate-cycle
```

Expected: each generated hypothesis's rationale metadata includes:
```json
{
  "bias_applied": true,
  "targeted_gap": "Multi-document synthesis in low-resource languages",
  "avoided_clusters": ["Retrieval augmentation over domain X"]
}
```

After 10 generations with bias, compute fraction landing outside saturated-cluster radius. Expected: ≥ 50% diversification lift vs. bias-disabled baseline (SC-002).

---

## Scenario S5 — Bias skipped when below min-hypothesis threshold

```bash
# Workspace has 4 hypotheses. Graph status is pre_proximity.
POST /api/v1/discovery/{session_id}/generate-cycle
```

Expected: hypothesis rationale metadata:
```json
{
  "bias_applied": false,
  "skip_reason": "insufficient_data",
  "min_hypotheses_required": 10,
  "current_embedded_count": 4
}
```

Generation proceeds normally (FR-009 extension — no bias ≠ no generation).

---

## Scenario S6 — Bias disabled for workspace

```bash
PATCH /api/v1/discovery/{workspace_id}/proximity-settings
{ "bias_enabled": false }

POST /api/v1/discovery/{session_id}/generate-cycle
```

Expected: rationale metadata:
```json
{
  "bias_applied": false,
  "skip_reason": "bias_disabled"
}
```

No `explore_hints` or `avoid_hints` appear in the generation prompt (parity with pre-feature behavior).

---

## Scenario S7 — Synchronous embedding on generation (happy path)

```bash
POST /api/v1/discovery/{session_id}/generate-cycle
# Returns within N seconds.

GET /api/v1/discovery/{workspace_id}/proximity-graph
# Response includes the new hypothesis as a node with embedding_status="indexed".
```

Verify: time between generation response and node visibility ≤ 5 s (SC-004).

---

## Scenario S8 — Embedding provider unavailable during generation

```bash
# Embedding provider returns 503 for 10 minutes.
POST /api/v1/discovery/{session_id}/generate-cycle
# Generation response: 201 Created (does NOT fail).

GET /api/v1/discovery/{workspace_id}/proximity-graph
# Response: pending_embedding_count = N
# Hypothesis appears in nodes[] with embedding_status="pending"
```

After provider recovers, next scheduler tick re-attempts. Verify: 100% of pending hypotheses transition to `indexed` within 2 recompute cycles (SC-006).

---

## Scenario S9 — Duplicate-embedding hypotheses land in same cluster

```bash
# Two hypotheses with byte-identical title+description content are generated.
GET /api/v1/discovery/{workspace_id}/proximity-graph
# Both appear as separate nodes.
# Both belong to the same cluster_id.
# An edge between them exists with similarity ≈ 1.0.
```

---

## Scenario S10 — Cluster-saturated event emitted on normal→over_explored transition

```bash
# Initial state: cluster-X classified "normal" (size=4, density=0.72).
# 3 new hypotheses added clustering near cluster-X centroid.
# Next recompute: cluster-X is now "over_explored" (size=7, density=0.88).
```

Expected Kafka event on `discovery.events`:
```json
{
  "event_type": "discovery.proximity.cluster_saturated",
  "payload": {
    "workspace_id": "...",
    "cluster_id": "cluster-X",
    "classification_from": "normal",
    "classification_to": "over_explored",
    "member_count": 7,
    "density": 0.88
  }
}
```

---

## Scenario S11 — Gap-filled event emitted when previous gap is consumed

```bash
# Recompute N: gap_regions includes "Multi-document synthesis" (label L).
# Several hypotheses are added around that region.
# Recompute N+1: label L no longer appears in gap_regions.
```

Expected Kafka event:
```json
{
  "event_type": "discovery.proximity.gap_filled",
  "payload": {
    "workspace_id": "...",
    "former_gap_label": "Multi-document synthesis",
    "now_part_of_cluster_id": "cluster-new"
  }
}
```

---

## Scenario S12 — Staleness annotation on read when beyond warning interval

```bash
# last_recomputed_at was 90 minutes ago; staleness_warning_minutes=60.
GET /api/v1/discovery/{workspace_id}/proximity-graph
```

Expected `200 OK` with:
```json
{
  "status": "computed",
  "computed_at": "2026-04-20T08:45:00Z",
  "staleness_warning": "Graph last computed 90 minutes ago; staleness threshold is 60 minutes."
}
```

No synchronous recomputation triggered (reads never trigger compute — D-007).

---

## Scenario S13 — Manual recompute trigger

```bash
POST /api/v1/discovery/{workspace_id}/proximity-graph/recompute
# → 202 Accepted, { "enqueued": true, "estimated_completion_seconds": 15 }

# Within estimated_completion_seconds:
GET /api/v1/discovery/{workspace_id}/proximity-settings
# last_recomputed_at advanced to current time.
```

Second concurrent recompute call → `409 Conflict: recompute_in_flight`.

---

## Scenario S14 — Update workspace settings

```bash
PATCH /api/v1/discovery/{workspace_id}/proximity-settings
{ "recompute_interval_minutes": 5, "bias_enabled": false }
# → 200 OK, updated settings returned.

# Scheduler respects the new per-workspace interval on next tick.
```

---

## Scenario S15 — Workspace isolation

```bash
# Hypothesis H-a in workspace A is semantically identical to H-b in workspace B.
GET /api/v1/discovery/{workspace_a_id}/proximity-graph
# H-a appears; H-b does NOT (cross-workspace isolation).
```

---

## Scenario S16 — Hypothesis deletion reflected on next recompute

```bash
# Hypothesis H1 belongs to cluster-A.
DELETE /api/v1/discovery/hypotheses/{H1}   # or equivalent archival action

# Before next recompute: GET proximity-graph still shows H1 in cluster-A (stale).
# Next scheduled recompute tick runs.
# After: GET proximity-graph shows H1 absent from nodes and cluster-A.
```

---

## Scenario S17 — Scale ceiling: truncation flag

```bash
# Workspace has 12,000 hypotheses; max_nodes default is 10,000.
GET /api/v1/discovery/{workspace_id}/proximity-graph
```

Expected `200 OK` with `"truncated": true`. Response includes the 10,000 most-recent hypotheses.

---

## Scenario S18 — Session-level session-scoped cluster computation preserved byte-identically

```bash
# Invoke pre-feature endpoint on a session that existed before feature 069 shipped.
POST /api/v1/discovery/sessions/{session_id}/compute-proximity
# → 202 Accepted, existing ClusterListResponse body returned — byte-identical (SC-007).
```

No new fields added to the legacy response shape. New fields live only on `ProximityGraphResponse`.
