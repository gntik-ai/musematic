# Implementation Plan: Memory and Knowledge Subsystem

**Branch**: `023-memory-knowledge-subsystem` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/023-memory-knowledge-subsystem/spec.md`

## Summary

Build the `memory/` bounded context within `apps/control-plane/src/platform/`. This covers a memory write gate (authorization via registry/workspaces service, Redis rate limiting, contradiction detection via embedding similarity + edit distance, retention policy validation, optional differential privacy), scoped vector storage in a single Qdrant collection (`platform_memory`) with workspace/agent/scope payload filters, hybrid retrieval coordinator (vector via Qdrant + keyword via PostgreSQL FTS + graph via Neo4j with reciprocal rank fusion k=60), knowledge graph operations (Neo4j nodes + edges with workspace isolation, multi-hop Cypher traversal), trajectory capture (immutable records), pattern promotion workflow (pending → approved/rejected), background consolidation workers (APScheduler every 15 min), embedding job queue (APScheduler every 30 sec), and session memory cleaner (APScheduler every 60 min). Storage: PostgreSQL (7 tables) + Qdrant (`platform_memory` collection) + Neo4j (MemoryNode/MEMORY_REL). Primary deliverable includes a `retrieve_for_context()` internal interface consumed by the context engineering bounded context.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), qdrant-client 1.12+ async gRPC (vector storage and search), neo4j-python-driver 5.x async (`AsyncGraphDatabase`, knowledge graph), redis-py 5.x async (rate limiting sliding window), httpx 0.27+ (embedding API calls to model provider), APScheduler 3.x (embedding worker + consolidation worker + session cleaner)  
**Storage**: PostgreSQL (7 tables: memory_entries, evidence_conflicts, embedding_jobs, trajectory_records, pattern_assets, knowledge_nodes, knowledge_edges) + Qdrant (`platform_memory` collection, 1536-dim Cosine) + Neo4j (MemoryNode label, MEMORY_REL type)  
**Testing**: pytest 8.x + pytest-asyncio  
**Target Platform**: Linux server, Kubernetes `platform-control` namespace (`api` profile for endpoints, `worker` profile for EmbeddingWorker + ConsolidationWorker + SessionMemoryCleaner)  
**Performance Goals**: Write gate ≤ 500ms (SC-001); vector retrieval ≤ 200ms for 1M entries (SC-002); hybrid retrieval ≤ 1s (SC-003); graph multi-hop ≤ 500ms (SC-005); scope isolation 100% (SC-006)  
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; write gate non-bypassable; trajectory records immutable (no update/delete); consolidation must not block real-time reads/writes  
**Scale/Scope**: 6 user stories, 20 FRs, 10 SCs, 17 REST endpoints + 1 internal interface, 7 PostgreSQL tables, 1 Qdrant collection, Neo4j graph, 4 Kafka event types, 3 APScheduler workers

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated |
| Pydantic v2 for all schemas | PASS | §2.1 mandated |
| SQLAlchemy 2.x async only | PASS | §2.1 mandated — 7 PostgreSQL tables |
| All code async | PASS | Coding conventions: "All code is async" |
| Bounded context structure | PASS | models, schemas, service, repository, router, events, exceptions, dependencies, write_gate, retrieval_coordinator, consolidation_worker, embedding_worker, memory_setup |
| No cross-boundary DB access | PASS | §IV — all cross-context data via in-process service interfaces: workspaces_service, registry_service |
| Canonical EventEnvelope | PASS | All events on `memory.events` use EventEnvelope from feature 013 |
| CorrelationContext everywhere | PASS | Events carry workspace_id + execution_id in CorrelationContext |
| Repository pattern | PASS | `MemoryRepository` (SQLAlchemy) in repository.py |
| Kafka for async events (not DB polling) | PASS | §III — events emitted on write, conflict, pattern promotion, consolidation |
| Alembic for PostgreSQL schema changes | PASS | migration 008_memory_knowledge for all 7 tables |
| ClickHouse for OLAP/time-series | N/A | Memory subsystem has no OLAP analytics requirements |
| No PostgreSQL for rollups | N/A | No rollups in this bounded context |
| Qdrant for vector search | PASS | §III — single `platform_memory` collection with scope/workspace payload filters |
| Redis for caching | PASS | §III — Redis sliding-window rate limiting (not in-memory per-process); `memory:ratelimit:{agent_fqn}:min` and `:hour` keys |
| OpenSearch | N/A | Memory keyword search is internal (PostgreSQL FTS on memory_entries.content_tsv) — constitution §III only prohibits PostgreSQL FTS for user-facing search |
| No PostgreSQL FTS for user-facing search | PASS | PostgreSQL FTS is only for internal memory retrieval within the bounded context's own tables |
| Neo4j for graph traversal | PASS | §III — knowledge graph operations via AsyncGraphDatabase; no recursive CTEs in PostgreSQL |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | PASS | §XI — optional LLM consolidation passes only memory text, not secrets |
| Zero-trust visibility | PASS | §IX — write gate checks namespace ownership; scope isolation enforced on 100% of reads (SC-006) |
| Goal ID as first-class correlation | PASS | §X — `goal_id` is a parameter in `retrieve_for_context()` internal interface |
| Modular monolith (no HTTP between contexts) | PASS | §I — `retrieve_for_context()` is in-process; context engineering calls it directly |
| APScheduler for background tasks | PASS | §2.1 — EmbeddingWorker, ConsolidationWorker, SessionMemoryCleaner use APScheduler in worker_main.py |

**All 25 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/023-memory-knowledge-subsystem/
├── plan.md                          # This file
├── spec.md                          # Feature specification
├── research.md                      # Phase 0 decisions (12 decisions)
├── data-model.md                    # Phase 1 — SQLAlchemy models, Qdrant/Neo4j schemas, Pydantic schemas, service signatures
├── quickstart.md                    # Phase 1 — run/test guide
├── contracts/
│   └── memory-api.md                # REST API contracts (17 endpoints + 1 internal interface)
└── tasks.md                         # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── memory/
│       ├── __init__.py
│       ├── models.py                          # SQLAlchemy: 7 models + enums
│       ├── schemas.py                         # Pydantic: all request/response + internal schemas
│       ├── service.py                         # MemoryService — write gate orchestration + CRUD + retrieval + graph
│       ├── repository.py                      # MemoryRepository — SQLAlchemy CRUD for all 7 tables
│       ├── router.py                          # FastAPI router: /api/v1/memory/* (17 endpoints)
│       ├── events.py                          # Event payload types + publish_* helpers
│       ├── exceptions.py                      # MemoryError, WriteGateError, RateLimitError, ConflictError, etc.
│       ├── dependencies.py                    # get_memory_service DI factory
│       ├── write_gate.py                      # MemoryWriteGate — authorization, rate limit, contradiction, retention, privacy
│       ├── retrieval_coordinator.py           # RetrievalCoordinator — vector + keyword + graph + RRF
│       ├── consolidation_worker.py            # ConsolidationWorker — APScheduler task, cluster + distill + promote
│       ├── embedding_worker.py                # EmbeddingWorker — APScheduler task, pending EmbeddingJob drain
│       └── memory_setup.py                    # Idempotent Qdrant collection + Neo4j index creation
├── migrations/
│   └── versions/
│       └── 008_memory_knowledge.py            # Alembic: 7 tables + indexes + GIN index for content_tsv
└── tests/
    ├── unit/
    │   ├── test_mem_write_gate.py             # Write gate validation: auth, rate limit, contradiction, retention, privacy
    │   ├── test_mem_retrieval_coordinator.py  # RRF fusion, recency/authority weighting, partial source handling
    │   ├── test_mem_schemas.py                # Pydantic validation tests
    │   └── test_mem_scope_isolation.py        # Scope filter logic (per_agent, per_workspace, shared_orchestrator)
    └── integration/
        ├── test_mem_write_retrieve.py         # Full write → embed → retrieve pipeline
        ├── test_mem_contradiction.py          # Contradiction detection + EvidenceConflict creation
        ├── test_mem_graph_operations.py       # Node + edge creation, multi-hop traversal, provenance
        ├── test_mem_trajectory_patterns.py    # Trajectory capture + pattern nomination + approval workflow
        ├── test_mem_consolidation.py          # ConsolidationWorker cluster + distill + promote
        └── test_mem_cross_scope.py            # Cross-scope transfer authorization + provenance
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/memory/` package with all module stubs
- `memory_setup.py`: idempotent `setup_memory_collections()` — create `platform_memory` Qdrant collection (1536-dim Cosine) + 3 payload indexes (workspace_id, agent_fqn, scope); create Neo4j `node_workspace` index and `node_unique` constraint
- Alembic migration `008_memory_knowledge.py`: all 7 tables + GIN index on `content_tsv` generated column + composite indexes

