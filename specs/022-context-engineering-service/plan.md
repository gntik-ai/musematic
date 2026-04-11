# Implementation Plan: Context Engineering Service

**Branch**: `022-context-engineering-service` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/022-context-engineering-service/spec.md`

## Summary

Build the `context_engineering/` bounded context within `apps/control-plane/src/platform/`. This covers a deterministic context assembly pipeline from 9 source types (system instructions including agent purpose+approach, workflow state, conversation history, long-term memory via Qdrant, tool outputs, connector payloads, workspace metadata, reasoning traces, workspace goal super-context), a multi-dimensional quality scorer (6 sub-scores: relevance, freshness, authority, contradiction density, token efficiency, task brief coverage), budget enforcement with 4 compaction strategies (relevance truncation, priority eviction, hierarchical compression, semantic deduplication), mandatory privacy filtering via policies service, context drift monitoring (ClickHouse statistical analysis, APScheduler 5-min polling), context A/B testing (deterministic hash-based group assignment), and profile management (CRUD with agent/role-type/workspace assignment hierarchy). Storage: PostgreSQL (5 tables) + ClickHouse (`context_quality_scores`) + MinIO (`context-assembly-records` bucket). Primary deliverable is the `assemble_context()` internal interface consumed by the execution bounded context.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), clickhouse-connect 0.8+ (quality score time-series), qdrant-client 1.12+ async gRPC (long-term memory retrieval), APScheduler 3.x (drift monitor background task), httpx 0.27+ (optional: hierarchical compression LLM call)  
**Storage**: PostgreSQL (5 tables: context_engineering_profiles, context_profile_assignments, context_assembly_records, context_ab_tests, context_drift_alerts) + ClickHouse (context_quality_scores time-series) + MinIO (context-assembly-records bucket for full bundle text)  
**Testing**: pytest 8.x + pytest-asyncio  
**Target Platform**: Linux server, Kubernetes `platform-control` namespace (`api` profile for endpoints, `scheduler` profile for DriftMonitorTask)  
**Project Type**: Bounded context within modular monolith control plane  
**Performance Goals**: Assembly ≤ 500ms (5 sources), ≤ 2s (all 8+ sources) — SC-001; drift alerts within 5 minutes — SC-006; 1,000 assemblies/minute throughput — SC-008  
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; privacy filtering non-bypassable (FR-014); deterministic output (SC-002); no cross-boundary DB access  
**Scale/Scope**: 6 user stories, 25 FRs, 10 SCs, 9 REST endpoints + 1 internal interface, 5 PostgreSQL tables, 1 ClickHouse table, 1 MinIO bucket, 3 Kafka event types, 9 context source adapters

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated |
| Pydantic v2 for all schemas | PASS | §2.1 mandated |
| SQLAlchemy 2.x async only | PASS | §2.1 mandated — 5 PostgreSQL tables |
| All code async | PASS | Coding conventions: "All code is async" |
| Bounded context structure | PASS | models, schemas, service, repository, router, events, exceptions, dependencies, adapters, quality_scorer, compactor, privacy_filter, drift_monitor, context_engineering_clickhouse_setup |
| No cross-boundary DB access | PASS | §IV — all cross-context data via in-process service interfaces: policies_service, workspaces_service, execution_service, interactions_service, registry_service, connectors_service |
| Canonical EventEnvelope | PASS | All events on `context_engineering.events` use EventEnvelope from feature 013 |
| CorrelationContext everywhere | PASS | Events carry workspace_id + execution_id in CorrelationContext |
| Repository pattern | PASS | `ContextEngineeringRepository` (SQLAlchemy) in repository.py |
| Kafka for async events (not DB polling) | PASS | §III — events emitted on assembly, drift detection, budget exceeded |
| Alembic for PostgreSQL schema changes | PASS | migration 007_context_engineering for all 5 tables |
| ClickHouse for OLAP/time-series | PASS | §III — quality score time-series in ClickHouse; no PostgreSQL rollups |
| No PostgreSQL for rollups | PASS | §III — drift analysis via ClickHouse stddevPop/avg queries |
| Qdrant for vector search | PASS | §III — long-term memory retrieval via LongTermMemoryAdapter; no vectors in PostgreSQL |
| Redis for caching | PASS | Policy lookup uses 60-second in-memory TTL cache (not Redis — single process); for multi-instance, Redis would be appropriate but const is met by no shared-state polling |
| OpenSearch | N/A | Context engineering does not use full-text search |
| No PostgreSQL FTS | N/A | No full-text search use case in this bounded context |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | PASS | §XI — hierarchical compression uses LLM but passes only context text, not secrets; secret injection happens at tool level, not context level |
| Zero-trust visibility | PASS | §IX — privacy filter mandatory and non-bypassable (FR-014); policies_service determines data classification access |
| Goal ID as first-class correlation | PASS | §X — `goal_id` is a first-class parameter to `assemble_context()`; WorkspaceGoalHistoryAdapter reads workspace super-context for the GID |
| Modular monolith (no HTTP between contexts) | PASS | §I — `assemble_context()` is an in-process function call, not HTTP/gRPC |
| APScheduler for background tasks | PASS | §2.1 — DriftMonitorTask uses APScheduler, registered in scheduler_main.py |

**All 25 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/022-context-engineering-service/
├── plan.md                          # This file
├── spec.md                          # Feature specification
├── research.md                      # Phase 0 decisions (12 decisions)
├── data-model.md                    # Phase 1 — SQLAlchemy models, ClickHouse schema, Pydantic schemas, service class signatures
├── quickstart.md                    # Phase 1 — run/test guide
├── contracts/
│   └── context-engineering-api.md   # REST API contracts (9 endpoints + 1 internal interface)
└── tasks.md                         # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── context_engineering/
│       ├── __init__.py
│       ├── models.py                          # SQLAlchemy: 5 models + enums
│       ├── schemas.py                         # Pydantic: all request/response + internal schemas
│       ├── service.py                         # ContextEngineeringService — assembly pipeline + CRUD
│       ├── repository.py                      # ContextEngineeringRepository — SQLAlchemy CRUD
│       ├── router.py                          # FastAPI router: /api/v1/context-engineering/* (9 endpoints)
│       ├── events.py                          # Event payload types + publish_* helpers
│       ├── exceptions.py                      # ContextEngineeringError, ContextSourceUnavailableError, etc.
│       ├── dependencies.py                    # get_context_engineering_service DI factory
│       ├── adapters.py                        # ContextSourceAdapter protocol + 9 concrete adapters
│       ├── quality_scorer.py                  # QualityScorer — 6-dimension scoring
│       ├── compactor.py                       # ContextCompactor — 4 compaction strategies
│       ├── privacy_filter.py                  # PrivacyFilter — policy-based element exclusion
│       ├── drift_monitor.py                   # DriftMonitorTask — APScheduler background task
│       └── context_engineering_clickhouse_setup.py  # Idempotent context_quality_scores table
├── migrations/
│   └── versions/
│       └── 007_context_engineering.py         # Alembic: 5 tables + indexes
└── tests/
    ├── unit/
    │   ├── test_ce_quality_scorer.py          # QualityScorer sub-score and aggregate tests
    │   ├── test_ce_compactor.py               # Compaction strategy correctness + minimum viable context
    │   ├── test_ce_privacy_filter.py          # Filter by data classification + exclusion logging
    │   ├── test_ce_schemas.py                 # Pydantic validation tests
    │   └── test_ce_determinism.py             # Deterministic assembly with same inputs
    └── integration/
        ├── test_ce_assembly_pipeline.py       # Full assembly: sources → privacy → score → compact → record
        ├── test_ce_profile_management.py      # Profile CRUD + assignment hierarchy resolution
        ├── test_ce_ab_testing.py              # A/B test group distribution + metrics tracking
        ├── test_ce_drift_monitor.py           # Drift alert generation from ClickHouse data
        └── test_ce_budget_enforcement.py      # Over-budget compaction + minimum viable context
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/context_engineering/` package with all module stubs
- `context_engineering_clickhouse_setup.py`: idempotent `create_context_quality_scores_table()` with MergeTree engine, month partitioning, 90-day TTL
- Alembic migration `007_context_engineering.py`: all 5 tables + unique constraints + indexes

