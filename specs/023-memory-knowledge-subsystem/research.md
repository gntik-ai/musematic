# Research: Memory and Knowledge Subsystem

**Feature**: 023-memory-knowledge-subsystem  
**Date**: 2026-04-11  
**Status**: Complete — all decisions resolved

---

## Decision 1: Storage Architecture — Single vs Multiple Qdrant Collections

**Decision**: Use a single Qdrant collection (`platform_memory`) with scope and workspace_id as payload filters, not separate per-scope collections.

**Rationale**: A single collection simplifies operational overhead (one collection to manage, backup, and tune). Scope and workspace isolation is enforced via Qdrant payload filters on every query — this is the idiomatic Qdrant pattern for multi-tenant deployments. Separate collections would require dynamic collection creation/deletion as agents and workspaces are added, creating operational complexity without measurable performance benefit at the projected scale (1M entries per collection fits well within a single shard).

**Alternatives considered**:
- Per-scope collections (`agent_memory`, `workspace_memory`, `orchestrator_memory`): simpler query filters but requires dynamic collection management, complicates backup/restore, and means small collections per-agent that waste Qdrant segment overhead.
- Per-workspace collections: operationally expensive at scale; Qdrant is not designed for thousands of small collections.

---

## Decision 2: PostgreSQL Tables vs Qdrant as Source of Truth

**Decision**: PostgreSQL is the source of truth for memory entry metadata (including content for keyword search), and Qdrant holds only the vector payload (pointing back to the PostgreSQL `memory_entry_id`). Deletions in PostgreSQL cascade to Qdrant cleanup via a background job (or synchronous delete call).

**Rationale**: PostgreSQL provides ACID guarantees for writes, full-text search via `tsvector`, retention enforcement queries, and relational constraints (FK to workspace, agent FQN). Qdrant holds the vectors. Writing to both on each write is the correct pattern — PostgreSQL first (get the UUID), then Qdrant upsert with that UUID as the point ID. Rollback: if Qdrant write fails, the PostgreSQL record is deleted (compensating). If PostgreSQL write fails, nothing is written to Qdrant.

**Alternatives considered**:
- Qdrant as source of truth with payload containing all metadata: loses ACID, makes FTS awkward, complicates retention enforcement and cross-entity queries.
- Dual-write with Kafka-mediated consistency: overkill for same-process writes; adds latency and complexity without benefit.

---

## Decision 3: PostgreSQL Full-Text Search for Keyword Retrieval

**Decision**: Use PostgreSQL `tsvector` + `tsquery` on the `memory_entries.content_tsv` column (generated column) for keyword search. This is an internal, bounded-context-private FTS — not user-facing. Constitution §III prohibits PostgreSQL FTS for user-facing search (use OpenSearch), but memory retrieval is an internal call from context engineering, not directly from users.

**Rationale**: The memory bounded context already owns the `memory_entries` table. Adding a `content_tsv` generated column and a GIN index is zero-overhead for keyword retrieval without introducing a new dependency. OpenSearch would be overkill for internal memory keyword matching — OpenSearch is reserved for user-facing marketplace search.

**Alternatives considered**:
- OpenSearch for keyword memory: violates the "user-facing search only" principle and adds cross-context storage coupling.
- In-process trigram matching: impractical at 1M+ entries.

---

## Decision 4: Neo4j Schema — Workspace-Scoped Nodes and Edges

**Decision**: Every node carries a `workspace_id` property and is created with a `workspace_id` index. Every Cypher query includes a `WHERE n.workspace_id = $workspace_id` clause. A composite index on `(workspace_id, node_type)` enables fast workspace-scoped lookups.

**Rationale**: Neo4j doesn't have schema-level multi-tenancy. The idiomatic approach is to store `workspace_id` as a property on every node and edge, and enforce it in every query. The `AsyncGraphDatabase` driver runs all queries in async sessions — workspace_id is injected as a query parameter, preventing injection.

**Alternatives considered**:
- Separate Neo4j databases per workspace: Neo4j enterprise supports multiple databases, but this is not available in community edition and creates operational complexity.
- Labels as workspace discriminators: more cumbersome than a property filter and less indexable.

---

## Decision 5: Contradiction Detection Algorithm

