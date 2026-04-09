# Contract: Qdrant Cluster Infrastructure

**Feature**: 005-qdrant-vector-search  
**Type**: Infrastructure Contract  
**Date**: 2026-04-09

---

## Cluster Contract

Any service that connects to the Qdrant cluster must respect the following contract:

### Connection

| Property | Value |
|----------|-------|
| REST endpoint | `http://musematic-qdrant.platform-data:6333` |
| gRPC endpoint | `musematic-qdrant.platform-data:6334` |
| Authentication | API key via `Authorization: api-key <key>` header (REST) or gRPC metadata `api-key` |
| API key source | `qdrant-api-key` Kubernetes Secret in `platform-data`, key `QDRANT_API_KEY` |
| Namespace requirement | Caller must be in `platform-control` or `platform-execution` |

### Client Requirements

- All requests must include the API key
- Use gRPC (port 6334) for data operations (upsert, search, delete) — lower latency
- Use REST (port 6333) for admin operations (collection info, snapshots, health check)
- All vector upserts must include `workspace_id` in the payload — required for filtering
- Query vectors must match the collection's configured dimension exactly (default: 768)

### Cluster SLA

| Metric | Value |
|--------|-------|
| Search latency p99 | < 50ms for 1M vectors with payload filter (SC-003) |
| Search recall | ≥ 95% vs. brute-force at ef_construction=128, m=16 (SC-004) |
| Fault tolerance | Single-node failure with no data loss (SC-002, replication factor 2) |

---

## Collection Existence Contract

After deployment and collection initialization, clients may assume all 4 collections exist:
`agent_embeddings`, `memory_embeddings`, `pattern_embeddings`, `test_similarity`

Collections will not be auto-created. Missing collections indicate a provisioning issue.

---

## Payload Filter Contract

All search queries targeting multi-tenant data **MUST** include a `workspace_id` filter. This is enforced by convention, not by the cluster — the platform's `AsyncQdrantClient` wrapper raises `ValueError` if `workspace_id` is absent from the filter for collections that require it.

---

## Network Policy Contract

| Source Namespace | REST (6333) | gRPC (6334) | Inter-node (6335) |
|-----------------|------------|------------|-------------------|
| `platform-control` | Yes | Yes | No |
| `platform-execution` | Yes | Yes | No |
| `platform-observability` | Yes (metrics) | No | No |
| `platform-data` (intra-pod) | Yes | Yes | Yes |
| Any other namespace | No | No | No |