### Phase 2 — US1+US3: Context Assembly with Provenance and Privacy (P1)
- `models.py`: all 5 SQLAlchemy models + enums
- `schemas.py`: `ContextElement`, `ContextBundle`, `ContextQualityScore`, `ContextProvenanceEntry`, `BudgetEnvelope`, `SourceConfig`, `ProfileCreate/Response`, `ProfileAssignmentCreate`, `AssemblyRecordResponse`, `DriftAlertResponse`, `AbTestCreate/Response`
- `exceptions.py`: `ContextEngineeringError`, `ContextSourceUnavailableError`, `ProfileNotFoundError`, `InvalidProfileAssignmentError`, `AbTestNotFoundError`
- `adapters.py`: `ContextSourceAdapter` protocol + all 9 concrete adapters including `WorkspaceGoalHistoryAdapter` (super-context)
- `privacy_filter.py`: `PrivacyFilter` — fetch policies from `policies_service`, evaluate each element, log exclusions
- `repository.py`: `ContextEngineeringRepository` — all SQLAlchemy CRUD for 5 tables + `get_agents_needing_drift_check()`
- `service.py`: `assemble_context()` — profile resolution → source fetching (ordered, with partial-sources handling) → privacy filter → quality score (pre) → budget check → compaction if needed → quality score (post) → persist assembly record → emit `assembly.completed` event → write quality score to ClickHouse
- `events.py`: `AssemblyCompletedPayload` + `publish_assembly_completed()`

