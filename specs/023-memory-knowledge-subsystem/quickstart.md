# Quickstart: Memory and Knowledge Subsystem

**Feature**: 023-memory-knowledge-subsystem  
**Date**: 2026-04-11

---

## Prerequisites

All services must be running before starting the control plane:

```bash
# Verify required infrastructure
docker ps | grep -E "postgres|qdrant|neo4j|redis|kafka"

# Or via kubectl (Kubernetes)
kubectl get pods -n platform-data | grep -E "postgres|qdrant|neo4j|redis"
kubectl get pods -n platform-kafka
```

Required services: PostgreSQL, Qdrant, Neo4j, Redis, Kafka.

---

## Run Migrations

```bash
cd apps/control-plane

# Apply migration 008 (memory and knowledge tables)
alembic upgrade head

# Verify
alembic current
# Expected: 008_memory_knowledge (head)
```

---

## Environment Variables

Add to your `.env` or Kubernetes ConfigMap:

```bash
# Memory subsystem
MEMORY_EMBEDDING_DIMENSIONS=1536
MEMORY_EMBEDDING_API_URL=https://api.openai.com/v1/embeddings
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_RATE_LIMIT_PER_MIN=60
MEMORY_RATE_LIMIT_PER_HOUR=500
MEMORY_CONTRADICTION_SIMILARITY_THRESHOLD=0.90
MEMORY_CONTRADICTION_EDIT_DISTANCE_THRESHOLD=0.15
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_CONSOLIDATION_INTERVAL_MINUTES=15
MEMORY_CONSOLIDATION_CLUSTER_THRESHOLD=0.85
MEMORY_CONSOLIDATION_LLM_ENABLED=false
MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE=3
MEMORY_DIFFERENTIAL_PRIVACY_ENABLED=false
MEMORY_DIFFERENTIAL_PRIVACY_EPSILON=1.0
MEMORY_RRF_K=60
MEMORY_SESSION_CLEANER_INTERVAL_MINUTES=60

# Neo4j (already set from feature 006, verify these are set)
NEO4J_URI=bolt://neo4j-service:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secret>
```

---

## Start the API (Development)

```bash
cd apps/control-plane

# API profile (includes memory router + setup_memory_collections startup)
uvicorn src.platform.entrypoints.api_main:app --host 0.0.0.0 --port 8000 --reload

# Worker profile (includes ConsolidationWorker + EmbeddingWorker APScheduler tasks)
uvicorn src.platform.entrypoints.worker_main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Verify Startup

```bash
# Check memory collection exists in Qdrant
curl http://localhost:6333/collections/platform_memory
# Expected: {"result":{"status":"green",...}}

# Check Neo4j indexes
cypher-shell -u neo4j -p <password> "SHOW INDEXES YIELD name, labelsOrTypes WHERE labelsOrTypes = ['MemoryNode']"
# Expected: node_workspace, node_unique constraints

# Check API health
curl http://localhost:8000/health
```

---

## Smoke Test

```bash
# 1. Write a per-agent memory
curl -X POST http://localhost:8000/api/v1/memory/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Customer ACME Corp prefers invoice terms NET-30.",
    "scope": "per_agent",
    "namespace": "finance-ops",
    "source_authority": 0.9,
    "retention_policy": "permanent",
    "tags": ["customer", "payment"]
  }'
# Expected: 201, WriteGateResult with memory_entry_id

# 2. Retrieve with hybrid search
curl -X POST http://localhost:8000/api/v1/memory/retrieve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "What are ACME payment preferences?",
    "top_k": 5
  }'
# Expected: 200, results list with the written memory

# 3. Write a contradiction
curl -X POST http://localhost:8000/api/v1/memory/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Customer ACME Corp prefers invoice terms NET-60.",
    "scope": "per_agent",
    "namespace": "finance-ops",
    "source_authority": 0.7,
    "tags": ["customer", "payment"]
  }'
# Expected: 201, but contradiction_detected: true, conflict_id set

# 4. List open conflicts
curl http://localhost:8000/api/v1/memory/conflicts?status=open \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200, list with the conflict above

# 5. Create knowledge graph node
curl -X POST http://localhost:8000/api/v1/memory/graph/nodes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "node_type": "Organization",
    "external_name": "ACME Corp",
    "attributes": {"industry": "manufacturing"}
  }'
# Expected: 201, KnowledgeNodeResponse
```

---

## Run Tests

```bash
cd apps/control-plane

# Unit tests only (fast, no external services)
pytest tests/unit/ -k "memory" -v

# Integration tests (requires PostgreSQL, Qdrant, Neo4j, Redis, Kafka)
pytest tests/integration/ -k "memory" -v

# Full suite with coverage
pytest tests/ -k "memory" --cov=src/platform/memory --cov-report=term-missing
# Expected: ≥ 95% coverage
```

---

## APScheduler Worker Tasks

The `worker_main.py` profile registers two memory tasks:

| Task | Interval | Description |
|---|---|---|
| `EmbeddingWorker.run` | Every 30 seconds | Processes pending `EmbeddingJob` records, generates embeddings, upserts to Qdrant |
| `ConsolidationWorker.run` | Every 15 minutes | Clusters similar agent-scoped memories, distills, promotes to workspace scope |
| `SessionMemoryCleaner.run` | Every 60 minutes | Deletes `session_only` memories where `ttl_expires_at < now()` |

Verify worker is running:
```bash
# Kubernetes
kubectl logs -n platform-control deployment/control-plane-worker | grep -E "memory|embedding|consolidation"
```

---

## Linting and Type Checking

```bash
cd apps/control-plane

# Ruff
ruff check src/platform/memory/ --fix

# Mypy strict
mypy src/platform/memory/ --strict
# Expected: 0 errors
```
