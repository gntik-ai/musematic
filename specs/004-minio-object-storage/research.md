# Research: S3-Compatible Object Storage

**Feature**: 004-minio-object-storage  
**Date**: 2026-04-09  
**Phase**: 0 — Pre-design research

---

## Decision 1: MinIO Deployment Model (Operator vs. Standalone)

**Decision**: Use the MinIO Operator with a `Tenant` CRD (`minio.min.io/v2`). The operator watches `Tenant` resources and manages the MinIO cluster lifecycle. Production deploys a `Tenant` with `pools[0].servers: 4` and `pools[0].volumesPerServer: 4` (16 PVCs total, EC:4 erasure coding). Development deploys a single-server standalone mode via a simpler `Deployment` + `PVC` (operator not used in dev to avoid dependency).

**Rationale**: The MinIO Operator is the recommended Kubernetes-native deployment. It handles rolling upgrades, pod scheduling, and cluster expansion. The `Tenant` CRD provides declarative configuration consistent with the platform's Helm + operator pattern (same as CloudNativePG for PostgreSQL, Strimzi for Kafka). Development standalone avoids the operator dependency for local testing.

**Alternatives considered**:
- StatefulSet with MinIO in distributed mode without operator: more manual management, no CRD lifecycle. Rejected — inconsistent with platform's operator pattern.
- Single StatefulSet for all environments: lacks erasure coding semantics for production. Rejected.

---

## Decision 2: Bucket Creation Mechanism

**Decision**: Use a Kubernetes `Job` (init job) that runs the MinIO client (`mc`) after cluster startup to create buckets, apply lifecycle policies, enable versioning, and configure bucket policies. The Job is templated in Helm and runs as a post-install hook. It reads credentials from the `Tenant`'s root credentials secret.

