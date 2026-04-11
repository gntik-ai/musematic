# Tasks: Memory and Knowledge Subsystem

**Input**: Design documents from `specs/023-memory-knowledge-subsystem/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/memory-api.md ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the memory bounded context package skeleton and Alembic migration

- [X] T001 Create `apps/control-plane/src/platform/memory/` package with stub `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `write_gate.py`, `retrieval_coordinator.py`, `consolidation_worker.py`, `embedding_worker.py`, `memory_setup.py`
- [X] T002 Create Alembic migration `apps/control-plane/migrations/versions/008_memory_knowledge.py` with all 7 tables: `memory_entries` (with `content_tsv` tsvector generated column + GIN index), `evidence_conflicts`, `embedding_jobs`, `trajectory_records`, `pattern_assets`, `knowledge_nodes`, `knowledge_edges` — all indexes and constraints per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, schemas, exceptions, repository, events infrastructure, and startup setup — must complete before any user story work

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Implement all 7 SQLAlchemy models and enums in `apps/control-plane/src/platform/memory/models.py`: enums `MemoryScope`, `RetentionPolicy`, `EmbeddingStatus`, `ConflictStatus`, `EmbeddingJobStatus`, `PatternStatus`; models `MemoryEntry` (UUIDMixin, TimestampMixin, SoftDeleteMixin), `EvidenceConflict`, `EmbeddingJob`, `TrajectoryRecord`, `PatternAsset`, `KnowledgeNode`, `KnowledgeEdge` — all fields, indexes, and constraints per data-model.md
- [X] T004 [P] Implement all Pydantic request schemas in `apps/control-plane/src/platform/memory/schemas.py`: `MemoryWriteRequest`, `RetrievalQuery`, `CrossScopeTransferRequest`, `KnowledgeNodeCreate`, `KnowledgeEdgeCreate`, `GraphTraversalQuery`, `TrajectoryRecordCreate`, `PatternNomination`, `PatternReview`, `ConflictResolution` — all field validations per data-model.md
- [X] T005 [P] Implement all Pydantic response schemas in `apps/control-plane/src/platform/memory/schemas.py`: `MemoryEntryResponse`, `WriteGateResult`, `RetrievalResult`, `RetrievalResponse`, `EvidenceConflictResponse`, `TrajectoryRecordResponse`, `PatternAssetResponse`, `KnowledgeNodeResponse`, `KnowledgeEdgeResponse`, `GraphTraversalResponse`
- [X] T006 [P] Implement `MemoryError` exception hierarchy in `apps/control-plane/src/platform/memory/exceptions.py`: `MemoryError`, `WriteGateAuthError`, `WriteGateRateLimitError` (with `retry_after_seconds` field), `WriteGateRetentionError`, `ConflictDetectedError` (with `conflict_id` field), `ScopeIsolationError`, `MemoryEntryNotFoundError`, `TrajectoryNotFoundError`, `PatternNotFoundError`, `KnowledgeNodeNotFoundError`, `GraphUnavailableError`
- [X] T007 Implement `MemoryRepository` in `apps/control-plane/src/platform/memory/repository.py`: all SQLAlchemy CRUD methods for all 7 models — `create_memory_entry()`, `get_memory_entry()`, `list_memory_entries()`, `soft_delete_memory_entry()`, `update_memory_entry_embedding()`, `find_similar_by_scope()` (FTS query using `content_tsv`), `create_evidence_conflict()`, `get_conflict()`, `list_conflicts()`, `update_conflict_status()`, `create_embedding_job()`, `get_pending_embedding_jobs()`, `update_embedding_job_status()`, `create_trajectory_record()`, `get_trajectory_record()`, `create_pattern_asset()`, `get_pattern_asset()`, `list_pattern_assets()`, `update_pattern_status()`, `create_knowledge_node()`, `get_knowledge_node()`, `list_knowledge_nodes()`, `create_knowledge_edge()`, `get_knowledge_edge()`, `get_session_only_expired()`, `get_consolidation_candidates()` (agent-scoped entries per workspace for clustering)
- [X] T008 [P] Implement Kafka event payload types and publish helpers in `apps/control-plane/src/platform/memory/events.py`: `MemoryWrittenPayload`, `ConflictDetectedPayload`, `PatternPromotedPayload`, `ConsolidationCompletedPayload`; publish helpers `publish_memory_written()`, `publish_conflict_detected()`, `publish_pattern_promoted()`, `publish_consolidation_completed()` — all using canonical `EventEnvelope` on topic `memory.events`
- [X] T009 [P] Implement idempotent startup in `apps/control-plane/src/platform/memory/memory_setup.py`: `setup_memory_collections()` — create `platform_memory` Qdrant collection (1536-dim Cosine, configurable `MEMORY_EMBEDDING_DIMENSIONS`) if absent; create 3 payload indexes (workspace_id KEYWORD, agent_fqn KEYWORD, scope KEYWORD); create Neo4j `node_workspace` index and `node_unique` constraint via async session
- [X] T010 [P] Add `MEMORY_*` settings fields to `apps/control-plane/src/platform/common/config.py`: `memory_embedding_dimensions: int = 1536`, `memory_embedding_api_url: str`, `memory_embedding_model: str`, `memory_rate_limit_per_min: int = 60`, `memory_rate_limit_per_hour: int = 500`, `memory_contradiction_similarity_threshold: float = 0.90`, `memory_contradiction_edit_distance_threshold: float = 0.15`, `memory_consolidation_enabled: bool = True`, `memory_consolidation_interval_minutes: int = 15`, `memory_consolidation_cluster_threshold: float = 0.85`, `memory_consolidation_llm_enabled: bool = False`, `memory_consolidation_min_cluster_size: int = 3`, `memory_differential_privacy_enabled: bool = False`, `memory_differential_privacy_epsilon: float = 1.0`, `memory_rrf_k: int = 60`, `memory_session_cleaner_interval_minutes: int = 60`
- [X] T011 Implement `get_memory_service()` DI factory in `apps/control-plane/src/platform/memory/dependencies.py` — inject `AsyncSession`, `AsyncQdrantClient`, `AsyncGraphDatabase` driver, `AsyncRedis`, `AiokafkaProducer`, `MemoryRepository`, and in-process `workspaces_service` + `registry_service` dependencies

