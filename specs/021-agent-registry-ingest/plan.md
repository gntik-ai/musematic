# Implementation Plan: Agent Registry and Ingest

**Branch**: `021-agent-registry-ingest` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/021-agent-registry-ingest/spec.md`

## Summary

Build the `registry/` bounded context within `apps/control-plane/src/platform/`. This covers agent namespace management, package upload/validation pipeline (path traversal, symlinks, size limits, manifest schema), SHA-256 immutable revisions stored in MinIO `agent-packages` bucket, PostgreSQL entity records (5 tables via Alembic migration 006), OpenSearch `marketplace-agents` synchronous indexing, Qdrant `agent_embeddings` async embedding generation, FQN uniqueness enforcement (`namespace:local_name`), lifecycle state machine (6 states, 7 transitions with full audit), maturity classification (Levels 0–3), zero-trust default visibility with FQN pattern filtering (union of per-agent + workspace grants), and 3 Kafka events on `registry.events`.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), opensearch-py 2.x async (keyword indexing), qdrant-client 1.12+ async gRPC (semantic search), aioboto3 latest (MinIO package storage), httpx 0.27+ (embedding API calls)  
**Storage**: PostgreSQL (5 tables: registry_namespaces, registry_agent_profiles, registry_agent_revisions, registry_maturity_records, registry_lifecycle_audit) + OpenSearch (marketplace-agents index) + Qdrant (agent_embeddings collection) + MinIO (agent-packages bucket)  
**Testing**: pytest 8.x + pytest-asyncio  
**Target Platform**: Linux server, Kubernetes `platform-control` namespace (`api` profile for endpoints, `worker` profile for index retry worker)  
**Project Type**: Bounded context within modular monolith control plane  
**Performance Goals**: FQN resolution ≤ 200ms (SC-003); keyword search ≤ 1s (SC-004); semantic search ≤ 2s (SC-005); upload validation ≤ 5s for rejected packages (SC-002); successful registration ≤ 10s end-to-end (SC-001)  
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; no cross-boundary DB access; no PostgreSQL FTS; package size ≤ 50MB configurable; embedding eventual consistency (~30s)  
**Scale/Scope**: 6 user stories, 24 FRs, 10 SCs, 10 REST endpoints + 2 internal interfaces, 5 PostgreSQL tables, 1 OpenSearch index, 1 Qdrant collection, 1 MinIO bucket, 3 Kafka event types

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated |
| Pydantic v2 for all schemas | PASS | §2.1 mandated |
| SQLAlchemy 2.x async only | PASS | §2.1 mandated — 5 PostgreSQL tables |
| All code async | PASS | Coding conventions: "All code is async" |
| Bounded context structure | PASS | models, schemas, service, repository, router, events, exceptions, dependencies, state_machine, package_validator, index_worker, registry_opensearch_setup, registry_qdrant_setup |
| No cross-boundary DB access | PASS | §IV — workspace membership via `workspaces_service` in-process; workspace visibility grants via `workspaces_service` in-process |
| Canonical EventEnvelope | PASS | All events on `registry.events` use EventEnvelope from feature 013 |
| CorrelationContext everywhere | PASS | Events carry workspace_id in CorrelationContext |
| Repository pattern | PASS | `RegistryRepository` (SQLAlchemy) in repository.py |
| Kafka for async events (not DB polling) | PASS | §III — events emitted on registration/publish/deprecation via `registry.events` |
| Alembic for PostgreSQL schema changes | PASS | migration 006_registry_tables for all 5 tables |
| OpenSearch for full-text search | PASS | §III — marketplace-agents index; never PostgreSQL FTS |
| Qdrant for vector search | PASS | §III — agent_embeddings collection; never PostgreSQL vectors |
| MinIO for object storage | PASS | §III — agent-packages bucket for package files |
| No PostgreSQL FTS | PASS | §III explicit — keyword search via OpenSearch |
| No vectors in PostgreSQL | PASS | §III explicit — embeddings in Qdrant only |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | N/A | No secrets in registry context |
| Zero-trust visibility | PASS | §IX — new agents default to empty visibility_agents=[]; FR-008 |
| FQN as primary addressing | PASS | §VIII — AgentProfile.fqn globally unique; resolution endpoint; FQN pattern matching |
| Goal ID as first-class correlation | N/A | Registry does not participate in goal execution flows |

**All 23 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/021-agent-registry-ingest/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 decisions (12 decisions)
├── data-model.md        # Phase 1 — SQLAlchemy models, Pydantic schemas, service classes
├── quickstart.md        # Phase 1 — run/test guide
├── contracts/
│   └── registry-api.md  # REST API contracts (10 endpoints + 2 internal interfaces)
└── tasks.md             # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── registry/
│       ├── __init__.py
│       ├── models.py                     # SQLAlchemy: AgentNamespace, AgentProfile, AgentRevision, AgentMaturityRecord, LifecycleAuditEntry
│       ├── schemas.py                    # Pydantic: all request/response schemas + AgentManifest
│       ├── service.py                    # RegistryService — all business logic
│       ├── repository.py                 # RegistryRepository — SQLAlchemy CRUD
│       ├── router.py                     # FastAPI router: /api/v1/namespaces + /api/v1/agents/* (10 endpoints)
│       ├── events.py                     # Event payload types + publish_* helpers for registry.events
│       ├── exceptions.py                 # RegistryError, FQNConflictError, InvalidTransitionError, PackageValidationError, etc.
│       ├── dependencies.py               # get_registry_service DI factory
│       ├── state_machine.py              # VALID_REGISTRY_TRANSITIONS dict + is_valid_transition()
│       ├── package_validator.py          # PackageValidator — security + structure + manifest validation
│       ├── index_worker.py               # RegistryIndexWorker — OpenSearch retry background worker
│       ├── registry_opensearch_setup.py  # Idempotent marketplace-agents index creation
│       └── registry_qdrant_setup.py      # Idempotent agent_embeddings collection creation
├── migrations/
│   └── versions/
│       └── 006_registry_tables.py        # Alembic: 5 registry tables + indexes
└── tests/
    ├── unit/
    │   ├── test_registry_package_validator.py  # PackageValidator security tests (path traversal, symlinks, size, manifest)
    │   ├── test_registry_state_machine.py      # VALID_REGISTRY_TRANSITIONS exhaustive tests
    │   ├── test_registry_schemas.py            # AgentManifest + request/response validation
    │   └── test_registry_visibility_filter.py  # FQN pattern matching + union logic
    └── integration/
        ├── test_registry_upload.py             # Full upload flow — validation, MinIO, PostgreSQL, OpenSearch
        ├── test_registry_discovery.py          # FQN resolution, pattern matching, keyword search
        ├── test_registry_lifecycle.py          # State transitions, audit records, event emission
        ├── test_registry_visibility.py         # End-to-end visibility filtering with workspace grants
        └── test_registry_revisions.py          # Revision immutability, listing, history
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/registry/` package with all module stubs
- `state_machine.py`: `VALID_REGISTRY_TRANSITIONS` dict, `is_valid_transition()`, `EVENT_TRANSITIONS` set
- Alembic migration `006_registry_tables.py`: all 5 tables + unique constraints + indexes
- `registry_opensearch_setup.py`: idempotent `marketplace-agents` index with mappings
- `registry_qdrant_setup.py`: idempotent `agent_embeddings` collection with configurable vector size