### Phase 2 — US1+US3: Write Gate and Scoped Memory Storage (P1)
- `models.py`: all 7 SQLAlchemy models + enums (`MemoryScope`, `RetentionPolicy`, `EmbeddingStatus`, `ConflictStatus`, `EmbeddingJobStatus`, `PatternStatus`)
- `schemas.py`: `MemoryWriteRequest`, `RetrievalQuery`, `CrossScopeTransferRequest`, `WriteGateResult`, `MemoryEntryResponse`, `RetrievalResult`, `RetrievalResponse`, `EvidenceConflictResponse`, `ConflictResolution`
- `exceptions.py`: `MemoryError`, `WriteGateAuthError`, `WriteGateRateLimitError`, `WriteGateRetentionError`, `ConflictDetectedError`, `ScopeIsolationError`
- `repository.py`: `MemoryRepository` — all SQLAlchemy CRUD for 7 tables + `find_similar_entries_for_contradiction()` + `get_pending_embedding_jobs()` + `get_consolidation_candidates()`
- `write_gate.py`: `MemoryWriteGate` — `validate_and_write()` pipeline: authorization check (in-process registry_service namespace ownership + workspaces_service scope membership) → Redis rate limit check (Lua `rate_limit_check.lua`, two keys) → namespace restriction check → contradiction check (Qdrant similarity search + normalized edit distance) → retention validation → optional Laplace noise injection → PostgreSQL insert → Qdrant upsert (compensating delete on failure) → emit `memory.written` event
- `service.py`: `MemoryService` — `write_memory()`, `get_memory_entry()`, `list_memory_entries()`, `delete_memory_entry()`, `transfer_memory_scope()`
- `events.py`: `MemoryWrittenPayload` + `publish_memory_written()`; `ConflictDetectedPayload` + `publish_conflict_detected()`