**Checkpoint**: Foundation complete — all models, schemas, repository, events, and settings in place. User story implementation can now begin.

---

## Phase 3: User Story 1 — Scoped Memory Storage and Write Gate (Priority: P1) 🎯 MVP

**Goal**: Memory write gate with authorization, rate limiting, contradiction detection, retention enforcement, optional differential privacy, and scoped vector storage in Qdrant.

**Independent Test**: Write a per-agent memory → verify `WriteGateResult` returned with `memory_entry_id`; write contradicting memory → verify `contradiction_detected: true` and `EvidenceConflict` created; exceed rate limit → verify `429` with `Retry-After`; write from unauthorized agent → verify `403`; write session-only to permanent scope → verify `422`.

- [X] T012 [US1] Implement `MemoryWriteGate` in `apps/control-plane/src/platform/memory/write_gate.py`: `validate_and_write()` pipeline — (1) `_check_authorization()` via in-process `registry_service.get_namespace()` + `workspaces_service.get_membership()`, raises `WriteGateAuthError`; (2) `_check_rate_limit()` via Redis Lua `rate_limit_check.lua` on keys `mem:ratelimit:{agent_fqn}:min` (60s TTL) and `mem:ratelimit:{agent_fqn}:hour` (3600s TTL), raises `WriteGateRateLimitError` with remaining cooldown; (3) `_validate_retention()` — session_only requires `execution_id`, permanent not allowed on session-scope; (4) `_check_contradiction()` — Qdrant search (cosine ≥ threshold, same scope/workspace filters) + normalized Levenshtein edit distance > threshold → create `EvidenceConflict` record, emit `conflict.detected` event; (5) `_apply_differential_privacy()` — Laplace noise on numeric substrings if workspace setting enabled; (6) PostgreSQL insert via repository; (7) Qdrant upsert with payload `{memory_entry_id, workspace_id, agent_fqn, scope, source_authority, created_at_ts}` — compensating PostgreSQL soft-delete on Qdrant failure; (8) create `EmbeddingJob` record if embedding API call fails; (9) emit `memory.written` event
- [X] T013 [US1] Implement `MemoryService` write methods in `apps/control-plane/src/platform/memory/service.py`: `write_memory()` (delegates to write gate), `get_memory_entry()` (workspace-scoped fetch), `list_memory_entries()` (paginated, scope/agent filters + workspace isolation), `delete_memory_entry()` (only writing agent or workspace admin, soft-delete PG + Qdrant point delete), `transfer_memory_scope()` (additional authorization check, copy via write gate, set `provenance_consolidated_by` to original)
- [X] T014 [US1] Implement memory entry REST endpoints in `apps/control-plane/src/platform/memory/router.py`: `POST /entries` (write_memory, 201), `GET /entries/{entry_id}` (get_memory_entry, 200), `GET /entries` (list_memory_entries paginated, 200), `DELETE /entries/{entry_id}` (delete, 204), `POST /entries/{entry_id}/transfer` (transfer_memory_scope, 201) — all workspace-scoped via JWT claim

