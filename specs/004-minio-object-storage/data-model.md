# Data Model: S3-Compatible Object Storage

**Feature**: 004-minio-object-storage  
**Date**: 2026-04-09

---

## Bucket Registry

All 8 buckets provisioned by this feature.

| Bucket | Purpose | Retention | Versioning | Lifecycle Rule |
|--------|---------|-----------|-----------|----------------|
| `agent-packages` | Agent .tar.gz/.zip archives and extracted revisions | Indefinite | Enabled | None (retain all versions) |
| `execution-artifacts` | Step outputs, completion artifacts | 90 days (configurable) | Disabled | `--expire-days 90` |
| `reasoning-traces` | CoT dumps, ToT branch payloads, correction artifacts | 90 days | Disabled | `--expire-days 90` |
| `sandbox-outputs` | Sandbox stdout, stderr, produced files | 30 days | Disabled | `--expire-days 30` |
| `evidence-bundles` | Certification evidence, discovery evidence | Indefinite | Disabled | None |
| `simulation-artifacts` | Simulation outputs (isolated from production) | 30 days | Disabled | `--expire-days 30` |
| `backups` | PostgreSQL dumps, Qdrant snapshots, Neo4j dumps, ClickHouse backups | 30 days | Disabled | `--expire-days 30` |
| `forensic-exports` | Exported forensic packages | 90 days | Disabled | `--expire-days 90` |

**Incomplete multipart upload cleanup**: All buckets get an additional lifecycle rule: `--expire-days 7 --incomplete`.

---

## Object Key Conventions

Each service defines its own key scheme. Recommended conventions per bucket:

| Bucket | Key Pattern | Example |
|--------|------------|---------|
| `agent-packages` | `{namespace}/{agent_name}/{version}.tar.gz` | `finance-ops/kyc-verifier/1.2.3.tar.gz` |
| `execution-artifacts` | `{workspace_id}/{execution_id}/{step}/{filename}` | `ws-abc/exec-123/step-3/output.json` |
| `reasoning-traces` | `{execution_id}/{trace_type}/{timestamp}.json` | `exec-123/cot/1712620800.json` |
| `sandbox-outputs` | `{sandbox_id}/{timestamp}/{filename}` | `sb-456/1712620800/stdout.log` |
| `evidence-bundles` | `{agent_fqn}/{certification_id}/{evidence_type}` | `finance-ops:kyc/cert-789/discovery.json` |
| `simulation-artifacts` | `{simulation_id}/{run_id}/{filename}` | `sim-001/run-5/result.json` |
| `backups` | `{service}/{date}/{filename}` | `postgresql/2026-04-09/dump.sql.gz` |
| `forensic-exports` | `{request_id}/{filename}` | `req-forensic-001/export.zip` |

Key conventions are recommendations, not enforcement — the storage system stores opaque keys.

---

## Access Credentials

Two credential sets are provisioned as Kubernetes `Secret` resources in `platform-data`:

| Secret Name | Access Key | Permissions |
|-------------|-----------|-------------|
| `minio-platform-credentials` | `platform` | Read/Write all production buckets (all except `simulation-artifacts`) |
| `minio-simulation-credentials` | `simulation` | Read/Write `simulation-artifacts` bucket only |

Secrets contain `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` fields. Platform services mount these as environment variables. The `minio-platform-credentials` secret is the primary credential used by `AsyncObjectStorageClient`.

---

## Kubernetes Resources

### Production Resources

| Resource | Kind | Count |
|---------|------|-------|
| `Tenant` CR | `minio.min.io/v2` | 1 |
| PersistentVolumeClaims | `PVC` | 16 (4 servers × 4 volumes each) |
| `Secret` (root) | `Secret` | 1 (`minio-root-credentials`) |
| `Secret` (platform) | `Secret` | 1 (`minio-platform-credentials`) |
| `Secret` (simulation) | `Secret` | 1 (`minio-simulation-credentials`) |
| Bucket init `Job` | `Job` | 1 (post-install hook) |
| `NetworkPolicy` | `NetworkPolicy` | 3 |

### Development Resources

| Resource | Kind | Count |
|---------|------|-------|
| `Deployment` | `Deployment` | 1 (single node) |
| `PersistentVolumeClaim` | `PVC` | 1 |
| `Secret` (root) | `Secret` | 1 |
| `Secret` (platform) | `Secret` | 1 |
| `Secret` (simulation) | `Secret` | 1 |
| Bucket init `Job` | `Job` | 1 (post-install hook) |

### Namespace: `platform-data`

All MinIO infrastructure lives in `platform-data`.

### Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 9000 | HTTP/HTTPS | S3 API and Prometheus metrics (`/minio/v2/metrics/cluster`) |
| 9001 | HTTP/HTTPS | MinIO Console (management UI) |

### Service Reference

| Service Name | Port | Target |
|-------------|------|--------|
| `musematic-minio` | 9000 | S3 API |
| `musematic-minio-console` | 9001 | Management Console |

---

## Helm Values Schema

```yaml
# deploy/helm/minio/values.yaml (shared defaults)
clusterName: musematic-minio
namespace: platform-data
standalone: false               # true = dev single-node Deployment
servers: 4                      # prod: 4 nodes
volumesPerServer: 4             # prod: 4 PVCs per node = 16 total
storageClass: standard
storageSize: 100Gi              # per PVC; total = 1.6 TB raw
consoleEnabled: true
networkPolicy:
  enabled: true
buckets:
  executionArtifactsRetentionDays: 90
  # Other buckets have fixed retention (see Bucket Registry above)
```

---

## AsyncObjectStorageClient Interface

Located at: `apps/control-plane/src/platform/common/clients/object_storage.py`

```
AsyncObjectStorageClient
├── upload_object(bucket, key, data, content_type) → None
├── download_object(bucket, key) → bytes
├── delete_object(bucket, key) → None
├── list_objects(bucket, prefix) → list[ObjectInfo]
├── upload_multipart(bucket, key, file_path, content_type) → None
├── get_presigned_url(bucket, key, expires_in_seconds) → str
├── object_exists(bucket, key) → bool
└── get_object_versions(bucket, key) → list[ObjectVersion]

ObjectInfo:
├── key: str
├── size: int
├── last_modified: datetime
└── etag: str

ObjectVersion:
├── version_id: str
├── key: str
├── size: int
├── last_modified: datetime
└── is_latest: bool
```
