# Implementation Plan: Hypothesis Proximity Graph

**Branch**: `069-hypothesis-proximity-graph` | **Date**: 2026-04-20 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/069-hypothesis-proximity-graph/spec.md`

## Summary

Extend the **already-existing** `discovery/proximity/` module to (1) expose a workspace-scope proximity graph endpoint, (2) index newly-generated hypotheses synchronously into Qdrant with a `pending` fallback when the embedding provider is down, (3) derive a bias signal (explore-hints from gap regions + avoid-hints from over-explored clusters) that the hypothesis-generator prompt injects at generation time, (4) schedule periodic workspace-scope recomputation that emits transition events on saturation/gap-fill, and (5) add per-workspace settings for bias on/off and recompute interval. **What exists**: `HypothesisEmbedder`, `ProximityClustering`, `HypothesisCluster` table, session-scoped cluster endpoints, `discovery.proximity_computed` event. **What this feature adds**: 1 new service (`ProximityGraphService`), 1 new scheduler, 1 new table (`discovery_workspace_settings`), 1 new column (`discovery_hypotheses.embedding_status`), 4 new REST endpoints, 2 new Kafka event types, 4 new `DiscoverySettings` fields, and a wire-in at `discovery/gde/cycle.py::_generate_hypotheses()` for sync-index + bias-hint injection. Migration 056 is a single atomic migration that also backfills `embedding_status` from existing `qdrant_point_id`.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, qdrant-client 1.12+ async gRPC, scipy ≥ 1.13 (existing — used by `ProximityClustering`), APScheduler 3.x — all already in requirements.txt  
**Storage**: PostgreSQL 16 (1 new table + 1 new column + 1 partial index via Alembic 056); Qdrant collection `discovery_hypotheses` (reused — no schema change); no Neo4j, no ClickHouse, no Redis keys added  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux, Kubernetes  
**Project Type**: Web service — additive extension in existing FastAPI monolith  
**Performance Goals**: Workspace proximity-graph read p95 ≤ 2 s for 1,000 hypotheses (SC-001); ≥ 95% of newly generated hypotheses appear in graph within 5 s (SC-004); cluster-transition events emitted within one recompute interval with zero missed transitions on deterministic replay (SC-005)  
**Constraints**: Preserve session-level proximity endpoints byte-identically (SC-007, FR-017); generation MUST NOT fail on embedding errors (FR-009); reads MUST NOT trigger synchronous recomputation (D-007 via edge case)  
**Scale/Scope**: 1 new service class, 1 new scheduler file, 4 modified files in `discovery/`, 1 migration, 4 new `DiscoverySettings` fields; ~10 files total

## Constitution Check

*All principles checked against this feature design.*

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | All changes inside existing `discovery/` bounded context |
| **Principle III** — Dedicated data stores | ✅ PASS | Qdrant for vectors (reused); PostgreSQL only for settings + embedding-status flag; **no vectors in PostgreSQL** |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `discovery_workspace_settings` table is owned by discovery context; workspace-membership check uses existing injected `workspaces_service` interface |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | Access control reuses existing workspace RBAC; bias is advisory (per Assumptions) not a policy gate |
| **Principle VIII** — FQN addressing | ✅ PASS | N/A at hypothesis-level; workspace addressing follows existing UUID pattern |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Proximity graph queries workspace-scoped via existing RBAC |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | No LLM calls introduced; existing embedding call goes through provider client |
| **Reminder 4** — No vectors in PostgreSQL | ✅ PASS | Vectors stay in Qdrant; PostgreSQL stores only `embedding_status` flag |
| **Reminder 23** — Evaluate trajectories, not just outputs | ✅ PASS | Feature tracks cluster evolution over time (trajectory analog for proximity) |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | `embeddings.py`, `clustering.py`, `gde/cycle.py` extended additively; no file replaced wholesale |
| **Brownfield Rule 2** — Alembic migrations | ✅ PASS | All DDL in migration 056 |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Session-level proximity endpoints untouched; existing tests continue to pass (verified in tasks polish phase) |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Repository/service/scheduler-in-lifespan/Kafka envelope/dependency-injection patterns all reused |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | All modified files cited below with exact paths |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | Existing `ClusterListResponse` endpoints preserved byte-identically; new `ProximityGraphResponse` is a new shape on a new endpoint |

No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/069-hypothesis-proximity-graph/
├── plan.md              ✅ This file
├── spec.md              ✅ Feature specification
├── research.md          ✅ Phase 0 output
├── data-model.md        ✅ Phase 1 output
├── quickstart.md        ✅ Phase 1 output
├── contracts/
│   └── rest-api.md      ✅ Phase 1 output
└── checklists/
    └── requirements.md  ✅ Spec validation (all pass)
```

### Source Code