**Checkpoint**: US1 complete — agents can write scoped memories through the write gate, contradiction detection works, rate limiting enforced, memories retrievable by ID.

---

## Phase 4: User Story 2 — Hybrid Retrieval with Rank Fusion (Priority: P1)

**Goal**: Hybrid retrieval coordinator combining vector (Qdrant), keyword (PostgreSQL FTS), and graph (Neo4j) sources using reciprocal rank fusion with recency and authority post-processing.

**Independent Test**: Write 3 memories covering vector/keyword/graph signals; call `POST /memory/retrieve` with query "ACME payment terms" → verify results from multiple sources in `sources_contributed`; verify most-recent memory outranks older with same relevance; verify `partial_sources` populated when Neo4j is unavailable; verify `contradiction_flag: true` when `EvidenceConflict` exists for a returned result.

- [X] T015 [US2] Implement `RetrievalCoordinator` in `apps/control-plane/src/platform/memory/retrieval_coordinator.py`: `_vector_search()` — Qdrant search with `must` filters on `workspace_id` + scope visibility (per_agent: also filter `agent_fqn`; per_workspace: filter `workspace_id`; shared_orchestrator: filter workspace + orchestrator scope), returns top 20 with cosine scores; `_keyword_search()` — async SQLAlchemy `to_tsquery()` on `content_tsv` GIN index with same scope/workspace WHERE clauses, returns top 20 ranked by `ts_rank()`; `_graph_search()` — Neo4j Cypher entity name match with `WHERE n.workspace_id = $workspace_id` propagation, returns top 20 node contents; `_reciprocal_rank_fusion()` — k=60, score `= sum(1/(k+rank_i))` across all sources where doc appears; `_apply_recency_weight()` — multiply by `exp(-decay * age_days)` where decay configured by `MEMORY_RECENCY_DECAY`; `_apply_authority_weight()` — multiply by `source_authority`; `_flag_contradictions()` — cross-reference `EvidenceConflict` records for result pairs, set `contradiction_flag` and `conflict_ids` on affected results; `retrieve()` — gather all 3 sources with `asyncio.gather` (catch individual source errors → populate `partial_sources`), fuse, weight, flag, return `RetrievalResponse`
- [X] T016 [US2] Wire `retrieve()` and `retrieve_for_context()` (internal interface) into `MemoryService` in `apps/control-plane/src/platform/memory/service.py`: `retrieve()` calls `RetrievalCoordinator`; `retrieve_for_context()` wraps `retrieve()` with 800ms timeout, logs partial source failures without raising, returns `list[RetrievalResult]`
- [X] T017 [US2] Add `POST /retrieve` endpoint to `apps/control-plane/src/platform/memory/router.py`: accepts `RetrievalQuery`, returns `RetrievalResponse` (200) — workspace-scoped, passes `agent_fqn` from JWT for scope visibility enforcement

