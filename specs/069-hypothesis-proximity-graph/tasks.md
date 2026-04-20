---
description: "Task list for 069-hypothesis-proximity-graph implementation"
---

# Tasks: Hypothesis Proximity Graph

**Input**: Design documents from `specs/069-hypothesis-proximity-graph/`
**Branch**: `069-hypothesis-proximity-graph`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = Graph Observability (P1), US2 = Generation Bias (P1), US3 = Per-hypothesis Indexing (P2)

---

## Phase 1: Setup

**Purpose**: Migration + config extensions that unblock all downstream work.

- [X] T001 Add Alembic migration `056_proximity_graph_workspace.py` in `apps/control-plane/migrations/versions/`: ADD COLUMN `embedding_status VARCHAR(16) NOT NULL DEFAULT 'pending'` on `discovery_hypotheses`, backfill (`indexed` where `qdrant_point_id IS NOT NULL`, `pending` elsewhere), CREATE TABLE `discovery_workspace_settings`, CREATE partial index `ix_discovery_hypotheses_embedding_pending ON (workspace_id) WHERE embedding_status = 'pending'`
- [X] T002 [P] Add 4 new fields to `DiscoverySettings` in `apps/control-plane/src/platform/common/config.py`: `proximity_graph_max_neighbors_per_node: int = 8`, `proximity_graph_recompute_interval_minutes: int = 15`, `proximity_graph_staleness_warning_minutes: int = 60`, `proximity_bias_default_enabled: bool = True`

**Checkpoint**: Migration can be applied; config loads without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data layer — models, schemas, repository extensions, new event types — that all three user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add `embedding_status` column to `Hypothesis` SQLAlchemy model and add `DiscoveryWorkspaceSettings` SQLAlchemy model in `apps/control-plane/src/platform/discovery/models.py`: `Hypothesis.embedding_status: Mapped[str]` (default `"pending"`); new `DiscoveryWorkspaceSettings` model with `workspace_id UUID PK`, `bias_enabled BOOL`, `recompute_interval_minutes INT`, `last_recomputed_at TIMESTAMPTZ`, `last_transition_summary JSONB`, timestamps
- [X] T004 [P] Add new Pydantic schemas in `apps/control-plane/src/platform/discovery/schemas.py`: `NodeEntry`, `EdgeEntry`, `GapRegionEntry`, `ClusterEntry` (workspace-scope), `ProximityGraphResponse` (with `status`, `saturation_indicator`, `computed_at`, `staleness_warning`, `pending_embedding_count`, `truncated`, `nodes`, `edges`, `clusters`, `gap_regions`), `ProximityWorkspaceSettingsResponse`, `ProximityWorkspaceSettingsUpdateRequest` (optional `bias_enabled`, `recompute_interval_minutes` validated in `[5, 240]`), `RecomputeEnqueuedResponse` — leave existing `ClusterListResponse` and `HypothesisClusterResponse` byte-identical
- [X] T005 [P] Add 2 new event types in `apps/control-plane/src/platform/discovery/events.py`: `discovery.proximity.cluster_saturated` (payload: `workspace_id`, `cluster_id`, `classification_from`, `classification_to`, `member_count`, `density`) and `discovery.proximity.gap_filled` (payload: `workspace_id`, `former_gap_label`, `now_part_of_cluster_id`)
- [X] T006 Add 5 new repository methods in `apps/control-plane/src/platform/discovery/repository.py`: `get_workspace_settings(workspace_id) -> DiscoveryWorkspaceSettings | None`, `upsert_workspace_settings(workspace_id, **fields) -> DiscoveryWorkspaceSettings`, `list_hypotheses_pending_embedding(workspace_id, limit=100) -> list[Hypothesis]`, `list_hypotheses_for_workspace(workspace_id, session_id=None, embedding_status=None) -> list[Hypothesis]`, `replace_workspace_clusters(workspace_id, cluster_entries) -> None`

**Checkpoint**: Foundation models, schemas, events, and repository are in place; existing tests still pass.

---

## Phase 3: User Story 1 — Graph Observability (Priority: P1) 🎯 MVP

**Goal**: Operators can query a workspace-scope proximity graph (nodes, edges, clusters, gap regions, saturation indicator) and read/update per-workspace proximity settings. A background scheduler keeps the graph up to date and emits cluster-transition events.

