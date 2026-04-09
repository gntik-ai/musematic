# Contract: Object Storage Cluster Infrastructure

**Feature**: 004-minio-object-storage  
**Type**: Infrastructure Contract  
**Date**: 2026-04-09

---

## Cluster Contract

Any service that connects to the object storage cluster must respect the following contract:

### Connection

| Property | Value |
|----------|-------|
| S3 API endpoint (production) | `http://musematic-minio.platform-data:9000` |
| S3 API endpoint (development) | `http://musematic-minio.platform-data:9000` |
| Console endpoint | `http://musematic-minio-console.platform-data:9001` |
| Region | `us-east-1` (MinIO default; set in client config) |
| Namespace requirement | Caller must be in `platform-control`, `platform-execution`, or `platform-simulation` (simulation-artifacts only) |

### Client Requirements

- All requests must include valid credentials (`MINIO_ACCESS_KEY` + `MINIO_SECRET_KEY`)
- Use the `minio-platform-credentials` secret for production bucket access
- Use the `minio-simulation-credentials` secret for simulation-artifacts bucket access only
- For objects > 100 MB, use multipart upload (mandatory per SC-003)
- S3 path-style addressing is used (not virtual-hosted-style): `http://endpoint/bucket/key`

### Bucket SLA

| Metric | Value |
|--------|-------|
| Upload/download latency p99 | < 200ms for objects < 1 MB same datacenter (SC-005) |
| Fault tolerance | Single-node failure with no data loss (SC-002) |
| Lifecycle execution | Expired objects deleted within 24 hours of expiration (SC-004) |

---

## Bucket Existence Contract

After Helm deployment, clients may assume all 8 buckets exist:
`agent-packages`, `execution-artifacts`, `reasoning-traces`, `sandbox-outputs`, `evidence-bundles`, `simulation-artifacts`, `backups`, `forensic-exports`.

Buckets will not be auto-created by the storage system. Missing buckets indicate a deployment issue (init Job failed).

---

## Credentials Contract

| Secret | Namespace | Buckets Accessible |
|--------|-----------|-------------------|
| `minio-platform-credentials` | `platform-data` | All except `simulation-artifacts` |
| `minio-simulation-credentials` | `platform-data` | `simulation-artifacts` only |

Services mount secrets as environment variables `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`.

---

## Network Policy Contract

| Source Namespace | S3 API (9000) | Console (9001) |
|-----------------|--------------|----------------|
| `platform-control` | Yes | No |
| `platform-execution` | Yes | No |
| `platform-simulation` | Yes (simulation bucket policy enforced separately) | No |
| `platform-observability` | Yes (metrics scrape only) | Yes (console access) |
| Any other namespace | No | No |