**Checkpoint**: US2 complete — hybrid retrieval returns fused results; `retrieve_for_context()` internal interface ready for context engineering service.

---

## Phase 5: User Story 3 — Evidence Conflict Management (Priority: P1)

**Goal**: Conflict listing, review, and dismissal endpoints for workspace operators to manage contradiction flags.

**Independent Test**: Create two contradicting memories (from US1/US3 write gate) → call `GET /memory/conflicts?status=open` → verify both appear; call `POST /conflicts/{id}/resolve` with `action: dismiss` → verify status transitions to `dismissed`; verify dismissed conflict does not appear in `open` filter.

- [X] T018 [US3] Implement conflict management methods in `apps/control-plane/src/platform/memory/service.py`: `list_conflicts()` (paginated, workspace-scoped, optional status filter), `resolve_conflict()` (validates reviewer has workspace admin role via `workspaces_service`, transitions status to `dismissed` or `resolved`, sets `reviewed_by` + `reviewed_at` + `resolution_notes`)
- [X] T019 [US3] Add conflict endpoints to `apps/control-plane/src/platform/memory/router.py`: `GET /conflicts` (list, 200 paginated), `POST /conflicts/{conflict_id}/resolve` (resolve, 200 `EvidenceConflictResponse`)

**Checkpoint**: US3 complete — operators can list and dismiss/resolve contradiction flags.

---

## Phase 6: User Story 4 — Knowledge Graph Operations (Priority: P2)

**Goal**: Node creation, edge creation, multi-hop traversal, and provenance chain queries backed by Neo4j with PostgreSQL metadata mirror.

**Independent Test**: Create nodes "Agent-A", "Tool-DocExtractor", "Fact-NET30"; create edges A→Tool ("used") and Tool→Fact ("produced"); call `POST /graph/traverse` from Agent-A with `max_hops: 2` → verify Fact-NET30 in results; call `GET /graph/nodes/{id}/provenance` on Fact-NET30 → verify full chain returned; query from different workspace → verify zero results.

- [X] T020 [US4] Implement knowledge graph service methods in `apps/control-plane/src/platform/memory/service.py`: `create_knowledge_node()` — PostgreSQL insert first (get UUID), then Neo4j `CREATE (n:MemoryNode {...})` — on Neo4j failure, rollback PostgreSQL record; `create_knowledge_edge()` — PostgreSQL insert, then Neo4j `MATCH + CREATE` edge — compensating PostgreSQL delete on Neo4j failure; `traverse_graph()` — Neo4j Cypher `MATCH path = (s:MemoryNode {pg_id: $id, workspace_id: $ws})-[:MEMORY_REL*1..$max_hops]->(e:MemoryNode {workspace_id: $ws}) WHERE all(n IN nodes(path) WHERE n.workspace_id = $ws)` with depth limit, map path to response; `get_provenance_chain()` — backward traversal Cypher from target node, return full chain with timestamps
- [X] T021 [US4] Add knowledge graph endpoints to `apps/control-plane/src/platform/memory/router.py`: `POST /graph/nodes` (201 `KnowledgeNodeResponse`), `POST /graph/edges` (201 `KnowledgeEdgeResponse`), `POST /graph/traverse` (200 `GraphTraversalResponse`), `GET /graph/nodes/{node_id}/provenance` (200 `GraphTraversalResponse`) — all workspace-scoped; `GraphUnavailableError` maps to 503 with `partial_sources: ["graph"]`

**Checkpoint**: US4 complete — knowledge graph nodes, edges, multi-hop traversal, and provenance chains all functional; graph results feed into hybrid retrieval via `_graph_search()`.

---