**Independent Test**: `GET /{workspace_id}/proximity-graph` returns `200 OK` with `status: computed` after running a recompute; `GET /{workspace_id}/proximity-settings` returns current settings; `PATCH` updates them; `POST /recompute` enqueues work and returns `202 Accepted`.

### Unit Tests for User Story 1

- [X] T007 [P] [US1] Add unit tests for `ProximityGraphService.compute_workspace_graph` in `apps/control-plane/tests/unit/discovery/test_proximity_graph_service.py`: pre-proximity path (< min hypotheses → `status: pre_proximity`), computed path (clusters + edges + gap regions), `include_edges=false` skips Qdrant batch search, `max_nodes` cap sets `truncated=true`, staleness annotation when `last_recomputed_at` > threshold
- [X] T008 [P] [US1] Add unit tests for `recompute_workspace_graph` transition detection in `apps/control-plane/tests/unit/discovery/test_proximity_graph_service.py`: `normal→over_explored` emits `cluster_saturated` event, gap disappearing emits `gap_filled` event, no-change recompute emits no transition events, tolerance-band prevents flap
- [X] T009 [P] [US1] Add unit tests for `workspace_proximity_recompute_task` scheduler in `apps/control-plane/tests/unit/discovery/test_proximity_scheduler.py`: iterates all active workspaces, per-workspace failure is caught and does not abort other workspaces, backfills pending-embedding hypotheses in batches

### Implementation for User Story 1

- [X] T010 [US1] Create `apps/control-plane/src/platform/discovery/proximity/graph.py` with `ProximityGraphService` class: constructor accepts `HypothesisEmbedder`, `ProximityClustering`, `DiscoveryRepository`, `DiscoveryEventPublisher`, `DiscoverySettings`; implement `compute_workspace_graph(workspace_id, session_id=None, include_edges=True) -> ProximityGraph` — loads hypotheses via `repository.list_hypotheses_for_workspace`, returns `pre_proximity` status if count < min threshold, delegates cluster computation to existing `ProximityClustering.compute()`, builds edges via Qdrant `search_batch` when `include_edges=True` (k=`max_neighbors_per_node`, self-edges removed, lower-UUID-first), maps gap regions from clustering output, attaches `staleness_warning` from `last_recomputed_at`, sets `truncated=true` if `max_nodes` cap activated
- [X] T011 [US1] Add `recompute_workspace_graph(workspace_id) -> RecomputeResult` method to `ProximityGraphService` in `apps/control-plane/src/platform/discovery/proximity/graph.py`: calls `compute_workspace_graph`, reads previous `HypothesisCluster` rows for workspace, diffs classification and gap-region membership with tolerance band (±0.02 density), emits `cluster_saturated` events for `normal→over_explored` transitions and `gap_filled` events for disappeared gap regions, calls `repository.replace_workspace_clusters`, updates `DiscoveryWorkspaceSettings.last_recomputed_at` + `last_transition_summary`, publishes existing `discovery.proximity_computed` event
- [X] T012 [US1] Create `apps/control-plane/src/platform/discovery/proximity/scheduler.py` with `workspace_proximity_recompute_task(service, settings)`: queries all active workspaces with ≥1 hypothesis, calls `service.workspace_proximity_recompute_task(workspace_id)` per workspace (wrapping each in try/except to isolate per-workspace failures), calls `repository.list_hypotheses_pending_embedding` + `ProximityGraphService.index_hypothesis` in batches of 100
- [X] T013 [US1] Export `ProximityGraphService` from `apps/control-plane/src/platform/discovery/proximity/__init__.py`
- [X] T014 [US1] Add 4 new service methods to `DiscoveryService` in `apps/control-plane/src/platform/discovery/service.py`: `get_proximity_graph(workspace_id, session_id, include_edges, max_nodes) -> ProximityGraphResponse` (delegates to `ProximityGraphService.compute_workspace_graph`, serializes to response schema), `get_workspace_proximity_settings(workspace_id) -> ProximityWorkspaceSettingsResponse` (lazy-creates row with defaults via `repository.upsert_workspace_settings`), `update_workspace_proximity_settings(workspace_id, payload, actor) -> ProximityWorkspaceSettingsResponse`, `enqueue_workspace_recompute(workspace_id, actor) -> RecomputeEnqueuedResponse` (409 if recompute already in flight); add `workspace_proximity_recompute_task(self) -> None` entry point that iterates active workspaces
- [X] T015 [US1] Add 4 new routes to `apps/control-plane/src/platform/discovery/router.py`: `GET /{workspace_id}/proximity-graph` (query params: `session_id`, `include_edges`, `max_nodes`; 404 if workspace not found/no access), `GET /{workspace_id}/proximity-settings`, `PATCH /{workspace_id}/proximity-settings` (requires `discovery:configure`; 403 if unauthorized), `POST /{workspace_id}/proximity-graph/recompute` (requires `discovery:configure`; 409 if in flight)

