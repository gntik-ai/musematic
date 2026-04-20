# Feature Specification: Hypothesis Proximity Graph

**Feature Branch**: `069-hypothesis-proximity-graph`  
**Created**: 2026-04-20  
**Status**: Draft  
**Input**: Brownfield extension to the `discovery/` bounded context. The discovery pipeline generates hypotheses that are then critiqued, experimented on, and ranked. Without a mechanism to measure how hypotheses relate to one another in semantic space, the generation step drifts into the same neighborhoods repeatedly — quality engineers see tournament leaderboards dominated by near-duplicates, and agents keep re-exploring already-saturated ideas while genuinely underexplored regions receive no attention. This feature formalizes a **Hypothesis Proximity Graph**: every generated hypothesis is embedded into vector space, placed on a graph whose edges encode semantic proximity, and clustered so the system can identify which regions are over-explored ("saturation") and which are gaps. Subsequent hypothesis generation is then biased away from saturated regions and toward the gaps, turning proximity information into a feedback loop that improves exploration diversity over the life of a discovery session and workspace. The feature extends existing proximity infrastructure (already present at session scope) to workspace scope and wires the gap signal into the hypothesis-generation prompt.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Quality Engineer Inspects the Proximity Graph for a Discovery Workspace (Priority: P1)

A quality engineer opens the proximity view for a discovery workspace and sees a graph where each node is a hypothesis and edges connect hypotheses that are semantically close. Hypotheses group visibly into clusters; each cluster is labeled with a density classification (under-explored / normal / over-explored) and shows which hypotheses belong to it. The engineer can see at a glance which regions of the idea-space the workspace has covered heavily and which it has not — without manually reading every hypothesis.

**Why this priority**: The graph itself is the entire observability artifact for this feature. Without it, quality engineers have no way to see whether generation is converging or diversifying; with it, the clustering/gap/bias signals become visible and actionable. P1 because every other story in this feature depends on the graph being computed and queryable.

**Independent Test**: Seed a workspace with 50 hypotheses spanning 3 known topical neighborhoods (25 near-duplicates in topic A, 15 in topic B, 10 spread broadly in topic C). Query the proximity graph for the workspace. Verify: (a) at least three clusters are returned; (b) topic A's cluster is classified over-explored, topic C's region surfaces at least one gap, topic B is classified normal; (c) each cluster entry lists member hypothesis IDs, centroid position, and density classification.

**Acceptance Scenarios**:

1. **Given** a workspace with at least the minimum-hypothesis threshold of embedded hypotheses, **When** the proximity graph is queried, **Then** the response returns clusters with member hypothesis IDs, a density classification per cluster (under-explored / normal / over-explored), and a list of gap regions.
2. **Given** a workspace with fewer hypotheses than the minimum threshold, **When** the proximity graph is queried, **Then** the response is returned with a "pre-proximity" status and the minimum-required count surfaced in the payload rather than a misleading empty graph.
3. **Given** the proximity graph has been computed for a workspace, **When** a new hypothesis is generated, **Then** a follow-up query reflects the new hypothesis as either a new cluster member or a new single-member region within at most the configured refresh interval.
4. **Given** a proximity graph has been computed, **When** the operator queries it with a `session_id` filter, **Then** the returned graph is scoped to only that session's hypotheses (backward-compatible with existing session-level behavior).
5. **Given** two hypotheses judged semantically identical, **When** both are embedded, **Then** they fall within the same cluster and the graph reports an edge between them.

---

### User Story 2 — Hypothesis Generation Is Automatically Biased Toward Underexplored Gaps (Priority: P1)

An agent requests a new hypothesis within a workspace that has an active discovery session. Instead of generating uniformly (which tends to drift back into already-saturated regions), the generator receives guidance derived from the proximity graph: the currently identified gap regions are surfaced as hints, and already-saturated regions are surfaced as "avoid" context. Over the course of the session, the distribution of hypotheses broadens — gaps fill in, saturation stops worsening — without requiring an operator to manually curate every prompt.

