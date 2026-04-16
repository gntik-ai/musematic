# Implementation Plan: OpenSearch Full-Text Search

**Branch**: `008-opensearch-full-text-search` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/008-opensearch-full-text-search/spec.md`

## Summary

Deploy OpenSearch 2.x as the dedicated full-text search engine for marketplace agent discovery, audit log search, and operator diagnostic queries. The implementation delivers: a wrapper Helm chart at `deploy/helm/opensearch/` using the official `opensearch-project/opensearch` and `opensearch-project/opensearch-dashboards` charts as dependencies, ICU analysis plugin installation via the chart plugin installer, synonym dictionary ConfigMap-mounted at pod startup, three index templates (marketplace-agents, audit-events, connector-payloads) with separate index-time and search-time analyzers plus ISM lifecycle policies created by an idempotent Python init Job, snapshot backup to MinIO via OpenSearch Snapshot Management (SM), a typed `AsyncOpenSearchClient` wrapper, and workspace-scoped search projection writers.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: `opensearch-py 2.x` (async client), Helm 3.x (wrapper chart with official opensearch-project charts as dependencies)  
**Storage**: OpenSearch 2.18.x (full-text search engine, StatefulSet — no operator) + OpenSearch Dashboards (separate Deployment)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (OpenSearch) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python OpenSearch client) + scripts  
**Performance Goals**: Search queries with filters < 200ms p99 at 100,000 documents (SC-004); snapshot complete < 15 minutes for 10M documents (SC-008)  
**Constraints**: Workspace-scoped queries mandatory (workspace_id filter always injected); security plugin disabled in dev, enabled in prod; backup depends on feature 004 (minio-object-storage); projection-indexer integration is out of scope  
**Scale/Scope**: 3 index templates, 2 ISM policies, 1 SM snapshot policy, 1 snapshot repository; 3-node production cluster, 1-node dev

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS |
| OpenSearch client | `opensearch-py 2.x` per constitution §2.1 | PASS |
| OpenSearch version | OpenSearch 2.x per constitution §2.4 | PASS |
| OpenSearch port | 9200 per constitution §2.4 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS |
| Namespace: observability | `platform-observability` per constitution — metrics at `:9600` | PASS |
| No PostgreSQL FTS | Constitution AD-3.3: "Never use PostgreSQL FTS for user-facing search" | PASS — all FTS in OpenSearch |
| No vectors in OpenSearch | Clarification in spec: "OpenSearch is for full-text search ONLY" | PASS — vectors in Qdrant |
| Helm chart conventions | No operator sub-dependencies | PASS — StatefulSet via official chart, no operator |
| Async everywhere | `AsyncOpenSearch` from opensearch-py 2.x | PASS |
| Secrets not in LLM context | Password managed via Kubernetes Secret `opensearch-credentials` | PASS |
| Observability | OpenSearch Performance Analyzer at `:9600` | PASS |
| Backup storage | Feature 004 (minio-object-storage) dependency documented | PASS |
| Client wrapper location | `apps/control-plane/src/platform/common/clients/opensearch.py` per constitution §4 | PASS |
| Search bounded context | `apps/control-plane/src/platform/search/` per constitution §4 | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/008-opensearch-full-text-search/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (index mappings, Helm schema, client interface)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── opensearch-cluster.md          # Cluster infrastructure contract
│   └── python-opensearch-client.md    # Python client interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/opensearch/
├── Chart.yaml                      # Wrapper chart; deps: opensearch-project/opensearch, /opensearch-dashboards
├── values.yaml                     # Shared defaults (security config, resources, persistence)
├── values-prod.yaml                # Production overrides (3 replicas, 8GB JVM, 100Gi PVC)
├── values-dev.yaml                 # Dev overrides (1 node, 512MB JVM, security disabled)
└── templates/
    ├── configmap-synonyms.yaml     # ConfigMap: agent-synonyms.txt
    ├── secret-credentials.yaml     # Secret: opensearch-credentials (username + password)
    ├── init-job.yaml               # Helm post-install/post-upgrade hook (Python init)
    └── network-policy.yaml         # NetworkPolicy (9200 from platform-control, platform-execution)

deploy/opensearch/init/
└── init_opensearch.py              # Idempotent init: ISM policies, index templates, snapshot repo, SM policy

apps/control-plane/src/platform/common/clients/opensearch.py
    # AsyncOpenSearchClient using opensearch-py 2.x (AsyncOpenSearch)
    # Methods: index_document, bulk_index, search, search_after, delete_document, delete_by_query, health_check, close
    # Types: SearchResult, BulkIndexResult, ClusterHealth
    # Exceptions: OpenSearchClientError, OpenSearchConnectionError, OpenSearchIndexError, OpenSearchQueryError

apps/control-plane/src/platform/search/projections.py
    # AgentSearchProjection: index_agent, delete_agent, bulk_reindex
    # AuditSearchProjection: index_event
    # Query builders: build_agent_query, build_agent_aggregations

apps/control-plane/tests/integration/
├── test_opensearch_basic.py         # Index, retrieve, delete, health_check, bulk_index
├── test_opensearch_search.py        # BM25 search, workspace isolation, search_after pagination
├── test_opensearch_facets.py        # Aggregations: by_capability, by_maturity, trust_ranges
└── test_opensearch_synonyms.py      # Synonym expansion: summarizer→text summary agent
```