**Checkpoint**: `GET /{workspace_id}/proximity-graph` returns a valid `ProximityGraphResponse`; transition events appear in Kafka on cluster-state changes; existing session-level cluster endpoints still return byte-identical responses.

---

## Phase 4: User Story 2 — Generation Bias (Priority: P1)

**Goal**: Hypothesis generation is guided by the proximity graph — explore-hints from gap regions + avoid-hints from over-explored clusters are injected into the prompt when bias is enabled. Bias can be disabled per workspace. The rationale metadata on each generated hypothesis records whether bias was applied.

**Independent Test**: `POST /discovery/{session_id}/generate-cycle` with `bias_enabled=true` produces hypotheses whose rationale metadata includes `bias_applied: true`, `targeted_gap`, and `avoided_clusters`. With `bias_enabled=false` (after PATCH), metadata shows `skip_reason: bias_disabled`. Below threshold shows `skip_reason: insufficient_data`.

### Unit Tests for User Story 2

- [X] T016 [P] [US2] Add unit tests for `derive_bias_signal` in `apps/control-plane/tests/unit/discovery/test_proximity_graph_service.py`: `bias_enabled=false` returns `BiasSignal(skipped=True, skip_reason="bias_disabled")`; below min threshold returns `BiasSignal(skipped=True, skip_reason="insufficient_data")`; happy path returns populated `explore_hints` (gap labels) and `avoid_hints` (over_explored cluster descriptions)
- [X] T017 [P] [US2] Add unit tests for bias injection in `_generate_hypotheses()` in `apps/control-plane/tests/unit/discovery/test_gde_cycle_bias_wiring.py`: bias signal injected into workflow execution input context when `skipped=False`; rationale metadata records `bias_applied`, `targeted_gap`, `avoided_clusters`; when `BiasSignal.skipped=True` no hints appear in prompt; generation succeeds in both cases

### Implementation for User Story 2

- [X] T018 [US2] Add `derive_bias_signal(workspace_id, session_id) -> BiasSignal` method to `ProximityGraphService` in `apps/control-plane/src/platform/discovery/proximity/graph.py`: reads `DiscoveryWorkspaceSettings.bias_enabled` (lazy-creates with defaults if absent); returns `BiasSignal(skipped=True, skip_reason="bias_disabled")` if `bias_enabled=False`; counts embedded hypotheses for workspace (or session if `session_id` provided); returns `BiasSignal(skipped=True, skip_reason="insufficient_data")` if count < min threshold; loads current `HypothesisCluster` rows; builds `explore_hints` from gap-region labels and `avoid_hints` from `over_explored` cluster centroid descriptions; returns `BiasSignal` with `source="workspace_scope"` or `"session_scope"`
- [X] T019 [US2] Extend `_generate_hypotheses()` in `apps/control-plane/src/platform/discovery/gde/cycle.py` with bias-signal injection (Part 1 of the wire-in): before prompt assembly, call `proximity_graph_service.derive_bias_signal(workspace_id, session_id)` inside try/except (signal failure must not abort generation); when `bias_signal.skipped=False` inject `explore_hints` and `avoid_hints` into the workflow execution input context; record `bias_signal` outcome on each created hypothesis's rationale metadata (`bias_applied`, `targeted_gap`, `avoided_clusters`, or `skip_reason`)

**Checkpoint**: Hypothesis rationale metadata includes `bias_applied` field; `PATCH /{workspace_id}/proximity-settings {"bias_enabled": false}` followed by a generation cycle produces `skip_reason: bias_disabled` in metadata.