### Phase 3 — US2: Hybrid Retrieval with Rank Fusion (P1)
- `retrieval_coordinator.py`: `RetrievalCoordinator` — `_vector_search()` (Qdrant search with workspace/scope/agent payload filters), `_keyword_search()` (PostgreSQL `to_tsquery()` on `content_tsv` with scope filters), `_graph_search()` (Neo4j entity name matching via Cypher), `_reciprocal_rank_fusion()` (k=60, sums `1/(k+rank)` across sources), `_apply_recency_weight()` (exponential decay, configurable half-life), `_apply_authority_weight()` (multiplicative `source_authority` factor), `_flag_contradictions()` (cross-reference open `EvidenceConflict` records)
- `service.py`: wire `retrieve()` and `retrieve_for_context()` (internal interface for context engineering)
- `router.py`: `POST /entries`, `POST /retrieve`, `GET /entries/{id}`, `GET /entries`, `DELETE /entries/{id}`, `POST /entries/{id}/transfer`

### Phase 4 — US3: Conflict Management Endpoints (P1)
- `service.py`: `list_conflicts()`, `resolve_conflict()`
- `router.py`: `GET /conflicts`, `POST /conflicts/{id}/resolve`
- `events.py`: wire `publish_conflict_detected()` from write gate

### Phase 5 — US4: Knowledge Graph Operations (P2)
- `schemas.py`: `KnowledgeNodeCreate/Response`, `KnowledgeEdgeCreate/Response`, `GraphTraversalQuery`, `GraphTraversalResponse`
- `service.py`: `create_knowledge_node()` (PostgreSQL insert + Neo4j `CREATE` — atomic with compensating Neo4j delete on PG failure), `create_knowledge_edge()`, `traverse_graph()` (Cypher `MATCH path = (s)-[:MEMORY_REL*1..max_hops]->(e)` with workspace filter), `get_provenance_chain()`
- `repository.py`: `KnowledgeRepository` — PostgreSQL CRUD for nodes + edges
- `router.py`: `POST /graph/nodes`, `POST /graph/edges`, `POST /graph/traverse`, `GET /graph/nodes/{id}/provenance`