```text
apps/control-plane/
├── migrations/versions/
│   └── 056_proximity_graph_workspace.py               # NEW: 1 table + 1 column + 1 partial index + backfill
└── src/platform/
    ├── discovery/
    │   ├── proximity/
    │   │   ├── __init__.py                            # MODIFY: export ProximityGraphService
    │   │   ├── embeddings.py                          # NO CHANGE (reused as-is)
    │   │   ├── clustering.py                          # NO CHANGE (reused as-is)
    │   │   ├── graph.py                               # NEW: ProximityGraphService (compute_workspace_graph, index_hypothesis, derive_bias_signal, recompute_workspace_graph)
    │   │   └── scheduler.py                           # NEW: workspace_proximity_recompute_task
    │   ├── gde/
    │   │   └── cycle.py                               # MODIFY: _generate_hypotheses() wires bias-signal into prompt + sync-indexes new hypotheses via try/except
    │   ├── models.py                                  # MODIFY: add Hypothesis.embedding_status column + DiscoveryWorkspaceSettings model
    │   ├── schemas.py                                 # MODIFY: add ProximityGraphResponse, NodeEntry, EdgeEntry, GapRegionEntry, ProximityWorkspaceSettingsResponse, ProximityWorkspaceSettingsUpdateRequest, RecomputeEnqueuedResponse
    │   ├── repository.py                              # MODIFY: add get/upsert_workspace_settings, list_hypotheses_pending_embedding, list_hypotheses_for_workspace, replace_workspace_clusters
    │   ├── service.py                                 # MODIFY: add get_proximity_graph, get_workspace_proximity_settings, update_workspace_proximity_settings, enqueue_workspace_recompute + workspace_proximity_recompute_task entry-point
    │   ├── router.py                                  # MODIFY: add 4 new routes (GET /{workspace_id}/proximity-graph, GET/PATCH /{workspace_id}/proximity-settings, POST /{workspace_id}/proximity-graph/recompute)
    │   ├── events.py                                  # MODIFY: add 2 new event types (cluster_saturated, gap_filled)
    │   └── dependencies.py                            # MODIFY: wire ProximityGraphService + inject into DiscoveryService
    ├── common/config.py                               # MODIFY: DiscoverySettings adds 4 fields (proximity_graph_max_neighbors_per_node, proximity_graph_recompute_interval_minutes, proximity_graph_staleness_warning_minutes, proximity_bias_default_enabled)
    └── main.py                                        # MODIFY: register workspace_proximity_recompute_task in lifespan

apps/control-plane/tests/
├── unit/discovery/
│   ├── test_proximity_graph_service.py               # NEW: unit tests for compute_workspace_graph, index_hypothesis, derive_bias_signal, recompute transitions
│   ├── test_gde_cycle_bias_wiring.py                 # NEW: unit tests for bias injection + sync-index with embed-failure path
│   └── test_proximity_scheduler.py                   # NEW: scheduler iterates workspaces, handles per-workspace failures
└── integration/
    └── discovery/
        └── test_proximity_graph_integration.py       # NEW: end-to-end propose → embed → recompute → transition-event → bias-loop
```

## Complexity Tracking

No constitution violations.

**Highest risk**: D-006 — wiring synchronous embedding into `gde/cycle.py::_generate_hypotheses()`. The existing generator does not embed; adding a sync call with try/except changes the timing of the generation response. Mitigation: the try/except is non-propagating (FR-009 is enforced by design), and `ProximityGraphService.index_hypothesis()` is specified to never raise — it translates every failure into an `embedding_status` update and a log+metric emission. Integration test exercises both happy path (sync embed success) and degraded path (embedding provider 503 for 10 minutes).

**Second risk**: D-003 — top-k edges computed at read time via Qdrant batch search. If Qdrant latency degrades under load, the 2 s p95 target (SC-001) could slip. Mitigation: `include_edges=false` query param lets callers opt out of edge computation; the `max_nodes` cap ensures the O(n·k) Qdrant calls stay bounded; response-level `truncated=true` flag surfaces any cap activation.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: Extend existing `discovery/proximity/` — not `discovery/services/`. Flat layout is the established pattern.
- **D-002**: `ProximityGraphService` lives in new file `discovery/proximity/graph.py` — single-responsibility service composing existing embedder + clustering.
- **D-003**: No Neo4j. Edges computed in-memory at read time via Qdrant top-k batch search; `proximity_graph_max_neighbors_per_node=8` caps fan-out.
- **D-004**: Workspace-level bias toggle lives in new `discovery_workspace_settings` table (not in `DiscoverySession.config` JSONB, not on `workspaces` table).
- **D-005**: `discovery_hypotheses.embedding_status VARCHAR(16)` column with `pending/indexed/failed` values; partial index for pending rows.
- **D-006**: Sync embedding in `_generate_hypotheses()` via try/except — FR-009 never fails generation.
- **D-007**: Bias signal derived at generation time, not precomputed; O(k) cluster lookup is cheap.
- **D-008**: New workspace-scope scheduler task; existing session-scope `proximity_clustering_task` preserved byte-identical.
- **D-009**: Cluster-transition events emitted only on state change (`normal` → `over_explored` or gap filled), not on every recomputation; tolerance band prevents flapping.
- **D-010**: New `ProximityGraphResponse` is additive — existing `ClusterListResponse` unchanged.
- **D-011**: Extend existing `DiscoverySettings` with 4 new fields — no new settings class.
- **D-012**: Migration 056 is atomic: adds column + backfills from `qdrant_point_id` presence + creates new table + creates partial index. `down_revision = "055_adaptation_pipeline_and_proficiency"`.

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 1 new table, 1 new column on existing, 1 partial index, 2 new Kafka event types; derived in-memory entities (`ProximityGraph`, `NodeEntry`, `EdgeEntry`, `GapRegion`, `BiasSignal`) specified as response-only types.
- [contracts/rest-api.md](contracts/rest-api.md) — 4 new REST endpoints + 1 new internal service class (`ProximityGraphService`) + 1 extended service (`DiscoveryService`) + extended repository.
- [quickstart.md](quickstart.md) — 18 acceptance scenarios (S1–S18) covering pre-proximity status, bias application, embedding failure fallback, cluster transitions, staleness annotation, manual recompute, workspace isolation, scale-ceiling truncation, and backward compatibility.
