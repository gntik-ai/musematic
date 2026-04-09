# Implementation Plan: Qdrant Vector Search

**Branch**: `005-qdrant-vector-search` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/005-qdrant-vector-search/spec.md`

## Summary

Deploy Qdrant as the dedicated vector search engine for the Agentic Mesh Platform. The implementation delivers: a Helm chart for Qdrant StatefulSet (3-node prod with replication factor 2, single-node dev), an idempotent Python collection initialization script (4 collections with HNSW + payload indexes), a daily backup CronJob uploading snapshots to object storage, network policy for namespace isolation, API key authentication, and a Python async gRPC client wrapper (`qdrant-client 1.12+`).

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: qdrant-client[grpc] 1.12+ (Python async gRPC client), Helm 3.x (Qdrant official chart: qdrant/qdrant)  
**Storage**: Qdrant (vector search engine, deployed as StatefulSet — no operator)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (Qdrant) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python Qdrant client) + scripts  
**Performance Goals**: < 50ms p99 search for 1M vectors with payload filter; ≥ 95% recall at ef_construction=128, m=16  
**Constraints**: Workspace-scoped search mandatory; API key required for all requests; backup to object storage (feature 004 dependency)  
**Scale/Scope**: 4 collections, 3 production nodes, replication factor 2

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS |
| Qdrant client | `qdrant-client 1.12+` per constitution §2.1 | PASS |
| Qdrant mode | "async gRPC preferred, REST fallback" per constitution §2.1 | PASS — `prefer_grpc=True` |
| Qdrant technology | Qdrant per constitution §2.4 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS |
| Namespace: observability | `platform-observability` per constitution | PASS — metrics on port 6333 |
| No vectors in PostgreSQL | Constitution AD-3.3 + spec clarification | PASS — all vectors in Qdrant |
| Helm chart conventions | No operator sub-dependencies | PASS — Qdrant has no operator; StatefulSet direct |
| Async everywhere | `qdrant-client` async mode throughout | PASS |
| Secrets not in LLM context | API key managed via Kubernetes Secret | PASS |
| Observability | Qdrant Prometheus metrics at `/metrics` | PASS |
| Backup storage | Feature 004 (minio-object-storage) dependency documented | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/005-qdrant-vector-search/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (collection registry, payload schemas, client interface)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── qdrant-cluster.md          # Cluster infrastructure contract
│   └── python-qdrant-client.md   # Python client interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/qdrant/
├── Chart.yaml                  # Chart metadata, qdrant/qdrant dependency locked to exact version
├── values.yaml                 # Shared defaults (3 replicas, HNSW config, dimensions=768)
├── values-prod.yaml            # Production overrides (resource limits, PVC size, auth enabled)
├── values-dev.yaml             # Development overrides (1 replica, no cluster mode, smaller PVC)
└── templates/
    ├── secret-api-key.yaml     # Secret: qdrant-api-key with QDRANT_API_KEY
    ├── network-policy.yaml     # NetworkPolicy (client, metrics, inter-node)
    └── backup-cronjob.yaml     # CronJob running backup_qdrant_snapshots.py daily at 02:00 UTC

apps/control-plane/src/platform/common/clients/qdrant.py
    # AsyncQdrantClient using qdrant-client 1.12+ with prefer_grpc=True
    # Methods: upsert_vectors, search_vectors, delete_vectors, get_collection_info,
    #          health_check, create_collection_if_not_exists, create_payload_index
    # Helpers: workspace_filter(workspace_id, extra) → Filter
    # Data types: PointStruct, ScoredPoint, CollectionInfo
    # Exception: QdrantError

apps/control-plane/scripts/
├── init_qdrant_collections.py      # Idempotent collection init: 4 collections + payload indexes
└── backup_qdrant_snapshots.py      # Snapshot all collections → upload to object storage

apps/control-plane/tests/integration/
├── test_qdrant_basic.py            # Upsert, search, delete, workspace isolation
├── test_qdrant_filtered_search.py  # Compound filters, recall measurement
└── test_qdrant_backup.py           # Snapshot + restore round-trip
```

**Structure Decision**: Python client in `apps/control-plane/src/platform/common/clients/qdrant.py` (pre-defined in constitution §4 repo structure). Scripts in `apps/control-plane/scripts/` (alongside control plane package to share its `qdrant-client` dependency). Helm chart at `deploy/helm/qdrant/` consistent with features 001–004.

Note: The Qdrant StatefulSet itself is deployed via the official `qdrant/qdrant` Helm chart as a dependency (pinned to exact version). The `deploy/helm/qdrant/` wrapper chart adds only the Secret, NetworkPolicy, and CronJob on top.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Qdrant as StatefulSet (no operator) — official Helm chart
- Collection init via idempotent Python script (not Helm hook Job)
- HNSW defaults: m=16, ef_construction=128, full_scan_threshold=10000
- API key auth via `QDRANT__SERVICE__API_KEY` env var
- Backup via Qdrant snapshot REST API + Python S3 upload
- Network policy: ports 6333 (REST+metrics), 6334 (gRPC), 6335 (inter-node)
- Python client: `qdrant-client 1.12+` with `prefer_grpc=True`

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Collection registry (4 collections + payload schemas), Helm values schema, client interface
- [contracts/qdrant-cluster.md](contracts/qdrant-cluster.md) — Cluster infrastructure contract
- [contracts/python-qdrant-client.md](contracts/python-qdrant-client.md) — Python client interface contract
- [quickstart.md](quickstart.md) — 10-section deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: Qdrant cluster deployment (Helm chart, StatefulSet, Secret)  
**P1 — US2**: Collection provisioning (init script, 4 collections, payload indexes)  
**P1 — US3**: Vector upsert/search (AsyncQdrantClient, workspace filter, integration tests)  
**P1 — US4**: Search latency SLA (HNSW tuning, filtered search, recall test)  
**P2 — US5**: Backup/restore (CronJob, backup script, restore documentation)  
**P2 — US6**: Network policy (NetworkPolicy template)  
**P2 — US7**: API key authentication (Secret, env var injection)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | Official Qdrant Helm chart as chart dependency | No Qdrant operator; official chart is best-maintained |
| Collection init | Idempotent Python script | Reuses platform `qdrant-client`; safer than Helm hook Job |
| HNSW parameters | m=16, ef_construction=128 | Qdrant-recommended defaults; meet 95% recall + 50ms SLA |
| Authentication | API key via Kubernetes Secret | Constitution-mandated; single key simplifies secret management |
| Backup mechanism | Qdrant snapshot REST API + Python S3 upload | Native snapshot API; reuses `AsyncObjectStorageClient` (feature 004) |
| gRPC vs REST | gRPC for data ops, REST for admin | Constitution mandates `prefer_grpc=True`; REST for snapshot API only |
| Workspace isolation | Client-enforced `workspace_id` filter | Cluster is filter-agnostic; `workspace_filter()` helper enforces convention |

## Dependencies

- **Upstream**: Feature 004 (minio-object-storage) — backup CronJob uploads to `backups/qdrant/` prefix
- **Downstream**: All bounded contexts using semantic memory, agent recommendation, similarity testing
- **Parallel with**: Kafka (003), MinIO (004) — no dependency relationship
- **Blocks**: Memory retrieval, agent marketplace recommendation, semantic testing

## Complexity Tracking

No constitution violations. Standard complexity for this feature. Qdrant has no operator — this is documented in the spec as a known exception to the operator pattern used by features 001–004.
