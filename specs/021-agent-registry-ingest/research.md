# Research Notes: Agent Registry and Ingest

**Feature**: 021-agent-registry-ingest  
**Date**: 2026-04-11  
**Phase**: 0 — Resolve unknowns before design

---

## Decision 1: Multi-store architecture for agent data

**Decision**: Use 4 stores for 4 distinct access patterns — PostgreSQL for relational entity records (profiles, revisions, namespaces, audit), OpenSearch for keyword/field search (`marketplace-agents` index), Qdrant for semantic similarity (`agent_embeddings` collection), MinIO for package files (`agent-packages` bucket).

**Rationale**: Each store is optimized for its workload (constitution §III). PostgreSQL is the system-of-record for FQN uniqueness and lifecycle state. OpenSearch handles keyword search at query time. Qdrant handles vector similarity. MinIO handles large binary blobs.

**Alternatives considered**: Storing full-text search in PostgreSQL FTS — rejected by constitution (§III: "Never use PostgreSQL FTS for user-facing search"). Storing packages as BLOBs in PostgreSQL — rejected for operational reasons (backup complexity, storage costs, size limits).

---

## Decision 2: Package validation pipeline order (security-first)

**Decision**: Validate in strict fail-fast order: (1) Content-Type / file extension check → (2) Size limit check (50 MB, before reading content) → (3) Extract to isolated temp directory → (4) Path traversal check (resolve all member paths against temp root) → (5) Symlink rejection → (6) File count and depth limits → (7) Required structure check (manifest file present) → (8) Manifest parse and schema validation → (9) SHA-256 digest computation on the original archive bytes.

**Rationale**: Security checks run before any data storage. Size check is cheapest and rejects most abuse before extraction. Path traversal and symlink checks happen before any file is read. SHA-256 is computed last to avoid wasted computation on invalid packages.

**Alternatives considered**: Validating asynchronously after storing the package — rejected because the spec requires "zero invalid packages reach storage" (SC-002). Streaming validation without temp dir — rejected due to symlink resolution requiring materialized files.

---

## Decision 3: FQN uniqueness enforcement

**Decision**: Store namespace name in `registry_namespaces.name` with a unique constraint per workspace (`UNIQUE (workspace_id, name)`). Store `local_name` in `registry_agent_profiles.local_name` with a composite unique constraint `UNIQUE (namespace_id, local_name)`. Compute and store `fqn` as a VARCHAR column populated at the application layer as `"{namespace_name}:{local_name}"`. Add a global unique index on `registry_agent_profiles.fqn`.

**Rationale**: Application-layer computation is simpler than PostgreSQL generated columns and works with SQLAlchemy. Two unique constraints enforce both halves of FQN uniqueness. The stored `fqn` column enables fast O(1) FQN resolution via index lookup.

**Alternatives considered**: Computed/generated column in PostgreSQL — possible but adds migration complexity. Storing only namespace_id and local_name without fqn column — requires a JOIN on every FQN lookup, hurting the 200ms SLA (SC-003).

---

## Decision 4: OpenSearch indexing — synchronous, with background retry

**Decision**: Index agent metadata in OpenSearch synchronously during registration (after PostgreSQL commit). If OpenSearch is unavailable, catch the exception, mark a `needs_reindex` flag in PostgreSQL, and complete registration successfully. A background worker (`RegistryIndexWorker`) polls for `needs_reindex = true` agents on a 30-second interval and retries indexing.

**Rationale**: OpenSearch indexing is fast (<100ms under normal conditions) so blocking slightly is acceptable. The retry mechanism satisfies FR-023 (graceful degradation) while keeping the primary path simple.

**Alternatives considered**: Always async indexing via Kafka consumer — adds latency and complexity; synchronous is sufficient and simpler. Pure fire-and-forget without retry tracking — fails FR-023 requirement for eventual consistency guarantee.

---

## Decision 5: Qdrant embedding generation — always asynchronous

**Decision**: After successful registration (PostgreSQL + OpenSearch complete), dispatch a background asyncio task (`_generate_embedding_async`) that calls the embedding API (configurable endpoint in PlatformSettings) with the agent's `purpose + " " + approach` text, then upserts the vector into Qdrant with the `agent_profile_id` as the point ID. A `embedding_status` field (`pending`, `complete`, `failed`) is tracked in `registry_agent_profiles`.

**Rationale**: Embedding API calls take 200-2000ms and are subject to rate limiting. Blocking the upload response for this is a poor UX. The spec explicitly accepts eventual consistency (~30s) for semantic search (spec Assumptions section).

**Alternatives considered**: Kafka consumer pattern for embedding — adds infrastructure complexity for one background operation; asyncio task is sufficient. Generating embeddings during indexing synchronously — violates spec assumption of eventual consistency; blocks upload response unacceptably.

---

## Decision 6: MinIO package storage and atomicity

**Decision**: Object key pattern: `{workspace_id}/{namespace_name}/{local_name}/{revision_id}/package.tar.gz`. Upload to MinIO first (streaming the validated bytes), then create the `AgentRevision` record in PostgreSQL within the same logical operation. If MinIO upload fails → no PostgreSQL record created (clean failure). If PostgreSQL commit fails after MinIO upload → delete the MinIO object (compensating action in exception handler). This achieves upload atomicity without a distributed transaction.

**Rationale**: The spec requires all-or-nothing upload semantics (edge case: "upload is atomic"). MinIO-first with compensating delete is simpler than saga orchestration and sufficient for this workload.

