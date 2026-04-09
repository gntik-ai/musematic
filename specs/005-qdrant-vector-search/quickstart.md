# Quickstart: Qdrant Vector Search

**Feature**: 005-qdrant-vector-search  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x with Qdrant repo added:
  ```bash
  helm repo add qdrant https://qdrant.github.io/qdrant-helm
  helm repo update
  ```
- Python 3.12+ with `qdrant-client[grpc]>=1.12` installed:
  ```bash
  pip install "qdrant-client[grpc]>=1.12"
  ```
- Install the control-plane package before running Python tests:
  ```bash
  pip install -e ./apps/control-plane
  ```
- Object storage (feature 004) deployed — required for backup CronJob

---

## 1. Deploy Qdrant Cluster (Production)

```bash
helm install musematic-qdrant deploy/helm/qdrant \
  -n platform-data \
  -f deploy/helm/qdrant/values.yaml \
  -f deploy/helm/qdrant/values-prod.yaml \
  --create-namespace

# Wait for all 3 replicas to be ready
kubectl rollout status statefulset/musematic-qdrant -n platform-data --timeout=300s

# Verify cluster health
kubectl port-forward svc/musematic-qdrant 6333:6333 -n platform-data &
API_KEY=$(kubectl get secret qdrant-api-key -n platform-data -o jsonpath='{.data.QDRANT_API_KEY}' | base64 -d)
curl -s http://localhost:6333/cluster -H "Authorization: api-key $API_KEY" | python3 -m json.tool
# Expected: {"status": "ok", "result": {"status": "enabled", "peer_count": 3}}
```

---

## 2. Deploy Qdrant (Development)

```bash
helm install musematic-qdrant deploy/helm/qdrant \
  -n platform-data \
  -f deploy/helm/qdrant/values.yaml \
  -f deploy/helm/qdrant/values-dev.yaml \
  --create-namespace

kubectl rollout status statefulset/musematic-qdrant -n platform-data --timeout=60s
```

---

## 3. Initialize Collections

```bash
# Run the collection init script (idempotent — safe to re-run)
kubectl port-forward svc/musematic-qdrant 6333:6333 6334:6334 -n platform-data &

API_KEY=$(kubectl get secret qdrant-api-key -n platform-data -o jsonpath='{.data.QDRANT_API_KEY}' | base64 -d)

QDRANT_URL=http://localhost:6333 QDRANT_API_KEY=$API_KEY \
  python3 apps/control-plane/scripts/init_qdrant_collections.py

# Verify all 4 collections exist
curl -s http://localhost:6333/collections -H "Authorization: api-key $API_KEY" | \
  python3 -c "import json,sys; data=json.load(sys.stdin); print([c['name'] for c in data['result']['collections']])"
# Expected: ['agent_embeddings', 'memory_embeddings', 'pattern_embeddings', 'test_similarity']
```

---

## 4. Test Basic Vector Operations

```python
import asyncio
import random
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct, workspace_filter
from platform.common.config import Settings

settings = Settings(
    QDRANT_URL="http://localhost:6333",
    QDRANT_API_KEY="<api-key>",
    QDRANT_GRPC_PORT=6334,
    QDRANT_COLLECTION_DIMENSIONS=768,
)

async def main():
    client = AsyncQdrantClient(settings)

    # Upsert a vector
    vec = [random.random() for _ in range(768)]
    await client.upsert_vectors("agent_embeddings", [
        PointStruct(
            id="agent-test-001",
            vector=vec,
            payload={
                "workspace_id": "ws-quickstart",
                "agent_id": "agent-test-001",
                "lifecycle_state": "published",
                "maturity_level": 3,
                "tags": ["test"],
            }
        )
    ])
    print("Upserted agent-test-001")

    # Search with workspace filter (mandatory)
    results = await client.search_vectors(
        "agent_embeddings",
        query_vector=vec,  # same vector — should be score=1.0
        filter=workspace_filter("ws-quickstart"),
        limit=1,
    )
    print(f"Top result: {results[0].id} score={results[0].score:.4f}")
    assert results[0].score > 0.9999, "Expected near-perfect score for same vector"

    # Workspace isolation — different workspace returns nothing
    results_other = await client.search_vectors(
        "agent_embeddings",
        query_vector=vec,
        filter=workspace_filter("ws-other"),
        limit=1,
    )
    print(f"Other workspace results: {len(results_other)} (expected 0)")

    # Health check
    health = await client.health_check()
    print(f"Health: {health}")

asyncio.run(main())
```

