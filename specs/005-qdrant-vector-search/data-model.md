# Data Model: Qdrant Vector Search

**Feature**: 005-qdrant-vector-search  
**Date**: 2026-04-09

---

## Collection Registry

All 4 vector collections provisioned by this feature.

| Collection | Dimensions | Distance | HNSW m | HNSW ef_construction | Replication |
|-----------|-----------|---------|--------|----------------------|-------------|
| `agent_embeddings` | 768 (configurable) | Cosine | 16 | 128 | 2 (prod), 1 (dev) |
| `memory_embeddings` | 768 (configurable) | Cosine | 16 | 128 | 2 (prod), 1 (dev) |
| `pattern_embeddings` | 768 (configurable) | Cosine | 16 | 128 | 2 (prod), 1 (dev) |
| `test_similarity` | 768 (configurable) | Cosine | 16 | 128 | 2 (prod), 1 (dev) |

`full_scan_threshold: 10000` — collections with fewer than 10k vectors use brute-force search (perfect recall during development).

---

## Payload Schemas

### `agent_embeddings`

Stores agent revision embeddings for similarity search and recommendation.

```json
{
  "workspace_id": "uuid",        // INDEXED — mandatory, all queries scoped by this
  "agent_id": "uuid",            // INDEXED
  "revision_id": "uuid",         // identifies specific version
  "name": "string",              // human-readable agent name
  "purpose": "string",           // short description for display
  "lifecycle_state": "string",   // INDEXED — e.g., "draft", "published", "deprecated"
  "maturity_level": 1,           // INDEXED — integer 1-5
  "tags": ["string"],            // INDEXED — array of strings for keyword filtering
  "trust_score": 0.92,           // float 0-1
  "agent_fqn": "namespace:name"  // fully qualified name (constitution AD-3.8)
}
```

**Payload indexes**: `workspace_id` (keyword), `agent_id` (keyword), `lifecycle_state` (keyword), `maturity_level` (integer), `tags` (keyword)

---

### `memory_embeddings`

Stores agent memory entries for context-aware retrieval.

```json
{
  "workspace_id": "uuid",        // INDEXED — mandatory, all queries scoped by this
  "agent_id": "uuid",            // INDEXED — which agent owns this memory
  "scope": "string",             // INDEXED — "workspace", "agent", "execution"
  "memory_type": "string",       // INDEXED — "semantic", "episodic", "procedural"
  "content_preview": "string",   // first 200 chars of original content
  "freshness_score": 0.85,       // float 0-1, decays over time
  "authority_score": 0.9,        // float 0-1, confidence in accuracy
  "created_at": "ISO8601",       // timestamp for temporal filtering
  "execution_id": "uuid"         // correlation to originating execution
}
```

**Payload indexes**: `workspace_id` (keyword), `agent_id` (keyword), `scope` (keyword), `memory_type` (keyword), `freshness_score` (float)

---

### `pattern_embeddings`

Stores learned behavioral and reasoning patterns for pattern matching.

```json
{
  "workspace_id": "uuid",        // INDEXED — mandatory
  "pattern_type": "string",      // INDEXED — e.g., "reasoning", "behavioral", "correction"
  "promoted": false,             // INDEXED — whether pattern is promoted to workspace level
  "source_agent_fqn": "string",  // agent that originated the pattern
  "confidence": 0.87,            // float 0-1
  "use_count": 42,               // how many times this pattern was applied
  "created_at": "ISO8601"
}
```

**Payload indexes**: `workspace_id` (keyword), `pattern_type` (keyword), `promoted` (bool)

---

### `test_similarity`

Stores test case embeddings for semantic similarity scoring in evaluation suites.

```json
{
  "workspace_id": "uuid",        // INDEXED — mandatory
  "agent_id": "uuid",            // INDEXED — agent under test
  "test_suite_id": "uuid",       // INDEXED — which test suite this belongs to
  "test_case_id": "uuid",        // individual test case identifier
  "expected_behavior": "string", // description of expected behavior
  "category": "string",          // test category
  "severity": "string"           // "critical", "high", "medium", "low"
}
```

**Payload indexes**: `workspace_id` (keyword), `agent_id` (keyword), `test_suite_id` (keyword)

---

## Helm Values Schema

```yaml
# deploy/helm/qdrant/values.yaml (shared defaults)
replicaCount: 3                  # override to 1 in values-dev.yaml
config:
  cluster:
    enabled: true                # override to false in values-dev.yaml
    p2p:
      port: 6335
  service:
    api_key: ""                  # set from secret in deployment
  collection:
    vectors:
      on_disk: false
  storage:
    hnsw_index:
      m: 16
      ef_construct: 128
      full_scan_threshold: 10000
persistence:
  storageClassName: standard
  size: 50Gi
service:
  type: ClusterIP
  port: 6333
  grpcPort: 6334
resources:
  requests:
    memory: 2Gi
    cpu: "1"
collections:
  dimensions: 768              # configurable per deployment
  replicationFactor: 2         # override to 1 in values-dev.yaml
networkPolicy:
  enabled: true
backup:
  enabled: true
  schedule: "0 2 * * *"        # daily at 02:00 UTC
  bucket: "backups"
  prefix: "qdrant"
```

---

## Kubernetes Resources

### Production Resources

| Resource | Kind | Count |
|---------|------|-------|
| StatefulSet | `StatefulSet` | 1 (3 replicas) |
| PersistentVolumeClaims | `PVC` | 3 (one per pod) |
| `Secret` (API key) | `Secret` | 1 (`qdrant-api-key`) |
| Collection init `Job` | `Job` | 1 (post-install hook) |
| Backup `CronJob` | `CronJob` | 1 (daily) |
| `NetworkPolicy` | `NetworkPolicy` | 1 |

### Development Resources

| Resource | Kind | Count |
|---------|------|-------|
| StatefulSet | `StatefulSet` | 1 (1 replica) |
| PersistentVolumeClaims | `PVC` | 1 |
| `Secret` (API key) | `Secret` | 1 |
| Collection init `Job` | `Job` | 1 |

### Namespace: `platform-data`

All Qdrant infrastructure lives in `platform-data`.

### Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 6333 | HTTP | REST API + Prometheus metrics (`/metrics`) |
| 6334 | gRPC | High-throughput vector operations |
| 6335 | TCP | Qdrant cluster peer-to-peer (inter-node) |

### Service Reference

| Service Name | Port | Target |
|-------------|------|--------|
| `musematic-qdrant` | 6333, 6334 | REST + gRPC API |

---

## AsyncQdrantClient Interface

Located at: `apps/control-plane/src/platform/common/clients/qdrant.py`

```
AsyncQdrantClient
├── upsert_vectors(collection, points: list[PointStruct]) → None
├── search_vectors(collection, query_vector, filter, limit, with_payload) → list[ScoredPoint]
├── delete_vectors(collection, point_ids: list[str | int]) → None
├── get_collection_info(collection) → CollectionInfo
├── health_check() → dict[str, Any]
└── create_collection_if_not_exists(collection, config) → bool

PointStruct:
├── id: str | int          # unique point ID (UUID string recommended)
├── vector: list[float]    # embedding vector (dimension must match collection)
└── payload: dict          # arbitrary metadata (workspace_id, agent_id, etc.)

ScoredPoint:
├── id: str | int
├── score: float           # similarity score (0-1 for cosine)
├── payload: dict
└── version: int
```