**Structure Decision**: Python client at `apps/control-plane/src/platform/common/clients/opensearch.py` (pre-defined in constitution §4). Search projection writer at `apps/control-plane/src/platform/search/projections.py` (constitution §4 `search/` bounded context). Init scripts at `deploy/opensearch/init/` (separate from Helm to allow standalone execution). Helm chart at `deploy/helm/opensearch/` using official charts as dependencies — no custom StatefulSet (unlike ClickHouse which couldn't use the official chart due to operator coupling).

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Official OpenSearch Helm chart (wrapper pattern with official chart as dependency)
- Security plugin disabled dev / enabled prod with internal user database
- ICU analysis plugin via the official chart plugin installer (not custom image)
- OpenSearch ISM for lifecycle policies (not Elasticsearch ILM)
- Python init Job with opensearch-py (idempotent PUT operations)
- Synonym dictionary as ConfigMap-mounted file
- Snapshot Management (SM) for scheduled snapshots (not Kubernetes CronJob)
- `AsyncOpenSearch` from opensearch-py 2.x

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Index templates (3), ISM policies (2), SM snapshot policy, Helm values schema, `AsyncOpenSearchClient` + projection interface
- [contracts/opensearch-cluster.md](contracts/opensearch-cluster.md) — Cluster infrastructure contract
- [contracts/python-opensearch-client.md](contracts/python-opensearch-client.md) — Python client interface contract
- [quickstart.md](quickstart.md) — 15-section deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: OpenSearch cluster deployment (Helm chart, StatefulSet, Dashboards, Secret, ICU plugin)  
**P1 — US2**: Template initialization (ISM policies, index templates, snapshot repo, init Job)  
**P1 — US3**: Marketplace search (AsyncOpenSearchClient, projections.py, workspace-scoped queries, integration tests)  
**P2 — US4**: Audit event search (AuditSearchProjection, audit-events index, search tests)  
**P2 — US5**: ISM lifecycle management (verify ISM auto-deletion, ILM expiry tests)  
**P2 — US6**: Snapshot backup (SM policy, manual snapshot test, restore test)  
**P2 — US7**: Network policy (NetworkPolicy template)  
**P2 — US8**: Synonym extensibility (update ConfigMap, reload analyzer, verify new synonyms)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | Wrapper Helm chart + official opensearch-project charts | Official chart is StatefulSet-based (no operator); wrapper adds project-specific resources |
| Plugin installation | Official chart plugin installer for `analysis-icu` and `repository-s3` | No custom image needed; version-compatible; required for ICU analysis and MinIO snapshots |
| Lifecycle policies | OpenSearch ISM (not Elasticsearch ILM) | ISM is the OpenSearch-native equivalent; correct API for OpenSearch 2.x |
| Index template API | `_index_template` (composable templates) | Current standard; supersedes legacy `_template` in OpenSearch 2.x |
| Synonym management | ConfigMap-mounted file | Operationally manageable without image rebuild; spec-mandated approach |
| Scheduled snapshots | OpenSearch Snapshot Management (SM) API | Native to OpenSearch; observable via Dashboards; no external CronJob needed |
| Python client | `AsyncOpenSearch` from `opensearch-py 2.x` | Constitution-mandated; async everywhere |
| Security | Disabled in dev (`DISABLE_SECURITY_PLUGIN=true`), enabled in prod | Simplifies local testing; prod uses internal user database (no LDAP/SAML) |

## Dependencies

- **Upstream**: Feature 004 (minio-object-storage) — MinIO provides the `backups` bucket for snapshots; bucket must exist before snapshot repository registration
- **Downstream**: Marketplace discovery APIs (reads from `marketplace-agents-*`); audit compliance APIs (reads from `audit-events-*`); projection-indexer runtime profile (writes to OpenSearch — implemented in downstream feature)
- **Parallel with**: Neo4j (006), ClickHouse (007), Qdrant (005), Redis (002) — no dependency relationship
- **Blocks**: Marketplace agent search UI, audit log search, operator diagnostic queries

## Complexity Tracking

No constitution violations. Standard complexity for this feature. Note that OpenSearch Dashboards is a separate Deployment (not part of the StatefulSet) — this is inherent to the OpenSearch architecture and cannot be simplified. The Helm chart cleanly handles both via two chart dependencies.