**Why this priority**: The graph (US1) is observability; the generation bias is the behavioral change that makes the graph actionable in real time. Without this wiring, the graph reveals over-exploration but the system keeps doing it. P1 because the feature's stated value proposition ("bias generation toward underexplored areas") depends entirely on this wire-up.

**Independent Test**: Seed a workspace with 30 hypotheses clustered in 2 saturated regions. Invoke hypothesis generation 10 times with bias enabled. Measure: (a) the fraction of new hypotheses whose embeddings land outside the saturated clusters' radius; (b) the fraction inside. Verify the diversified fraction exceeds a configurable minimum (default 50%), versus a measurable baseline (same generations run with bias off) that shows significantly lower diversification. Verify the rationale attached to each generation call cites the gap signal it was biased toward.

**Acceptance Scenarios**:

1. **Given** a workspace with an active proximity graph containing at least one gap region, **When** a hypothesis is generated with bias enabled, **Then** the gap region's topical description is included in the generation context and the resulting hypothesis rationale records which gap was targeted.
2. **Given** a workspace where the graph identifies one cluster as over-explored, **When** a hypothesis is generated, **Then** the over-explored cluster's topical description is included as "avoid" context so the generator is nudged away.
3. **Given** bias is disabled for the workspace, **When** a hypothesis is generated, **Then** the generation prompt does not include gap/saturation guidance (parity with pre-feature behavior).
4. **Given** the proximity graph has not yet reached the minimum-hypothesis threshold, **When** generation is invoked, **Then** bias is skipped (no gap/saturation guidance surfaces) and a rationale note records "insufficient graph data" so operators can see why bias was skipped.
5. **Given** a session converges on diverse hypotheses over 20 consecutive generation calls with bias enabled, **When** the proximity graph is recomputed, **Then** the ratio of under-explored to over-explored clusters decreases measurably (configurable threshold) compared to the session's initial state.

---

### User Story 3 — Every Generated Hypothesis Is Added to the Proximity Graph Immediately (Priority: P2)

When an agent finishes generating a hypothesis, the hypothesis is embedded and placed into the proximity graph without waiting for a scheduled recomputation. A subsequent query on the same workspace reflects the new hypothesis in the cluster structure. This keeps the graph's gap signal fresh so the next generation call in a rapid-fire session sees the most recent state rather than stale clusters.

**Why this priority**: Freshness is important but not load-bearing — a scheduled batch recomputation (existing infrastructure) already computes clusters periodically. P2 because US1 and US2 deliver value even with a periodic recompute; per-hypothesis update is a latency improvement for interactive sessions.

**Independent Test**: Generate a hypothesis. Immediately (before the next scheduled recomputation) query the proximity graph. Verify the new hypothesis is present in the cluster structure (either as a member of an existing cluster or as its own region). Verify the hypothesis' embedding is persisted and discoverable. Verify per-hypothesis indexing failure does not block the hypothesis-generation call itself — the hypothesis record still persists with a note that it will be picked up by the next scheduled recomputation.

**Acceptance Scenarios**:

1. **Given** a hypothesis is generated, **When** the generation call completes, **Then** the hypothesis' embedding is computed and inserted into the proximity graph before the generation response is returned, unless the embedding step fails.
2. **Given** the embedding provider is unavailable, **When** a hypothesis is generated, **Then** the hypothesis persists with an "embedding pending" annotation and the next scheduled recomputation picks it up; generation does not fail.
3. **Given** 100 hypotheses are generated in rapid succession, **When** the proximity graph is queried immediately after the last one, **Then** all 100 hypotheses are represented (either as members or with a pending annotation if any embedding step failed).

---

### Edge Cases