## Phase 7: User Story 5 — Trajectory Capture and Pattern Promotion (Priority: P2)

**Goal**: Immutable trajectory record storage and pattern nomination/approval workflow where approved patterns become workspace-scoped memory entries.

**Independent Test**: Call `POST /trajectories` with full action sequence → verify 201 and immutable record created; nominate pattern from trajectory → verify `PatternAssetResponse` with status `pending`; approve → verify status `approved` and `memory_entry_id` set (workspace-scoped `MemoryEntry` created); reject a different nomination → verify status `rejected` with `rejection_reason`; verify `GET /patterns?status=approved` only returns approved entries.

- [X] T022 [US5] Implement trajectory and pattern service methods in `apps/control-plane/src/platform/memory/service.py`: `record_trajectory()` (insert-only, no update path, immutable); `get_trajectory()` (workspace-scoped fetch); `nominate_pattern()` (create `PatternAsset` in pending status, linked to trajectory if provided); `review_pattern()` — if approved: (1) call `write_gate.validate_and_write()` with pattern content to per_workspace scope (nominated_by as agent_fqn), (2) set `pattern_assets.memory_entry_id` to new entry UUID, (3) emit `pattern.promoted` event; if rejected: set status `rejected` + `rejection_reason`; `list_patterns()` (paginated, workspace-scoped, optional status filter)
- [X] T023 [US5] Add trajectory and pattern endpoints to `apps/control-plane/src/platform/memory/router.py`: `POST /trajectories` (201), `GET /trajectories/{id}` (200), `POST /patterns` (201), `POST /patterns/{pattern_id}/review` (200), `GET /patterns` (200 paginated)

**Checkpoint**: US5 complete — execution trajectories captured immutably, patterns nominatable and approvable through full workflow, approved patterns discoverable via hybrid retrieval.

---

## Phase 8: User Story 6 — Consolidation Workers and Cross-Scope Transfer (Priority: P3)

**Goal**: Background APScheduler workers (EmbeddingWorker 30s, ConsolidationWorker 15min, SessionMemoryCleaner 60min) that process pending embeddings, distill recurring knowledge, and clean up expired session memories.

**Independent Test**: Create 3 agent-scoped memories with similar content; run `ConsolidationWorker.run()` directly; verify consolidated workspace-scoped memory created with `provenance_consolidated_by` links on originals; create a memory with `session_only` retention and expired `ttl_expires_at`; run `SessionMemoryCleaner.run()`; verify soft-deleted; create a memory with pending embedding job; run `EmbeddingWorker.run()`; verify `embedding_status = completed` and `qdrant_point_id` set.

- [X] T024 [US6] Implement `EmbeddingWorker` in `apps/control-plane/src/platform/memory/embedding_worker.py`: `run()` entry point called by APScheduler every 30s; `_process_pending_jobs()` — query `get_pending_embedding_jobs(limit=50)`, set status to `processing`, call embedding API via `httpx.AsyncClient.post()` to `settings.memory_embedding_api_url`, on success: Qdrant upsert with point_id = memory_entry_id UUID, update `memory_entries.embedding_status = completed` + `qdrant_point_id`, mark job `completed`; on failure: increment `retry_count`, set error_message, reset to `pending` (max 3 retries then `failed`)
- [X] T025 [US6] Implement `ConsolidationWorker` in `apps/control-plane/src/platform/memory/consolidation_worker.py`: `run()` entry; `_find_consolidation_candidates()` — per workspace, fetch agent-scoped entries and do Qdrant batch similarity search to find cosine ≥ 0.85 clusters with ≥ `MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE` members; `_distill()` — if `MEMORY_CONSOLIDATION_LLM_ENABLED`: httpx POST to embedding/LLM API; else use highest `source_authority` member as distilled content; `_promote()` — call `write_gate.validate_and_write()` with distilled content to per_workspace scope, then bulk-update `provenance_consolidated_by` on all source entries; emit `consolidation.completed` event with counts and duration
- [X] T026 [US6] Implement `SessionMemoryCleaner` inline in `apps/control-plane/src/platform/memory/consolidation_worker.py` (or separate class): `run()` — query `get_session_only_expired()` (entries with `retention_policy = session_only` AND `ttl_expires_at < now()`), soft-delete each via repository, fire-and-forget Qdrant point delete for each with `qdrant_point_id` set
- [X] T027 [US6] Register all three APScheduler workers in `apps/control-plane/entrypoints/worker_main.py`: `EmbeddingWorker.run` every 30 seconds; `ConsolidationWorker.run` every `settings.memory_consolidation_interval_minutes` minutes; `SessionMemoryCleaner.run` every `settings.memory_session_cleaner_interval_minutes` minutes

