# Research: Qdrant Vector Search Deployment

**Feature**: 005-qdrant-vector-search  
**Date**: 2026-04-09  
**Phase**: 0 — Pre-design research

---

## Decision 1: Qdrant Deployment Model (StatefulSet, No Operator)

**Decision**: Deploy Qdrant as a Kubernetes `StatefulSet` directly — no dedicated operator exists for Qdrant. The official Qdrant Helm chart (`qdrant/qdrant`) is used as the basis. Production: 3 replicas with `replicationFactor: 2`. Development: 1 replica. Each pod gets a persistent volume via `volumeClaimTemplates`. The chart creates a `Service` for both REST (6333) and gRPC (6334) access.

**Rationale**: Qdrant provides an official Helm chart (`qdrant/qdrant`) that is the recommended Kubernetes deployment method. Unlike PostgreSQL (CloudNativePG), Kafka (Strimzi), and MinIO (MinIO Operator), Qdrant has no Kubernetes operator — the StatefulSet pattern is both the official and industry-standard approach. This is documented in the spec assumptions.

**Alternatives considered**:
- Custom StatefulSet without Qdrant chart: more maintenance burden. Rejected — official chart is better maintained.
- Deployment (not StatefulSet): StatefulSet is required for stable pod hostnames needed for Qdrant cluster peer-to-peer communication. Rejected.

---

## Decision 2: Collection Creation Mechanism

**Decision**: Use an idempotent Python script `apps/control-plane/scripts/init_qdrant_collections.py` that runs at platform startup (or on-demand via `platform-cli`). The script uses `qdrant-client` to call `recreate_collection` only if the collection doesn't exist (checked via `get_collection`). This is idempotent — safe to re-run.

**Rationale**: Qdrant has no CRD or declarative collection API (unlike Kafka's KafkaTopic CRs). The recommended pattern is an init script or a startup Job. An idempotent Python script (using the platform's own `qdrant-client`) is simpler than a Helm hook Job and reuses the same client used by platform services. The script can also be wired into `platform-cli preflight` for automated provisioning.

**Alternatives considered**:
- Helm post-install Job with `curl`: works but requires a container image with curl and API key handling; harder to maintain. Rejected in favour of the Python script.
- Qdrant REST API via init container: similar issues. Rejected.

**Note**: The script location is `apps/control-plane/scripts/init_qdrant_collections.py` (not `scripts/` at repo root) to keep it alongside the Python control plane that owns the `qdrant-client` dependency.

---

## Decision 3: HNSW Index Parameters

**Decision**: Default HNSW parameters per collection: `ef_construction: 128`, `m: 16`, `full_scan_threshold: 10000`. These are configurable via Helm values and the collection init script. `ef` (search time parameter) defaults to 128 as well, set per-search-request.

**Rationale**: `m=16` and `ef_construction=128` are the Qdrant-recommended defaults for general-purpose workloads. They achieve >95% recall with sub-50ms search for 1M vectors (per SC-003, SC-004). Higher `m` increases recall but also memory usage and index build time. `full_scan_threshold=10000` means collections with fewer than 10k vectors use brute force (perfect recall for small collections during development).

**Alternatives considered**:
- `m=32`, `ef_construction=200`: higher recall but 2x memory overhead. Unnecessary given 95% recall target. Rejected.
- Dynamic per-collection parameters: adds complexity without clear benefit. All 4 collections have similar workload characteristics. Rejected.

---

## Decision 4: API Key Authentication

**Decision**: Enable Qdrant API key authentication via `QDRANT__SERVICE__API_KEY` environment variable (set from a Kubernetes Secret). The Helm chart supports this natively. Both gRPC and REST endpoints require the key. A single API key is provisioned for all platform services (no per-service RBAC at the Qdrant layer — authorization is handled by the platform middleware).

**Rationale**: Per FR-009 and User Story 7. The constitution states API key is the authentication mechanism for Qdrant (constitution §2.1: `qdrant-client 1.12+`). Per-service RBAC is out of scope per spec assumption. Single key simplifies secret management and is consistent with how Redis auth and MinIO are handled.

**Alternatives considered**:
- JWT-based auth: not supported by Qdrant Community edition. Rejected.
- No auth (network policy only): defense-in-depth requires both layers per platform security posture. Rejected.

---

## Decision 5: Backup via Snapshot API + S3 Upload

**Decision**: A Kubernetes `CronJob` runs on schedule (default: `0 2 * * *` — daily at 02:00 UTC). It runs a Python script (`apps/control-plane/scripts/backup_qdrant_snapshots.py`) that: (1) calls the Qdrant REST snapshot API for each collection (`POST /collections/{name}/snapshots`); (2) downloads the snapshot file; (3) uploads to `s3://backups/qdrant/{collection}/{timestamp}.snapshot` via the platform's `AsyncObjectStorageClient`. Restore is a separate manual operation documented in the quickstart.

**Rationale**: Qdrant's native snapshot API is the recommended backup mechanism. Using the Python script (instead of `curl` in a shell Job) reuses the platform's existing `AsyncObjectStorageClient` (feature 004) and `qdrant-client`. This is consistent with how other platform scripts work and avoids a new container image.

**Alternatives considered**:
- `curl` + `aws s3 cp` in a shell script (as suggested in user input): requires installing both tools in the Job image. The Python script uses already-installed platform dependencies. Rejected.
- Qdrant full-disk backup (copy PVC data): requires stopping the pod. Rejected — snapshot API is online (no downtime).

---

## Decision 6: Network Policy

**Decision**: One `NetworkPolicy` resource:
- `podSelector: {app.kubernetes.io/name: qdrant}` allows ingress on ports 6333 (REST) and 6334 (gRPC) from `namespaceSelector` matching `platform-control` OR `platform-execution` (two separate `from` entries).
- An additional `from` entry allows ingress on port 6333 (metrics at `/metrics`) from `platform-observability`.
- Inter-pod communication (Qdrant cluster consensus port 6335): allow from same `podSelector` within `platform-data` namespace.

**Rationale**: Qdrant uses port 6335 for inter-node cluster communication (`p2p`). All three ports need to be considered. Metrics are exposed at `GET /metrics` on port 6333 (REST port), not a separate port.

**Alternatives considered**:
- Single broad policy for all ingress: violates constitution isolation. Rejected.
- Separate policy per namespace: functionally equivalent but more verbose. One policy with multiple `from` entries is cleaner. Rejected.

---

## Decision 7: Python Qdrant Client Wrapper

**Decision**: The existing `apps/control-plane/src/platform/common/clients/qdrant.py` file is referenced in the constitution's repo structure. This feature implements it using `qdrant-client 1.12+` in async gRPC mode (`prefer_grpc=True`). The wrapper exposes: `upsert_vectors`, `search_vectors`, `delete_vectors`, `get_collection_info`, `health_check`. The gRPC connection is used for all data operations; REST is used only for admin operations (snapshots) via the HTTP snapshot API.

**Rationale**: Constitution §2.1 mandates `qdrant-client 1.12+` with "async gRPC preferred, REST fallback". The async gRPC mode provides lower latency for the hot path (upsert + search). Snapshot backup uses the REST API because it's a file-streaming operation not well-suited to gRPC.

**Alternatives considered**:
- REST-only client: higher latency; gRPC is the constitution-mandated preference. Rejected.
- Separate clients for gRPC and REST: `qdrant-client` handles both internally with `prefer_grpc=True`. Rejected.

---

## Resolution Summary

All technical unknowns resolved. No NEEDS CLARIFICATION markers remain. Plan can proceed to Phase 1.