- **Minimum-hypothesis threshold**: Proximity clustering is statistically meaningless below a minimum hypothesis count. The graph query is well-defined at any count, but the response distinguishes "insufficient data" from "computed" rather than returning noisy clusters.
- **Duplicate-embedding hypothesis**: Two hypotheses with byte-identical content yield identical embeddings. The graph records both as separate nodes in the same cluster (a "near-zero" edge is valid), and they are not deduplicated at the graph layer — dedup is a hypothesis-layer concern.
- **Embedding provider outage**: If the embedding model API is unreachable, affected hypotheses are annotated "embedding pending" and the graph query returns current-known state plus a flag noting how many are pending. The system does not silently drop hypotheses from the graph.
- **Graph stale beyond refresh interval**: If a workspace has not been recomputed within the configured staleness window and proximity data is requested, the response returns the stale graph with a "last computed at" annotation; a synchronous recomputation is not triggered by a read.
- **Bias references a deleted hypothesis**: If a hypothesis that was a cluster centroid is deleted between graph computation and the next generation call, the bias context that references it remains valid for the duration of the interval (stale references are acceptable — the next recomputation re-derives centroids).
- **Workspace isolation**: Proximity graphs are strictly workspace-scoped. A hypothesis in workspace A cannot influence clustering in workspace B even if they are semantically identical.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute a proximity graph for a workspace in which (a) nodes represent individual hypotheses, (b) edges represent semantic proximity between hypotheses, and (c) the graph exposes cluster groupings.
- **FR-002**: System MUST classify each cluster as `under_explored`, `normal`, or `over_explored` based on configurable density thresholds.
- **FR-003**: System MUST identify "gap regions" — areas of the idea-space that have fewer than the configured threshold of hypotheses nearby — and surface them distinctly from clusters with members.
- **FR-004**: System MUST expose a read endpoint at `GET /api/v1/discovery/{workspace_id}/proximity-graph` returning clusters, cluster classifications, edges, gap regions, and a graph-level saturation indicator.
- **FR-005**: Proximity graph queries MUST be workspace-scoped and respect existing discovery-bounded-context visibility and RBAC.
- **FR-006**: The proximity graph query MUST accept an optional `session_id` filter to restrict clustering to that session's hypotheses (backward-compatible with existing session-level behavior).
- **FR-007**: System MUST refresh the proximity graph on a configurable interval via the existing scheduled recomputation task, extended to cover workspace scope.
- **FR-008**: When a new hypothesis is generated, system MUST synchronously compute its embedding, persist the embedding, and insert a node into the proximity graph before returning the generation response, unless embedding fails.
- **FR-009**: If embedding fails at generation time (e.g., provider unavailable), system MUST persist the hypothesis with an "embedding pending" annotation and enqueue it for the next scheduled recomputation; the generation call MUST NOT fail because of an embedding error.
- **FR-010**: The proximity graph response MUST include a "pre-proximity" status when the number of embedded hypotheses in the workspace is below the minimum threshold, along with the minimum-required count.
- **FR-011**: System MUST surface the identified gap regions to the hypothesis-generation prompt as exploration hints, and the identified over-explored clusters as avoidance hints, when bias is enabled for the workspace.
- **FR-012**: System MUST record on each generated hypothesis' rationale which gap region was targeted (or that bias was skipped and why: insufficient graph data, bias disabled, graph stale).
- **FR-013**: System MUST allow bias to be enabled or disabled at the workspace level (default: enabled for new workspaces) without requiring schema changes to the hypothesis record.
- **FR-014**: System MUST expose the minimum-hypothesis threshold, bias enable/disable toggle, and refresh interval as configuration (not hardcoded).
- **FR-015**: Proximity graph queries MUST return within a reasonable interactive budget for workspaces up to the documented scale ceiling (e.g., 10,000 hypotheses); beyond the ceiling the response SHOULD return a paginated or compacted representation and MUST clearly indicate truncation when it occurs.
- **FR-016**: System MUST emit an observable signal when a cluster transitions from `normal` to `over_explored`, or when a previously-existing gap is filled, so operators can be notified about saturation and exploration progress.
- **FR-017**: System MUST preserve backward compatibility with existing session-level proximity computation: session-scoped queries and scheduled session-level tasks continue to work without behavior change, and existing proximity data remains accessible.
- **FR-018**: Deletion or archival of a hypothesis MUST cause the next recomputation to remove its node and edges from the graph; historical graph snapshots do not need to be retroactively mutated.