**Rationale**: The MinIO Operator does not have a `Bucket` CRD (unlike Strimzi's `KafkaTopic`). The standard approach is an `mc` client Job. This is idempotent — `mc mb --ignore-existing` is safe to re-run. The Job is a Helm post-install + post-upgrade hook so it re-runs on upgrades.

**Alternatives considered**:
- Terraform MinIO provider: external dependency, not in platform toolchain. Rejected.
- MinIO Operator `PolicyBinding` CRD: only manages IAM policies, not bucket creation or lifecycle. Insufficient alone.
- Custom Python script in init container: `mc` is the official MinIO CLI and handles all needed operations natively. Rejected in favor of `mc`.

---

## Decision 3: Bucket Lifecycle Policies

**Decision**: Lifecycle policies are set via `mc ilm rule add` in the init Job. Per-bucket rules:

| Bucket | Lifecycle | `mc` rule |
|--------|-----------|-----------|
| `agent-packages` | Indefinite (no expiry rule) | Versioning enabled only |
| `execution-artifacts` | Configurable (default 90d) | `--expire-days 90` |
| `reasoning-traces` | 90 days | `--expire-days 90` |
| `sandbox-outputs` | 30 days | `--expire-days 30` |
| `evidence-bundles` | Indefinite (no expiry rule) | None |
| `simulation-artifacts` | 30 days | `--expire-days 30` |
| `backups` | 30 days | `--expire-days 30` |
| `forensic-exports` | 90 days | `--expire-days 90` |

Incomplete multipart upload cleanup: `--expire-days 7 --incomplete` applied to all buckets.

**Rationale**: S3 lifecycle rules are the standard mechanism. MinIO fully supports S3-compatible lifecycle XML. The init Job applies rules via `mc ilm rule add` which translates to PUT Bucket Lifecycle API calls. Rules are idempotent when applied with consistent IDs.

**Alternatives considered**:
- Lifecycle via Terraform: external toolchain. Rejected.
- Lifecycle via custom Python (boto3): workable but `mc` is simpler and official. Rejected.

---

## Decision 4: Versioning Configuration

**Decision**: Object versioning is enabled on the `agent-packages` bucket only via `mc version enable alias/agent-packages`. Versioning is a bucket-level configuration, not an object-level one. Once enabled, all subsequent writes create a new version. Version listing and retrieval use standard S3 `ListObjectVersions` and `GetObject?versionId=` APIs.

**Rationale**: Per FR-006 and User Story 4. Versioning on all buckets would add storage overhead and complexity. Only `agent-packages` requires immutable revision history per the spec. The `evidence-bundles` bucket stores indefinitely but doesn't require versioning since evidence bundles are immutable by write pattern (one upload per bundle, no overwrites).

**Alternatives considered**:
- Versioning on all buckets: excessive storage overhead for transient data buckets (sandbox-outputs, simulation-artifacts). Rejected.
- Object Lock (WORM mode): stronger guarantee but requires MinIO Enterprise. Rejected — standard versioning is sufficient.

---

## Decision 5: Simulation Isolation

**Decision**: Use MinIO bucket policies (S3 IAM policies) to enforce isolation. Two sets of credentials are provisioned: (1) `platform-credentials` (access to all production buckets), (2) `simulation-credentials` (access to `simulation-artifacts` bucket only). The init Job creates a MinIO user for simulation and attaches a policy restricting access to `simulation-artifacts/*`. Services in `platform-simulation` namespace use `simulation-credentials`.

**Rationale**: Per constitution AD-3.7: "Simulation workloads run in a separate Kubernetes namespace with network policies." The bucket-level IAM policy ensures even if network policy is bypassed, simulation credentials cannot access production buckets. Two Kubernetes secrets are created: `minio-platform-credentials` and `minio-simulation-credentials`.

**Alternatives considered**:
- Separate MinIO clusters for simulation and production: overkill for current scale, doubles infrastructure. Rejected.
- Network policy alone (no IAM): defense-in-depth requires both layers. Rejected.

---

## Decision 6: Network Policy

**Decision**: Three network policies:
1. **client-access**: Allow ingress to port 9000 (S3 API) from `platform-control`, `platform-execution`, `platform-simulation` namespaces.
2. **console-access**: Allow ingress to port 9001 (MinIO Console) from `platform-observability` (operators access via monitoring namespace or ingress).
3. **metrics**: Allow ingress to port 9000/metrics from `platform-observability`.

**Rationale**: MinIO exposes S3 API and Console on the same service with different ports (9000/9001). Metrics are served by the MinIO Prometheus scrape endpoint at `/minio/v2/metrics/cluster` on port 9000. All live in `platform-data` namespace per constitution.

**Alternatives considered**:
- Single broad network policy: violates constitution isolation. Rejected.
- Console on separate service port 9001: MinIO Operator creates a separate service for the Console. This is the default — use it.

---

## Decision 7: Helm Chart Structure

**Decision**: Single Helm chart at `deploy/helm/minio/` with:
- `Tenant` CR (production) / standalone `Deployment` (dev) controlled by `values.standalone` flag
- `Job` template for bucket initialization (post-install hook)
- `ConfigMap` with `mc` init script
- `NetworkPolicy` resources (3 policies)
- `Secret` for root credentials (generated via Helm `randAlphaNum`)
- No `dependencies` in Chart.yaml — MinIO operator is a cluster prerequisite

**Rationale**: Consistent with feature 001 (CloudNativePG), 002 (Redis), 003 (Kafka). Operator is pre-installed; chart deploys the `Tenant` CRD and supporting resources.

**Alternatives considered**:
- Bitnami MinIO chart: does not use MinIO Operator; standalone only. Insufficient for production erasure coding. Rejected.

---

## Decision 8: aioboto3 Python Client Wrapper

**Decision**: Implement `AsyncObjectStorageClient` in `apps/control-plane/src/platform/common/clients/object_storage.py` using `aioboto3` (async wrapper over `boto3`). The client wraps common operations: `upload_object`, `download_object`, `delete_object`, `list_objects`, `upload_multipart`, `get_presigned_url`. Initialized from `Settings` with `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_USE_SSL`.

**Rationale**: Constitution specifies `boto3 / aioboto3 (latest)` for object storage. `aioboto3` wraps `aiobotocore` to provide async context manager semantics compatible with the platform's async-everywhere requirement. The client implements `async with` for resource lifecycle management.

**Alternatives considered**:
- `minio-py` (official MinIO Python SDK): synchronous, no async support. Rejected per constitution async requirement.
- Raw `aiobotocore`: lower-level, more verbose. `aioboto3` is the right abstraction layer. Rejected.

---

## Resolution Summary

All technical unknowns resolved. No NEEDS CLARIFICATION markers remain. Plan can proceed to Phase 1.