### Phase 2 — US1+US6: Agent Registration and Revisions
- `models.py`: all 5 SQLAlchemy models + enums
- `schemas.py`: `AgentManifest`, `NamespaceCreate`, `AgentUploadParams`, `AgentPatch`, request/response schemas
- `exceptions.py`: `RegistryError`, `FQNConflictError`, `NamespaceConflictError`, `PackageValidationError`, `InvalidTransitionError`, `AgentNotFoundError`, `WorkspaceAuthorizationError`, `RegistryStoreUnavailableError`
- `package_validator.py`: `PackageValidator` with 8-step validation pipeline
- `repository.py`: `RegistryRepository` — namespace CRUD, profile upsert, revision insert (no update), maturity record insert, audit entry insert, list/get queries
- `service.py`: `RegistryService.create_namespace()`, `upload_agent()`, `get_agent()`, `list_namespaces()`, `delete_namespace()`, `list_revisions()`
- `router.py`: `POST /namespaces`, `GET /namespaces`, `DELETE /namespaces/{id}`, `POST /agents/upload`, `GET /agents/{id}`, `GET /agents/{id}/revisions`
- `dependencies.py`: DI factories

### Phase 3 — US2: Agent Discovery and FQN Resolution
- `repository.py`: `get_by_fqn()`, `list_by_workspace()`, `search_by_keyword()` (OpenSearch)
- `service.py`: `resolve_fqn()`, `list_agents()` with visibility filtering (FQN pattern union + workspace grants)
- `router.py`: `GET /agents/resolve/{fqn}`, `GET /agents`
- `events.py`: `AgentCreatedPayload` + `publish_agent_created()`