**Checkpoint**: US6 complete — embedding backlog drained continuously; agent memory distilled and promoted to workspace scope by consolidation; expired session memories cleaned hourly.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Wiring, linting, coverage, and integration verification

- [X] T028 Mount memory router in `apps/control-plane/src/platform/api/__init__.py`: `app.include_router(memory_router, prefix="/api/v1/memory", tags=["memory"])`
- [X] T029 [P] Call `memory_setup.setup_memory_collections()` in `apps/control-plane/entrypoints/api_main.py` lifespan startup (idempotent — safe to call on every restart)
- [X] T030 [P] Call `memory_setup.setup_memory_collections()` in `apps/control-plane/entrypoints/worker_main.py` lifespan startup
- [X] T031 [P] Write unit tests `apps/control-plane/tests/unit/test_mem_write_gate.py`: authorization rejection, rate limit enforcement (mock Redis), retention policy mismatch, contradiction detection threshold logic, differential privacy noise application, compensating delete on Qdrant failure
- [X] T032 [P] Write unit tests `apps/control-plane/tests/unit/test_mem_retrieval_coordinator.py`: RRF score calculation with 1/2/3 sources contributing, recency weight ordering, authority weight ordering, partial source handling (individual source exception caught), contradiction flag cross-reference
- [X] T033 [P] Write unit tests `apps/control-plane/tests/unit/test_mem_scope_isolation.py`: per_agent scope filter (agent_fqn match), per_workspace scope filter, shared_orchestrator filter, cross-workspace isolation
- [X] T034 [P] Write integration tests `apps/control-plane/tests/integration/test_mem_write_retrieve.py`: end-to-end write → EmbeddingWorker drain → vector retrieve pipeline; keyword retrieve via FTS
- [X] T035 [P] Write integration tests `apps/control-plane/tests/integration/test_mem_contradiction.py`: write + contradicting write → EvidenceConflict created → conflict appears in list → resolve → status updated
- [X] T036 [P] Write integration tests `apps/control-plane/tests/integration/test_mem_graph_operations.py`: node + edge creation (PostgreSQL + Neo4j dual write), multi-hop traversal workspace isolation, provenance chain
- [X] T037 [P] Write integration tests `apps/control-plane/tests/integration/test_mem_trajectory_patterns.py`: trajectory record create + fetch; nominate → approve → memory entry created; nominate → reject → not discoverable
- [X] T038 [P] Write integration tests `apps/control-plane/tests/integration/test_mem_consolidation.py`: similar entries → ConsolidationWorker run → consolidated entry created + provenance links; SessionMemoryCleaner removes expired session entries
- [X] T039 Run `ruff check src/platform/memory/ --fix` and `mypy src/platform/memory/ --strict` — resolve all errors in `apps/control-plane/`
- [X] T040 Run full test suite with coverage `pytest tests/ -k "memory" --cov=src/platform/memory --cov-report=term-missing` — achieve ≥ 95% coverage per SC-010

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — foundational models, repository, write gate infra
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (requires existing memories for retrieval testing)
- **US3 (Phase 5)**: Depends on Phase 2 + US1 (conflicts created by write gate in US1)
- **US4 (Phase 6)**: Depends on Phase 2 — graph operations independent from US1/US2/US3
- **US5 (Phase 7)**: Depends on Phase 2 + US1 (pattern approval calls write gate)
- **US6 (Phase 8)**: Depends on Phase 2 + US1 + US2 (workers operate on existing memories, EmbeddingWorker feeds Qdrant for vector search)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Phase 2 — no story dependencies
- **US2 (P1)**: Can start in parallel with US1 if Phase 2 complete; requires US1 for meaningful integration tests
- **US3 (P1)**: Can start in parallel with US1 — conflict management is a small isolated set of endpoints
- **US4 (P2)**: Independent from US1/US2/US3 — graph store is separate
- **US5 (P2)**: Independent from US4; depends on US1's write gate for pattern approval
- **US6 (P3)**: Depends on US1+US2 being complete (workers process memory entries and feed vector search)