**Decision**: Contradiction detection uses cosine similarity on incoming vs. existing embeddings for the same entity/scope, combined with a content-hash check. Two memories are flagged as potential contradictions if: (1) cosine similarity ≥ 0.90 (semantically very similar topic) AND (2) the content differs by more than a 0.15 normalized edit distance threshold. The 0.90/0.15 thresholds are configurable in PlatformSettings.

**Rationale**: Pure embedding similarity catches same-topic memories regardless of phrasing. The edit distance guard prevents flagging near-paraphrase updates as contradictions (a memory and its correction should not create a conflict if they're nearly identical). This heuristic achieves the required 85% accuracy target (SC-004) without requiring an LLM judge call for every write (which would blow the 500ms budget, SC-001).

**Alternatives considered**:
- LLM-as-judge for contradiction: accurate but too slow (adds 1–5s) and expensive for every write.
- Keyword overlap only: misses paraphrased contradictions entirely.
- Pure embedding similarity with no edit distance guard: too many false positives on paraphrase updates.

---

## Decision 6: Redis Rate Limiting — Sliding Window per Agent FQN

**Decision**: Use Redis `INCR` + `EXPIRE` with a two-key pattern per agent: `memory:ratelimit:{agent_fqn}:min` (60-second TTL) and `memory:ratelimit:{agent_fqn}:hour` (3600-second TTL). Thresholds: 60 writes/minute, 500 writes/hour (configurable). Uses the same `rate_limit_check.lua` script pattern established in feature 014.

**Rationale**: Consistent with the platform's existing rate limiting pattern (sliding window Lua script in Redis). Two keys (per-minute, per-hour) catch both burst and sustained overuse. Using `INCR`+`EXPIRE` with atomic Lua script ensures no race conditions.

**Alternatives considered**:
- Token bucket: more complex Lua, not consistent with existing pattern.
- PostgreSQL-based rate tracking: too slow, wrong store for ephemeral counters.
- In-memory per-process: doesn't work across multiple API instances.

---

## Decision 7: EmbeddingJob Queue — PostgreSQL-Backed Async Job

**Decision**: `EmbeddingJob` records are stored in PostgreSQL with status (`pending`, `processing`, `completed`, `failed`). A background APScheduler task (every 30 seconds, `worker_main.py` profile) scans for `pending` jobs, processes up to 50 at a time, and updates status. No Kafka required for the queue — the job table is small and APScheduler is already the established pattern.

**Rationale**: The embedding queue is a retry mechanism for transient embedding model failures. PostgreSQL is sufficient for a small bounded queue (in practice, `pending` jobs drain within seconds once the model is available). Using Kafka would overcomplicate a simple backlog drain.

**Alternatives considered**:
- Redis queue (LPUSH/RPOP): loses durability on Redis restart; embedding job loss would cause vector-less entries indefinitely.
- Kafka-based job queue: correct for durable streaming but overkill for a local retry queue.
- APScheduler + PostgreSQL (chosen): durable, simple, consistent with existing worker patterns.

---

## Decision 8: Pattern Promotion State Machine

**Decision**: `PatternAsset.status` follows: `pending` → `approved` | `rejected`. No intermediate states. Approved patterns are immutable — once approved, a pattern cannot be reverted to pending. A rejected pattern can be re-nominated from the same trajectory (creating a new `PatternAsset` with `pending` status).

**Rationale**: Simple two-outcome state machine reduces complexity and eliminates state transition bugs. Re-nomination creates a new record (preserving the rejection record) rather than mutating the existing one — consistent with the platform's audit-first philosophy.

**Alternatives considered**:
- Draft → review → approved/rejected: unnecessary intermediate; the nomination itself is the review trigger.
- Mutating rejected records to pending: violates append-only audit posture.

---

## Decision 9: Consolidation Worker Pipeline

**Decision**: Consolidation runs as an APScheduler job (every 15 minutes, configurable) in `worker_main.py`. Pipeline: (1) retrieve agent-scoped memories per workspace with high embedding similarity clusters (cosine ≥ 0.85, ≥ 3 members), (2) distill via text concatenation + LLM summarization call (optional, configurable `MEMORY_CONSOLIDATION_LLM_ENABLED`), (3) write consolidated entry to workspace scope via the write gate (normal gate enforcement, including contradiction check), (4) link originals to the consolidated entry via `provenance_consolidated_by` field, (5) emit `consolidation.completed` Kafka event.

**Rationale**: The clustering threshold (0.85) is lower than contradiction detection (0.90) — we want to catch same-topic memories before they reach contradiction threshold. LLM summarization is opt-in: when disabled, consolidation uses the highest-scoring memory as the distilled entry (no LLM required). The write gate is called normally so consolidated entries go through the same authorization and contradiction checks as any other write.

**Alternatives considered**:
- Run on every workspace after every write: too expensive; batching every 15 minutes is the right tradeoff.
- Skip the write gate for consolidated entries: violates the non-bypassable gate invariant.
- Kafka-triggered consolidation: would require producing an event and consuming it in the same service — adds unnecessary roundtrip.

---

## Decision 10: Kafka Topic and Event Types

**Decision**: Single topic `memory.events` with 4 event types:
1. `memory.written` — emitted after successful write gate completion and storage
2. `memory.conflict.detected` — emitted when an evidence conflict is created
3. `memory.pattern.promoted` — emitted when a pattern asset transitions to `approved`
4. `memory.consolidation.completed` — emitted after consolidation run (includes count of consolidated entries)

All events use the canonical `EventEnvelope` from feature 013 with `CorrelationContext` carrying `workspace_id` + `execution_id`.

**Rationale**: One topic per bounded context is the established platform pattern. Four event types cover all observable state changes. Consolidation completion is a single event per run (not per entry) to avoid flooding the topic.

**Alternatives considered**:
- Separate topics per event type: unnecessary; consumers can filter by `event_type` within the envelope.
- No Kafka events for memory writes: loses observability and prevents downstream consumers (e.g., analytics) from tracking memory usage.

---

## Decision 11: Hybrid Retrieval — RRF with k=60

**Decision**: Reciprocal rank fusion with k=60 (standard constant). Each source (vector, keyword, graph) returns up to 20 candidates. RRF score per document: `sum(1 / (k + rank_i))` across sources where the document appears. Final list sorted by RRF score descending, top 10 returned. Recency weight and authority weight are applied as multiplicative modifiers after RRF: `final_score = rrf_score * recency_factor * authority_factor`.

**Rationale**: k=60 is the empirically validated constant from the original RRF paper and widely used in production hybrid search. Multiplicative post-RRF weighting preserves ranking relative order while biasing toward fresh, authoritative sources. Returning 20 candidates per source before fusion ensures coverage.

**Alternatives considered**:
- Weighted score fusion (linear combination): requires normalizing scores from different score spaces (cosine similarity, BM25, graph traversal depth) — not straightforward.
- k=0 or k=1: makes RRF extremely sensitive to rank position; k=60 is the stable choice.
- Applying recency/authority before RRF: distorts the individual source rankings before fusion.

---

## Decision 12: Alembic Migration Number

**Decision**: Migration `008_memory_knowledge.py` — 7 tables:
1. `memory_entries` (content, content_tsv GIN, scope, workspace_id, agent_fqn, namespace, source_authority, content_hash, retention_policy, embedding_status, provenance metadata)
2. `evidence_conflicts` (memory_entry_id_a, memory_entry_id_b, description, status, reviewer_id)
3. `embedding_jobs` (memory_entry_id, status, retry_count, error_message)
4. `trajectory_records` (execution_id, agent_fqn, workspace_id, actions JSONB, tool_invocations JSONB, reasoning_snapshots JSONB, verdicts JSONB)
5. `pattern_assets` (trajectory_record_id, content, status, reviewer_id, rejection_reason, tags JSONB, description)
6. `knowledge_nodes` — PostgreSQL mirror for workspace-scoped node metadata only (Neo4j holds the graph structure); stores `(external_id, workspace_id, node_type, attributes JSONB, created_by_fqn)`
7. `knowledge_edges` — PostgreSQL mirror for edge metadata; stores `(external_id, source_node_id, target_node_id, relationship_type, metadata JSONB, workspace_id)`

**Rationale**: Mirroring KnowledgeNode and KnowledgeEdge in PostgreSQL (in addition to Neo4j) enables ACID-consistent creation (PostgreSQL FK constraint to workspace), workspace listing queries without round-tripping to Neo4j, and Alembic-managed schema. Neo4j holds the graph traversal structure; PostgreSQL holds the metadata and serves as the authoritative creation record.

**Alternatives considered**:
- Neo4j only for nodes/edges: no FK constraints, no workspace-scoped list queries without Neo4j, no Alembic-managed schema.
- Separate bounded context tables per node type: premature specialization; JSONB attributes handle arbitrary node types cleanly.