---

## Phase 5: User Story 3 — Per-hypothesis Indexing (Priority: P2)

**Goal**: Every newly generated hypothesis is synchronously embedded into Qdrant immediately after persistence. If the embedding provider is unavailable, the hypothesis is saved with `embedding_status=pending` and the scheduled recomputation retries it. Generation never fails due to embedding errors.

**Independent Test**: After `POST /generate-cycle`, `GET /{workspace_id}/proximity-graph` shows the new hypothesis node with `embedding_status: indexed` (happy path). When embedding provider returns 503, generation still returns `201 Created`, and `pending_embedding_count` increments; after provider recovery, next scheduler tick transitions the node to `indexed`.

### Unit Tests for User Story 3

- [X] T020 [P] [US3] Add unit tests for `index_hypothesis` in `apps/control-plane/tests/unit/discovery/test_proximity_graph_service.py`: success path sets `embedding_status=indexed` and `qdrant_point_id`; provider 503 sets `embedding_status=pending`, logs, emits metric, does NOT raise; non-transient provider error (invalid content) sets `embedding_status=failed`; method never raises under any condition

### Implementation for User Story 3

- [X] T021 [US3] Add `index_hypothesis(hypothesis_id) -> IndexResult` method to `ProximityGraphService` in `apps/control-plane/src/platform/discovery/proximity/graph.py`: loads hypothesis from repository; calls `HypothesisEmbedder.embed_hypothesis()` inside try/except; on success updates `embedding_status=indexed` + `qdrant_point_id` via repository; on transient failure updates `embedding_status=pending`, logs warning, emits metric; on non-transient (bad content) failure updates `embedding_status=failed`, logs error, emits metric; NEVER raises — callers must not fail
- [X] T022 [US3] Extend `_generate_hypotheses()` in `apps/control-plane/src/platform/discovery/gde/cycle.py` with sync-embed try/except (Part 2 of the wire-in): after each hypothesis is persisted, call `await proximity_graph_service.index_hypothesis(hypothesis_id)` inside try/except; catch any unexpected exception, log it, update `embedding_status=pending`, and continue — generation response must NOT propagate embedding errors (FR-009)
- [X] T023 [US3] Add end-to-end integration test in `apps/control-plane/tests/integration/discovery/test_proximity_graph_integration.py`: propose → persist hypothesis → sync embed → verify `indexed` node appears in proximity-graph response within 5 s (SC-004); provider-503 path: generation returns `201`, `pending_embedding_count` increments, scheduler tick retries, node transitions to `indexed` within 2 cycles (SC-006); transition-event path: fill cluster to `over_explored`, trigger recompute, verify `cluster_saturated` Kafka event; bias loop: generate with bias enabled, verify `explore_hints` injected, generated hypotheses target gap region

---

## Phase 6: Polish & Cross-cutting Concerns

**Purpose**: Wire everything together, register scheduler, update dependency injection, verify backward compatibility.

- [X] T024 Wire `ProximityGraphService` into `apps/control-plane/src/platform/discovery/dependencies.py`: instantiate with `HypothesisEmbedder`, `ProximityClustering`, `DiscoveryRepository`, `DiscoveryEventPublisher`, `DiscoverySettings`; inject into `DiscoveryService`
- [X] T025 [P] Register `workspace_proximity_recompute_task` in `apps/control-plane/src/platform/main.py` lifespan: schedule with APScheduler using `proximity_graph_recompute_interval_minutes` as default interval; preserve existing `proximity_clustering_task` registration byte-identical (SC-007)
- [X] T026 [P] Verify backward compatibility: run existing session-level cluster endpoint tests (`GET /sessions/{session_id}/clusters` and `POST /sessions/{session_id}/compute-proximity`) and confirm `ClusterListResponse` shape is byte-identical to pre-feature behavior (SC-007, FR-017)

---

## Dependencies

### User Story Dependencies