### Parallel Opportunities Within Each Story

**US1**: T012 (write gate) must precede T013 (service methods), which must precede T014 (router)  
**US2**: T015 (retrieval coordinator) must precede T016 (service wire-up), then T017 (router)  
**US3**: T018 (service) must precede T019 (router)  
**US4**: T020 (service) must precede T021 (router)  
**US5**: T022 (service) must precede T023 (router)  
**US6**: T024 (EmbeddingWorker), T025 (ConsolidationWorker), T026 (SessionMemoryCleaner) are [P] — different files; T027 (APScheduler registration) depends on all three  
**Polish**: T031–T038 are all [P] — different test files, independent

---

## Parallel Example: Polish Phase

```bash
# All test files can be written in parallel (different files):
Task: "Write test_mem_write_gate.py"        # T031
Task: "Write test_mem_retrieval_coordinator.py"  # T032
Task: "Write test_mem_scope_isolation.py"   # T033
Task: "Write test_mem_write_retrieve.py"    # T034
Task: "Write test_mem_contradiction.py"     # T035
Task: "Write test_mem_graph_operations.py"  # T036
Task: "Write test_mem_trajectory_patterns.py"  # T037
Task: "Write test_mem_consolidation.py"     # T038
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 (write gate + scoped storage)
4. Complete Phase 4: US2 (hybrid retrieval)
5. **STOP and VALIDATE**: Write a memory, wait for EmbeddingWorker, retrieve it — verify end-to-end pipeline
6. Wire `retrieve_for_context()` to context engineering service (feature 022 `LongTermMemoryAdapter`)

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 + US3 → memory writing with contradiction detection and conflict management → MVP
3. US2 → hybrid retrieval (unblocks context engineering integration)
4. US4 → knowledge graph enrichment (enriches retrieval without blocking anything)
5. US5 → trajectory capture + pattern promotion
6. US6 → workers (embedding drain, consolidation, session cleanup)
7. Polish → tests, linting, coverage gate

### Parallel Team Strategy

With multiple developers (after Phase 2 complete):

- Developer A: US1 (write gate — most complex, blocks US2/US3/US5/US6)
- Developer B: US4 (knowledge graph — fully independent)
- Developer A → US2 after US1
- Developer B → US5 after US4 + US1 complete
- Both → US3 (small, 2 tasks), US6, Polish

---

## Notes

- [P] tasks = different files, no dependencies on each other
- [Story] label maps task to specific user story for traceability
- Trajectory records (US5) are immutable — `TrajectoryRecord` has no update path in repository
- Write gate is the single enforcement boundary — pattern approval (US5) and scope transfer (US1) call it normally, never bypass
- `retrieve_for_context()` (US2) is the internal interface for context engineering — no HTTP call, in-process only (§I)
- PostgreSQL FTS on `content_tsv` is internal to the memory bounded context — not user-facing search (OpenSearch is for that)
- Neo4j writes always have PostgreSQL mirror inserts first; on Neo4j failure, compensate by rolling back PostgreSQL record
- Qdrant writes always come after PostgreSQL insert (get UUID first); on Qdrant failure, compensate by soft-deleting PostgreSQL record