### Phase 4 — US3: Lifecycle State Management
- `service.py`: `transition_lifecycle()` — state machine check + audit record + event emission
- `events.py`: `AgentPublishedPayload`, `AgentDeprecatedPayload`, `publish_agent_published()`, `publish_agent_deprecated()`
- `router.py`: `POST /agents/{id}/transition`, `GET /agents/{id}/lifecycle-audit`

### Phase 5 — US4: Maturity Classification
- `service.py`: `update_maturity()` — update profile + insert `AgentMaturityRecord`
- `router.py`: `POST /agents/{id}/maturity`

### Phase 6 — US5: Visibility Configuration Management
- `service.py`: Visibility pattern validation (re.fullmatch) in `patch_agent()` and `upload_agent()`; `resolve_effective_visibility()` internal interface
- `router.py`: `PATCH /agents/{id}` — visibility fields validated at patch time

### Phase 7 — US6 (remaining): Metadata Updates
- `service.py`: `patch_agent()` — mutable fields only, no revision creation
- Enforce immutability of `AgentRevision` in repository layer (no UPDATE methods on revisions)

### Phase 8 — Polish & Cross-Cutting Concerns
- `index_worker.py`: `RegistryIndexWorker` — background 30s poll for `needs_reindex = true`
- Async embedding generation task (dispatched after successful registration)
- Mount registry router in `src/platform/api/__init__.py`
- Register `RegistryIndexWorker` in `worker_main.py` lifespan
- Run `registry_opensearch_setup.py` + `registry_qdrant_setup.py` in `api_main.py` + `worker_main.py` lifespan (idempotent)
- Full test coverage audit (≥ 95%)
- ruff + mypy --strict clean run

## Key Decisions (from research.md)

1. **Multi-store architecture**: PostgreSQL (system-of-record), OpenSearch (keyword search), Qdrant (semantic), MinIO (packages) — each store for its workload (§III)
2. **Package validation order**: security-first (size → extract → path-traversal → symlinks → structure → manifest → digest) — fast-fail before any storage
3. **FQN uniqueness**: `UNIQUE (namespace_id, local_name)` + stored `fqn` column with global unique index — O(1) resolution lookup
4. **OpenSearch indexing**: synchronous during registration with `needs_reindex` flag + background retry worker for outages
5. **Qdrant embedding**: always async background task after registration — eventual consistency ~30s, `embedding_status` tracked
6. **MinIO atomicity**: MinIO upload first, then PostgreSQL commit; compensating MinIO delete on PostgreSQL failure
7. **Lifecycle state machine**: `VALID_REGISTRY_TRANSITIONS` dict in `state_machine.py`; service-layer enforcement with event emission for `published` and `deprecated`
8. **Visibility filtering**: Python-side `re.fullmatch()` on fetched results; union of per-agent patterns + workspace grants from `workspaces_service`
9. **Idempotent setup scripts**: `registry_opensearch_setup.py` + `registry_qdrant_setup.py` — same pattern as feature 020's `clickhouse_setup.py`
10. **New Kafka topic**: `registry.events` with 3 event types using canonical EventEnvelope
11. **Maturity audit trail**: separate `AgentMaturityRecord` table — queryable history without row versioning overhead
12. **Manifest format**: Pydantic `AgentManifest` validates both YAML and JSON; required: `local_name`, `version`, `purpose`, `role_types`