**Alternatives considered**: PostgreSQL-first — leaves orphaned MinIO objects on failure; harder to clean up. Two-phase commit — unnecessary complexity for this use case.

---

## Decision 7: Lifecycle state machine implementation

**Decision**: Define `VALID_REGISTRY_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]]` in `registry/state_machine.py`. Valid graph: `draft → {validated}`, `validated → {published}`, `published → {disabled, deprecated}`, `disabled → {published}`, `deprecated → {archived}`. Service method `transition_agent_status()` checks the dict, creates a `LifecycleAuditEntry` record, updates `AgentProfile.status`, and emits the appropriate Kafka event (for `published` and `deprecated` transitions).

**Rationale**: Centralizing the transition graph in a single dict makes it easy to audit and test exhaustively. Service-layer enforcement (not database constraints) gives better error messages and event emission hooks.

**Alternatives considered**: Database-level check constraints — rigid, no event emission, poor error messages. State machine library (transitions, pytransitions) — overkill for 6 states and 7 transitions; a dict is readable and sufficient.

---

## Decision 8: Visibility filtering in discovery queries

**Decision**: In `RegistryService.list_agents()`, after fetching candidates from the primary store, apply visibility filtering using Python `re.fullmatch()` against each candidate's `fqn`. The effective visibility is the union of: (a) `requesting_agent.visibility_agents` patterns and (b) `WorkspaceVisibilityGrant` records fetched from the workspaces service interface. For human user queries, skip agent-level visibility and apply workspace membership filtering only.

**Rationale**: Python-side filtering is simpler to implement and test than pushing regex logic into PostgreSQL or OpenSearch queries. For ≤10,000 agents (SC-009), Python-side filtering of a reasonable result set is fast enough. Pattern union is necessary to implement FR-014.

**Alternatives considered**: OpenSearch query-time filtering with regex — complex to implement FQN pattern matching in OpenSearch DSL; Python filter is more maintainable. Caching visibility results — premature optimization; patterns can change and should take effect immediately (FR-021 corollary).

---

## Decision 9: OpenSearch and Qdrant setup scripts (idempotent at startup)

**Decision**: Create `registry_opensearch_setup.py` and `registry_qdrant_setup.py` modules in the `registry/` bounded context. Both are called from `api_main.py` and `worker_main.py` lifespan hooks. OpenSearch: create `marketplace-agents` index if not exists with mappings for fqn (keyword), name (text+keyword), purpose (text), approach (text), tags (keyword array), role_types (keyword array), maturity_level (integer), namespace (keyword), workspace_id (keyword), status (keyword). Qdrant: create `agent_embeddings` collection if not exists with vector size from `PlatformSettings.embedding_vector_size` (default 1536, OpenAI text-embedding-3-small).

**Rationale**: Same idempotent pattern established in feature 020 (`clickhouse_setup.py`). No Alembic equivalent for OpenSearch/Qdrant — idempotent creation scripts are the convention.

**Alternatives considered**: Create indices at first write — fails if both api and worker start simultaneously; idempotent startup is safer. Manual pre-provisioning — adds operational burden to every deployment.

---

## Decision 10: Kafka topic `registry.events`

**Decision**: Register `registry.events` as a new Kafka topic in the event registry. Events emitted: `registry.agent.created` (on successful registration), `registry.agent.published` (on published transition), `registry.agent.deprecated` (on deprecated transition). All events use the canonical `EventEnvelope` from feature 013 with `CorrelationContext` carrying `workspace_id`.

**Rationale**: Same pattern as `analytics.events` (feature 020), `workspaces.events` (feature 018). The constitution requires Kafka for async event coordination (§III).

**Alternatives considered**: Inline synchronous notification — violates constitution §III (never use DB polling for event-driven patterns); Kafka is required.

---

## Decision 11: Maturity level storage and assessment

**Decision**: Store `maturity_level` (0-3) directly on `AgentProfile` as an integer column. Create `AgentMaturityRecord` table for audit history of maturity changes (previous_level, new_level, assessment_method: `manifest_declared` | `system_assessed`, actor, reason, changed_at). The service method `update_maturity_level()` inserts an audit record and updates the profile. Default: 0 if not declared in manifest.

**Rationale**: Simple integer column on the profile for fast filtering. Separate audit table for history without row versioning overhead. Matches spec US4 requirements exactly.

**Alternatives considered**: Storing maturity history as JSON array on the profile — non-queryable, grows unboundedly. Full event sourcing for maturity — overkill for a simple 4-level classification.

---

## Decision 12: Package manifest format and required fields

**Decision**: Accept both YAML and JSON manifests. The manifest must contain: `local_name` (string, slug format), `version` (semver string), `purpose` (non-empty string), `role_types` (list with ≥1 valid role type). Optional fields: `approach` (string), `maturity_level` (0-3), `reasoning_modes` (list), `context_profile` (object), `tags` (list of strings), `display_name` (string). Validate with a Pydantic model `AgentManifest` during package ingestion.

**Rationale**: Pydantic validation gives precise error messages for manifest issues (SC-002 requires "specific error details"). Supporting both YAML and JSON reduces friction for developers. Required fields match FR-005, FR-006, FR-007.

**Alternatives considered**: JSON-only manifest — less ergonomic for developers who prefer YAML. Unstructured manifest parsing — no validation, violates SC-002.
