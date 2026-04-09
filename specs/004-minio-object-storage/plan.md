# Implementation Plan: S3-Compatible Object Storage

**Branch**: `004-minio-object-storage` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/004-minio-object-storage/spec.md`

## Summary

Deploy MinIO as the S3-compatible object storage for the Agentic Mesh Platform. The implementation delivers: a Helm chart for MinIO cluster (4-node erasure-coded production, single-node dev), a post-install Job that creates all 8 buckets with lifecycle policies and versioning, network policies for namespace isolation, bucket-level IAM policies for simulation isolation, and a Python async S3 client wrapper (`aioboto3`) with full operation coverage.

## Technical Context

**Language/Version**: Python 3.12+ (control plane client)  
**Primary Dependencies**: aioboto3 latest (Python async S3 client), MinIO Operator (Kubernetes), Helm 3.x  
**Storage**: MinIO (S3-compatible object storage)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (MinIO) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python S3 client wrapper)  
**Performance Goals**: < 200ms p99 upload/download for objects < 1 MB; 1 GB multipart upload success  
**Constraints**: Single-node failure must not cause data loss (erasure coding); simulation artifacts must be isolated from production  
**Scale/Scope**: 8 buckets, 4 production nodes, 16 PVCs total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS — plan uses Python 3.12+ |
| Object storage client (Python) | `boto3 / aioboto3 (latest)` per constitution §2.1 | PASS — using aioboto3 |
| Object storage technology | MinIO (S3-compatible) per constitution §2.4 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS — MinIO lives in `platform-data` |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS — network policy allows both |
| Namespace: observability | `platform-observability` per constitution | PASS — metrics and console access from `platform-observability` |
| Namespace: simulation | `platform-simulation` per constitution AD-3.7 | PASS — simulation namespace gets restricted credentials |
| Simulation isolation | Constitution AD-3.7: separate namespace + network policies | PASS — bucket IAM policy + network policy enforced |
| Helm chart conventions | No operator sub-dependencies; exact versions | PASS — MinIO operator is pre-installed; chart deploys Tenant CRD only |
| Async everywhere | aioboto3 async API used throughout Python client | PASS |
| Secrets not in LLM context | MinIO credentials managed via Kubernetes Secrets | PASS |
| Observability | MinIO Prometheus metrics endpoint on port 9000 | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/004-minio-object-storage/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (bucket registry, credentials, Helm schema)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── object-storage-cluster.md       # Cluster infrastructure contract
│   └── python-object-storage-client.md # Python S3 client interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/minio/
├── Chart.yaml                    # Chart metadata (no dependencies — MinIO operator pre-installed)
├── values.yaml                   # Shared defaults (bucket list, storage class, etc.)
├── values-prod.yaml              # Production overrides (4 nodes, PVC sizes, resource limits)
├── values-dev.yaml               # Development overrides (standalone: true, 1 node)
└── templates/
    ├── tenant.yaml               # Tenant CR (MinIO Operator) — prod only
    ├── deployment.yaml           # Standalone Deployment — dev only
    ├── pvc.yaml                  # PersistentVolumeClaim — dev standalone only
    ├── secret-root.yaml          # Root credentials Secret (Helm randAlphaNum)
    ├── secret-platform.yaml      # Platform service credentials Secret
    ├── secret-simulation.yaml    # Simulation credentials Secret
    ├── bucket-init-configmap.yaml # ConfigMap with mc init shell script
    ├── bucket-init-job.yaml      # Job (post-install hook) running mc init script
    └── network-policy.yaml       # NetworkPolicy (client access, console, metrics)

apps/control-plane/src/platform/common/clients/object_storage.py
    # AsyncObjectStorageClient using aioboto3
    # Operations: upload_object, download_object, delete_object, list_objects,
    #             upload_multipart, get_presigned_url, object_exists, get_object_versions, health_check
    # Data types: ObjectInfo, ObjectVersion
    # Exceptions: ObjectStorageError, ObjectNotFoundError, BucketNotFoundError

apps/control-plane/tests/integration/
├── test_object_storage_basic.py       # PUT/GET/DELETE/LIST + multipart operations
├── test_object_storage_versioning.py  # Version list/retrieve for agent-packages
└── test_object_storage_lifecycle.py   # Lifecycle policy config validation
```

**Structure Decision**: Python S3 client lives in `apps/control-plane/src/platform/common/clients/` (consistent with `redis.py`, `qdrant.py` per constitution §4). Helm chart at `deploy/helm/minio/` consistent with features 001–003.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- MinIO Operator + `Tenant` CRD for production; standalone `Deployment` for dev
- Bucket creation via `mc` CLI post-install Job (no Bucket CRD in MinIO Operator)
- Lifecycle policies via `mc ilm rule add` (per-bucket expiry-days)
- Versioning on `agent-packages` only via `mc version enable`
- Simulation isolation via MinIO IAM bucket policies + separate credentials secret
- Network policy ports: 9000 (S3 + metrics), 9001 (Console)
- aioboto3 for async Python client

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Bucket registry (8 buckets + lifecycle), credentials, Helm values schema, client interface
- [contracts/object-storage-cluster.md](contracts/object-storage-cluster.md) — Cluster infrastructure contract
- [contracts/python-object-storage-client.md](contracts/python-object-storage-client.md) — Python S3 client interface contract
- [quickstart.md](quickstart.md) — 12-section deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

Implementation order follows spec priorities:

**P1 — US1**: MinIO cluster deployment (Helm chart, Tenant CR, dev standalone Deployment)  
**P1 — US2**: Bucket provisioning (init Job, mc script, lifecycle policies, versioning)  
**P1 — US3**: S3 client wrapper (AsyncObjectStorageClient, all operations, integration tests)  
**P2 — US4**: Versioning (get_object_versions, agent-packages integration test)  
**P2 — US5**: Simulation isolation (simulation credentials, IAM policy in mc script)  
**P2 — US6**: Network policy (NetworkPolicy templates)  
**P2 — US7**: Observability (Prometheus metrics endpoint, console access verification)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | MinIO Operator + Tenant CRD (prod), standalone Deployment (dev) | Operator pattern consistent with platform |
| Bucket creation | Post-install Job with `mc` CLI | No Bucket CRD in MinIO Operator; `mc` is official and idempotent |
| Lifecycle policies | `mc ilm rule add` in init Job | S3 lifecycle via `mc` — idempotent, no extra tooling |
| Versioning | `agent-packages` bucket only | Transient buckets don't need version history |
| Simulation isolation | IAM bucket policy + separate credentials | Defense-in-depth: network policy alone insufficient per constitution AD-3.7 |
| Python client | aioboto3 latest | Constitution-mandated async S3 client |
| Helm operator dep | None (MinIO operator is pre-installed) | Same pattern as features 001–003 |
| Metrics | MinIO built-in Prometheus endpoint on port 9000 | No separate exporter needed |

## Dependencies

- **Upstream**: MinIO Operator must be installed before Helm chart deployment
- **Downstream**: Agent package registry, execution artifacts, reasoning traces, forensic export, backup operations
- **Parallel with**: Kafka (003) — no dependency relationship
- **Blocks**: Any bounded context that stores binary artifacts

## Complexity Tracking

No constitution violations. Standard complexity for this feature.