---

## 5. Test Filtered Search

```python
async def test_filtered_search(client):
    # Upsert agents across two workspaces with different lifecycle states
    vectors = []
    for i in range(10):
        vec = [random.random() for _ in range(768)]
        vectors.append(PointStruct(
            id=f"agent-{i:03d}",
            vector=vec,
            payload={
                "workspace_id": "ws-A" if i < 5 else "ws-B",
                "agent_id": f"agent-{i:03d}",
                "lifecycle_state": "published" if i % 2 == 0 else "draft",
                "maturity_level": i % 5 + 1,
                "tags": [],
            }
        ))
    await client.upsert_vectors("agent_embeddings", vectors)

    # Filter by workspace AND lifecycle_state
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    results = await client.search_vectors(
        "agent_embeddings",
        query_vector=[random.random() for _ in range(768)],
        filter=workspace_filter(
            "ws-A",
            extra=Filter(must=[FieldCondition(key="lifecycle_state", match=MatchValue(value="published"))])
        ),
        limit=5,
    )
    # All results must be from ws-A and be published
    for r in results:
        assert r.payload["workspace_id"] == "ws-A"
        assert r.payload["lifecycle_state"] == "published"
    print(f"Compound filter returned {len(results)} results — all pass assertion")
```

---

## 6. Test Backup

```bash
# Port-forward and set API key
API_KEY=$(kubectl get secret qdrant-api-key -n platform-data -o jsonpath='{.data.QDRANT_API_KEY}' | base64 -d)

# Trigger snapshot of agent_embeddings
SNAPSHOT=$(curl -s -X POST http://localhost:6333/collections/agent_embeddings/snapshots \
  -H "Authorization: api-key $API_KEY" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])")
echo "Created snapshot: $SNAPSHOT"

# Run backup script manually (uploads to MinIO)
QDRANT_URL=http://localhost:6333 QDRANT_API_KEY=$API_KEY \
MINIO_ENDPOINT=http://musematic-minio.platform-data:9000 \
MINIO_ACCESS_KEY=platform \
  python3 apps/control-plane/scripts/backup_qdrant_snapshots.py

# Verify in object storage
mc ls local/backups/qdrant/
# Expected: snapshot files per collection
```

---

## 7. Test Restore from Snapshot

```bash
# List available snapshots
SNAPSHOT_NAME=$(curl -s http://localhost:6333/collections/agent_embeddings/snapshots \
  -H "Authorization: api-key $API_KEY" | python3 -c "
import json, sys
snaps = json.load(sys.stdin)['result']
print(snaps[-1]['name']) if snaps else print('no snapshots')")

# Restore (WARNING: overwrites current data)
curl -X PUT "http://localhost:6333/collections/agent_embeddings/snapshots/recover" \
  -H "Authorization: api-key $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"location\": \"http://localhost:6333/collections/agent_embeddings/snapshots/$SNAPSHOT_NAME\"}"
# Expected: {"status": "ok"}
```

---

## 8. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-qdrant --image=curlimages/curl:latest --restart=Never -- \
  curl -s http://musematic-qdrant.platform-data:6333/health -H "Authorization: api-key $API_KEY"

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-qdrant --image=curlimages/curl:latest --restart=Never -- \
  curl --connect-timeout 5 http://musematic-qdrant.platform-data:6333/health
# Expected: connection refused or timeout
```

---

## 9. Verify Prometheus Metrics

```bash
curl -s http://localhost:6333/metrics -H "Authorization: api-key $API_KEY" | \
  grep "qdrant_collections_total\|qdrant_grpc_requests_total\|qdrant_rest_requests_total"
# Expected: metric lines for collection count and request counts
```

---

## 10. Verify Authentication

```bash
curl -i http://localhost:6333/collections
# Expected: HTTP 401 or 403

curl -i http://localhost:6333/collections \
  -H "Authorization: api-key wrong-key"
# Expected: HTTP 401 or 403

curl -i http://localhost:6333/collections \
  -H "Authorization: api-key $API_KEY"
# Expected: HTTP 200
```

---

## 11. Run Qdrant Integration Tests Locally

```bash
# Requires Docker (testcontainers or local Qdrant)
export QDRANT_TEST_MODE=testcontainers
python -m pytest apps/control-plane/tests/integration/test_qdrant*.py -v
```