- **US1 (P1 — Graph Observability)**: Can start after Phase 2 complete — no dependency on US2/US3
- **US2 (P1 — Generation Bias)**: Can start after Phase 2 complete; Phase 4 T019 requires `derive_bias_signal` from T018 and the `index_hypothesis`-aware data model from T003; bias wire-in in `gde/cycle.py` is additive to but independent of the sync-embed wire-in
- **US3 (P2 — Per-hypothesis Indexing)**: Can start after Phase 2 complete; T022 (sync-embed wire-in in `cycle.py`) MUST follow T019 (bias wire-in) to avoid merge conflicts on the same function — sequence within `_generate_hypotheses()`: bias injection first (T019), sync-embed second (T022)

### Within Each Phase

- T001 (migration) before T003 (models reference new column)
- T003 (models) before T006 (repository references models)
- T006 (repository) before T010 (graph service uses repository)
- T010 (`compute_workspace_graph`) before T011 (`recompute_workspace_graph` calls it)
- T011 before T012 (scheduler calls `recompute_workspace_graph`)
- T014 (service methods) before T015 (router calls service)
- T018 (`derive_bias_signal`) before T019 (bias wire-in calls it)
- T021 (`index_hypothesis`) before T022 (sync-embed wire-in calls it)
- T024 (dependency wiring) before T025 (scheduler registration uses wired service)

---

## Parallel Opportunities

```bash
# Phase 1 — run in parallel:
Task T001: migration 056
Task T002: config.py DiscoverySettings extensions

# Phase 2 — T003 first (models), then T004/T005 in parallel, then T006:
Task T003: models.py
# After T003:
Task T004: schemas.py
Task T005: events.py
# After T004 + T005:
Task T006: repository.py

# US1 — tests in parallel with each other, then implementation in sequence:
Task T007: unit tests compute_workspace_graph
Task T008: unit tests recompute transition detection
Task T009: unit tests scheduler
# Implementation (T010→T011→T012 sequential; T013/T014/T015 sequential):
T010 → T011 → T012 → T013 → T014 → T015

# US2 — T016/T017 in parallel (tests), then T018→T019:
Task T016: unit tests derive_bias_signal
Task T017: unit tests bias injection in cycle.py

# US3 — T020 unit test in parallel, then T021→T022→T023:
Task T020: unit tests index_hypothesis

# Phase 6 — T024 first, then T025/T026 in parallel:
Task T025: main.py scheduler registration
Task T026: backward-compat verification
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only — skip US3)

1. Phase 1: Migration + config
2. Phase 2: Foundational (models, schemas, events, repository)
3. Phase 3: US1 Graph Observability — workspace proximity graph endpoints + scheduler + transition events
4. **STOP and VALIDATE**: `GET /{workspace_id}/proximity-graph` works; scheduler emits events
5. Phase 4: US2 Generation Bias — `derive_bias_signal` + `_generate_hypotheses()` bias injection
6. **STOP and VALIDATE**: Generated hypotheses include `bias_applied` metadata
7. Deploy/demo

### Full Delivery (all three stories)

1. Phases 1–4 as above
2. Phase 5: US3 Per-hypothesis Indexing — `index_hypothesis` + sync-embed wire-in + integration tests
3. Phase 6: Polish — dependency wiring + scheduler registration + backward-compat check
4. **Final Validation**: All 18 quickstart scenarios pass (S1–S18)

### Parallel Team Strategy

With two developers after Phase 2:
- Developer A: US1 (T007–T015) — graph service + scheduler + routes
- Developer B: US2 (T016–T019) — bias signal + cycle.py Part 1
- After US1 and US2: both converge on US3 (T020–T023) + Phase 6 (T024–T026)

---

## Notes

- **Highest-risk task**: T022 (sync-embed wire-in in `_generate_hypotheses()`) — sequence it after T019 (bias wire-in) to avoid conflicts; both changes touch the same function
- **Never-raises invariant**: `index_hypothesis` and `derive_bias_signal` MUST be wrapped in try/except at every call site in `cycle.py`; generation must return `201 Created` regardless of embedding/bias-signal outcome (FR-009)
- **Session-level backward compat**: Do NOT modify `ClusterListResponse`, `HypothesisClusterResponse`, `LandscapeStatus`, or the `GET/POST /sessions/{session_id}/clusters|compute-proximity` handlers (SC-007, FR-017)
- **No vectors in PostgreSQL**: `embedding_status` is a string flag only; vectors stay in Qdrant (Reminder 4)
- **[P]** tasks have different file targets and no incomplete-task dependencies — safe to run concurrently