### Phase 3 — US2: Quality Scoring and Budget Enforcement with Compaction (P1)
- `quality_scorer.py`: `QualityScorer` with all 6 scoring methods + configurable weights
- `compactor.py`: `ContextCompactor` — `relevance_truncate()`, `priority_evict()`, `semantic_deduplicate()`, `hierarchical_compress()` (async, LLM call, opt-in), minimum viable context protection
- Wire quality_scorer and compactor into `service.assemble_context()` (pre+post compaction scoring)

### Phase 4 — US4: Drift Monitoring and Alerting (P2)
- `drift_monitor.py`: `DriftMonitorTask` — ClickHouse query for per-agent rolling stats, degradation detection (mean - 2*stddev), `ContextDriftAlert` creation, Kafka event emission
- `events.py`: `DriftDetectedPayload` + `publish_drift_detected()`; `BudgetExceededMinimumPayload` + `publish_budget_exceeded_minimum()`
- `service.py`: `run_drift_analysis()`, `list_drift_alerts()`, `resolve_drift_alert()`
- `router.py`: `GET /drift-alerts`, `POST /drift-alerts/{id}/resolve`

### Phase 5 — US5: Context A/B Testing (P2)
- `service.py`: `create_ab_test()`, `get_ab_test()`, `end_ab_test()`, `get_ab_test_results()`, `_resolve_ab_test_profile()` (hash-based group assignment)
- `repository.py`: A/B test CRUD + `update_ab_test_metrics()` (update aggregated counts/means)
- `router.py`: `POST /ab-tests`, `GET /ab-tests`, `GET /ab-tests/{id}`, `POST /ab-tests/{id}/end`
- Wire A/B test profile selection into `assemble_context()` before adapter fetch

### Phase 6 — US6: Profile Management (P3)
- `service.py`: `create_profile()`, `list_profiles()`, `get_profile()`, `update_profile()`, `delete_profile()`, `assign_profile()`, `resolve_profile()` (agent → role_type → workspace → built-in default resolution)
- `dependencies.py`: `get_context_engineering_service()` DI factory
- `router.py`: `POST /profiles`, `GET /profiles`, `GET /profiles/{id}`, `PUT /profiles/{id}`, `DELETE /profiles/{id}`, `POST /profiles/{id}/assign`

### Phase 7 — Polish & Cross-Cutting Concerns
- Mount context engineering router in `src/platform/api/__init__.py`
- Register `DriftMonitorTask` in `apps/control-plane/entrypoints/scheduler_main.py` via APScheduler (every 5 minutes)
- Run `context_engineering_clickhouse_setup.create_context_quality_scores_table()` in `api_main.py` + `scheduler_main.py` lifespan (idempotent)
- Full test coverage audit (≥ 95%)
- ruff + mypy --strict clean run

## Key Decisions (from research.md)

1. **Storage split**: PostgreSQL (config + assembly records metadata) + ClickHouse (quality time-series) + MinIO (full bundle text) — each store for its workload (§III)
2. **Determinism**: Fixed profile-defined source order + (execution_id, step_id) deterministic seed + sort long-term memory by (score DESC, id ASC) for tie-breaking
3. **Quality scorer**: Pure Python heuristics (6 sub-scores) — no ML model; configurable sub-score weights in PlatformSettings
4. **Compaction strategy order**: Profile-defined sequence; hierarchical compression opt-in (LLM call); minimum viable context (system_instructions + most recent turn) always protected
5. **Privacy filter**: In-process `policies_service.get_active_context_policies()` + 60-second in-memory TTL cache; exclusions logged as provenance entries
6. **Drift monitor**: APScheduler every 5 minutes; ClickHouse `stddevPop` + `avg` over configurable window (default 7 days); alerts stored in PostgreSQL + emitted as Kafka events
7. **A/B group assignment**: `sha256(f"{test_id}:{execution_id}")[-8:]` mod 2 — deterministic, no shared state required
8. **Assembly record storage**: Fixed PostgreSQL columns for indexed fields + JSONB `provenance_chain`; full bundle in MinIO
9. **Context source adapters**: Async adapter protocol + DI; 9 adapters including `WorkspaceGoalHistoryAdapter` for super-context (GID-scoped workspace goal messages)
10. **New Kafka topic**: `context_engineering.events` — 3 event types; assembly.completed feeds analytics pipeline
11. **Internal interface**: `assemble_context()` is pure in-process async function — no HTTP/gRPC within monolith (§I)
12. **ClickHouse setup**: Idempotent `context_engineering_clickhouse_setup.py` — same pattern as feature 020 + 021