### Key Entities *(include if feature involves data)*

- **Hypothesis**: Existing entity produced by the discovery generator. For this feature, each hypothesis gets an associated embedding vector and participation in the proximity graph. No schema change at the hypothesis layer.
- **HypothesisEmbedding**: A vector representation of a hypothesis' content, computed at or near generation time. Associated with a single hypothesis, an embedding-provider/model identifier, and a timestamp; stored in the vector index.
- **ProximityCluster**: A grouping of hypotheses whose pairwise proximity in embedding space exceeds a threshold. Has a centroid, a member list, a density classification (under-explored / normal / over-explored), and a topical summary used for bias hints.
- **GapRegion**: An area of embedding space where too few hypotheses exist to form a cluster but where additional hypotheses would benefit the discovery process. Has a descriptive label (derived from nearby content) used as the generation hint.
- **ProximityGraph**: The composite view over a workspace or session at a point in time: set of clusters, edges between close hypotheses, and gap regions. Has a computed-at timestamp and a saturation indicator.
- **BiasSignal**: The guidance surface emitted to the hypothesis generator, derived from the current ProximityGraph's gap regions and over-explored clusters. Not persisted — derived on demand at generation time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Quality engineers can load a workspace's proximity graph in under 2 seconds for workspaces with up to 1,000 hypotheses.
- **SC-002**: After 20 consecutive bias-enabled generations in a saturated workspace, the fraction of new hypotheses landing outside already-saturated clusters increases by at least 50% compared to a baseline of the same generations run with bias disabled.
- **SC-003**: For a workspace seeded with known topical neighborhoods, the graph's cluster structure recovers those neighborhoods with at least 80% agreement against a human-labeled ground-truth clustering on a representative validation set.
- **SC-004**: At least 95% of newly generated hypotheses appear in the proximity graph within 5 seconds of the generation response being returned, subject to embedding-provider latency.
- **SC-005**: Saturation and gap-filled events are emitted observably within one recomputation interval of the underlying state change, with zero missed transitions in a deterministic replay test.
- **SC-006**: When the embedding provider is unreachable for 10 consecutive minutes, no hypothesis generation calls fail because of embedding errors; 100% of affected hypotheses are recovered into the graph via the scheduled recomputation on provider restoration.
- **SC-007**: Existing session-level proximity queries and scheduled tasks continue to produce byte-identical results after this feature lands (backward compatibility preserved).

## Assumptions

- The existing proximity infrastructure in `discovery/proximity/` (`HypothesisEmbedder`, `ProximityClustering`, `proximity_clustering_task`, `discovery_hypotheses` Qdrant collection) is preserved and extended — not replaced.
- Embeddings use the existing embedding provider configured for the discovery bounded context; no new provider choice is introduced.
- Bias is applied as **prompt-guidance**: gap-region topical descriptions are included as exploration hints and over-explored cluster descriptions as avoidance hints in the generation prompt. Other bias modalities (rejection sampling, post-generation filtering) are out of scope for this feature.
- "Workspace-level" proximity graph extends existing session-level computation without losing session-level granularity — both scopes coexist.
- Cluster and gap topical summaries are derived from the hypothesis content already stored, not from a separate summarization service.
- The minimum-hypothesis threshold for proximity clustering reuses the existing configurable default rather than introducing a new constant.
- Agents generating hypotheses are cooperating clients: the bias signal is advisory, not enforced. If an agent ignores the bias, the graph still records the new hypothesis and saturation may continue to worsen — this is a diagnostic rather than a system failure.
- Historical proximity snapshots are not persisted — the graph is always the current view. Historical analysis is a separate feature not covered here.
- No new external dependencies are introduced; all required capabilities (Qdrant vector search, optional Neo4j edge storage, embedding provider, clustering library) already exist in the control plane.
- Neo4j edge storage is used only if the existing session-level clustering task already uses it; otherwise this feature follows the current implementation pattern and does not introduce Neo4j as a new dependency.