### Phase 6 — US5: Trajectory Capture and Pattern Promotion (P2)
- `schemas.py`: `TrajectoryRecordCreate/Response`, `PatternNomination`, `PatternReview`, `PatternAssetResponse`
- `service.py`: `record_trajectory()` (immutable insert — no update/delete), `get_trajectory()`, `nominate_pattern()`, `review_pattern()` (state transition: pending → approved/rejected; on approval, creates workspace-scoped `MemoryEntry` via write gate and sets `pattern_assets.memory_entry_id`), `list_patterns()`
- `events.py`: `PatternPromotedPayload` + `publish_pattern_promoted()`
- `router.py`: `POST /trajectories`, `GET /trajectories/{id}`, `POST /patterns`, `POST /patterns/{id}/review`, `GET /patterns`

### Phase 7 — US6: Consolidation Workers and Cross-Scope Transfer (P3)
- `consolidation_worker.py`: `ConsolidationWorker` — `run()` (APScheduler entry), per-workspace cluster detection (Qdrant batch search for cosine ≥ 0.85 clusters with ≥ 3 members), distillation (LLM call if enabled, else top-scoring member), promotion via `write_gate.validate_and_write()` to workspace scope, link originals via `provenance_consolidated_by`, emit `consolidation.completed` event
- `embedding_worker.py`: `EmbeddingWorker` — `run()` (APScheduler entry, every 30s), scan `embedding_jobs` for `pending` records (limit 50), call embedding API via httpx, upsert to Qdrant, update `memory_entries.embedding_status` + `qdrant_point_id`, mark job `completed`
- Session memory cleaner (inline in `consolidation_worker.py` or separate `SessionMemoryCleaner`): scan `memory_entries` for `session_only` with `ttl_expires_at < now()`, soft-delete entries, remove Qdrant points
- `events.py`: `ConsolidationCompletedPayload` + `publish_consolidation_completed()`

### Phase 8 — Polish & Cross-Cutting Concerns
- `dependencies.py`: `get_memory_service()` DI factory
- Mount memory router in `src/platform/api/__init__.py`
- Register `EmbeddingWorker`, `ConsolidationWorker`, `SessionMemoryCleaner` in `apps/control-plane/entrypoints/worker_main.py` via APScheduler
- Run `memory_setup.setup_memory_collections()` in `api_main.py` + `worker_main.py` lifespan (idempotent)
- Full test coverage audit (≥ 95%)
- ruff + mypy --strict clean run

## Key Decisions (from research.md)

1. **Single Qdrant collection**: `platform_memory` with scope/workspace/agent as payload filters — simpler ops than per-scope collections
2. **PostgreSQL as source of truth**: metadata + FTS in PostgreSQL; Qdrant holds vectors pointing back to `memory_entry_id`; compensating delete on Qdrant write failure
3. **PostgreSQL FTS for keyword retrieval**: internal bounded-context keyword search via `tsvector` GIN index — not user-facing search (constitution §III only prohibits PostgreSQL FTS for user-facing search)
4. **Neo4j workspace isolation**: `workspace_id` property on every node/edge; enforced in every Cypher query parameter
5. **Contradiction detection**: cosine similarity ≥ 0.90 AND normalized edit distance > 0.15 — both memories stored, `EvidenceConflict` created, caller notified
6. **Redis rate limiting**: `rate_limit_check.lua` Lua script, two keys per agent (`mem:ratelimit:{fqn}:min` / `:hour`), consistent with feature 014 pattern
7. **EmbeddingJob queue**: PostgreSQL-backed APScheduler drain — durable, no Kafka needed for retry queue
8. **Pattern promotion**: two-state outcome (pending → approved/rejected); re-nomination creates new record; approved patterns become workspace-scoped `MemoryEntry`
9. **Consolidation pipeline**: APScheduler every 15 min; Qdrant batch clustering (cosine ≥ 0.85, ≥ 3 members); optional LLM distillation; normal write gate enforcement on consolidated entries
10. **RRF fusion**: k=60, up to 20 candidates per source, multiplicative recency+authority post-fusion modifiers
11. **Internal interface**: `retrieve_for_context()` is pure in-process async call — no HTTP within monolith (§I)
12. **PostgreSQL mirrors for Neo4j nodes/edges**: ACID-consistent creation with FK to workspace; Neo4j holds graph traversal structure; PostgreSQL holds metadata and serves as creation record
