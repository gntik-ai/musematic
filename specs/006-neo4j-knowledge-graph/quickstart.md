# Quickstart: Neo4j Knowledge Graph

**Feature**: 006-neo4j-knowledge-graph  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x with Neo4j repo added:
  ```bash
  helm repo add neo4j https://helm.neo4j.com/neo4j
  helm repo update
  ```
- Python 3.12+ with `neo4j` driver installed:
  ```bash
  pip install "neo4j>=5.0"
  ```
- Install the control-plane package before running Python tests:
  ```bash
  pip install -e ./apps/control-plane
  ```
- Object storage (feature 004) deployed — required for backup CronJob

---

## 1. Deploy Neo4j Cluster (Production)

```bash
helm install musematic-neo4j deploy/helm/neo4j \
  -n platform-data \
  -f deploy/helm/neo4j/values.yaml \
  -f deploy/helm/neo4j/values-prod.yaml \
  --create-namespace

# Wait for all 3 pods to be ready
kubectl rollout status statefulset/musematic-neo4j -n platform-data --timeout=300s

# Verify cluster formation (1 leader + 2 followers)
kubectl port-forward svc/musematic-neo4j 7474:7474 -n platform-data &
curl -s http://localhost:7474/db/neo4j/cluster/available
# Expected: {"available": true, "role": "LEADER" or "FOLLOWER"}
```

---

## 2. Deploy Neo4j (Development)

```bash
helm install musematic-neo4j deploy/helm/neo4j \
  -n platform-data \
  -f deploy/helm/neo4j/values.yaml \
  -f deploy/helm/neo4j/values-dev.yaml \
  --create-namespace

kubectl rollout status statefulset/musematic-neo4j -n platform-data --timeout=120s
```

---

## 3. Verify Schema Initialization

The schema init Job runs automatically as a Helm post-install hook. Verify it completed:

```bash
kubectl get jobs -n platform-data -l app=neo4j-schema-init
# Expected: COMPLETIONS 1/1

# Check all constraints and indexes
kubectl port-forward svc/musematic-neo4j 7687:7687 -n platform-data &
NEO4J_PASSWORD=$(kubectl get secret neo4j-credentials -n platform-data \
  -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d)

cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a bolt://localhost:7687 \
  "SHOW CONSTRAINTS;"
# Expected: 5 constraints — agent_id, workflow_id, fleet_id, hypothesis_id, memory_id

cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a bolt://localhost:7687 \
  "SHOW INDEXES;"
# Expected: indexes include memory_workspace, evidence_hypothesis, relationship_type
```

---

## 4. Run Schema Init Manually (Idempotent)

```bash
# Re-run schema init — safe to repeat, IF NOT EXISTS prevents duplicates
kubectl create job --from=cronjob/neo4j-schema-init manual-schema-init -n platform-data
kubectl wait --for=condition=complete job/manual-schema-init -n platform-data --timeout=120s
```

---

## 5. Test Basic Graph Operations

```python
import asyncio
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.config import Settings

settings = Settings(
    NEO4J_URL="bolt://neo4j:password@localhost:7687",
)

async def main():
    client = AsyncNeo4jClient(settings)

    # Create agent nodes
    await client.create_node("Agent", {
        "id": "agent-qs-001",
        "workspace_id": "ws-quickstart",
        "fqn": "qs:research-agent",
        "lifecycle_state": "published",
    })
    await client.create_node("Workflow", {
        "id": "wf-qs-001",
        "workspace_id": "ws-quickstart",
        "name": "research-pipeline",
        "status": "active",
    })

    # Create relationship
    await client.create_relationship(
        from_id="wf-qs-001",
        to_id="agent-qs-001",
        rel_type="DEPENDS_ON",
        properties={"weight": 1.0},
    )

    # Traverse 1 hop from workflow
    paths = await client.traverse_path(
        start_id="wf-qs-001",
        rel_types=["DEPENDS_ON"],
        max_hops=1,
        workspace_id="ws-quickstart",
    )
    print(f"Found {len(paths)} path(s)")
    assert len(paths) >= 1, "Expected at least one path"
    print(f"Path length: {paths[0].length}")

    # Health check
    health = await client.health_check()
    print(f"Health: {health}")
    assert health["status"] == "ok"
    assert health["mode"] == "neo4j"

    await client.close()

asyncio.run(main())
```

---

## 6. Test Workspace Isolation

```python
async def test_workspace_isolation(client):
    # Create nodes in two different workspaces
    await client.create_node("Agent", {
        "id": "agent-ws-a",
        "workspace_id": "ws-A",
        "fqn": "a:agent",
        "lifecycle_state": "published",
    })
    await client.create_node("Agent", {
        "id": "agent-ws-b",
        "workspace_id": "ws-B",
        "fqn": "b:agent",
        "lifecycle_state": "published",
    })

    # Query workspace-A — should only return workspace-A nodes
    results = await client.run_query(
        "MATCH (a:Agent) WHERE a.workspace_id = $workspace_id RETURN a",
        workspace_id="ws-A",
    )
    assert all(r["a"]["workspace_id"] == "ws-A" for r in results)
    assert not any(r["a"]["workspace_id"] == "ws-B" for r in results)
    print(f"Workspace isolation: PASS — {len(results)} agents in ws-A, none from ws-B")
```

---

## 7. Test 3-Hop Traversal

```python
async def test_three_hop_traversal(client):
    # Create a chain: Hypothesis → Evidence → Evidence → Source
    await client.create_node("Hypothesis", {
        "id": "h-001", "workspace_id": "ws-qs", "status": "open", "confidence": 0.8,
    })
    await client.create_node("Evidence", {
        "id": "ev-001", "workspace_id": "ws-qs", "hypothesis_id": "h-001",
        "polarity": "supporting", "confidence": 0.9,
    })
    await client.create_node("Evidence", {
        "id": "ev-002", "workspace_id": "ws-qs", "hypothesis_id": "h-001",
        "polarity": "supporting", "confidence": 0.7,
    })
    await client.create_relationship("h-001", "ev-001", "SUPPORTS", {"confidence": 0.9})
    await client.create_relationship("ev-001", "ev-002", "DERIVED_FROM", {})

    paths = await client.traverse_path(
        start_id="h-001",
        rel_types=["SUPPORTS", "DERIVED_FROM"],
        max_hops=3,
        workspace_id="ws-qs",
    )
    print(f"3-hop traversal: found {len(paths)} paths")
    assert any(p.length >= 2 for p in paths), "Expected paths of at least 2 hops"
```

---

## 8. Test APOC (Advanced Algorithms)

```python
async def test_apoc_shortest_path(client):
    # Build a graph with two paths between agent-A and agent-C
    await client.create_node("Agent", {"id": "a", "workspace_id": "ws-qs", "fqn": "qs:a", "lifecycle_state": "published"})
    await client.create_node("Agent", {"id": "b", "workspace_id": "ws-qs", "fqn": "qs:b", "lifecycle_state": "published"})
    await client.create_node("Agent", {"id": "c", "workspace_id": "ws-qs", "fqn": "qs:c", "lifecycle_state": "published"})
    await client.create_relationship("a", "b", "COORDINATES", {"protocol": "direct"})
    await client.create_relationship("b", "c", "COORDINATES", {"protocol": "direct"})
    await client.create_relationship("a", "c", "COORDINATES", {"protocol": "direct"})

    path = await client.shortest_path(from_id="a", to_id="c", rel_types=["COORDINATES"])
    assert path is not None
    assert path.length == 1, f"Expected shortest path of 1 hop (direct), got {path.length}"
    print(f"Shortest path: {path.length} hop(s) — PASS")

    # Verify APOC is available
    results = await client.run_query("CALL apoc.help('path') YIELD name RETURN name LIMIT 1")
    assert len(results) > 0, "APOC not available"
    print(f"APOC available: {results[0]['name']}")
```

---

## 9. Test Backup

```bash
# Port-forward and get credentials
NEO4J_PASSWORD=$(kubectl get secret neo4j-credentials -n platform-data \
  -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d)

# Trigger manual backup job
kubectl create job --from=cronjob/neo4j-backup manual-backup -n platform-data
kubectl wait --for=condition=complete job/manual-backup -n platform-data --timeout=1200s

# Verify dump uploaded to object storage
mc ls local/backups/neo4j/
# Expected: directory with neo4j.dump file dated today
```

---

## 10. Test Restore from Dump

```bash
# WARNING: Restoring overwrites current database data

NEO4J_PASSWORD=$(kubectl get secret neo4j-credentials -n platform-data \
  -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d)

# 1. Download dump from object storage
mc cp local/backups/neo4j/2026-04-09/neo4j.dump /tmp/neo4j.dump

# 2. Copy dump into the Neo4j pod
kubectl cp /tmp/neo4j.dump platform-data/musematic-neo4j-0:/dumps/neo4j.dump

# 3. Stop Neo4j, load dump, restart
kubectl exec -it musematic-neo4j-0 -n platform-data -- neo4j stop
kubectl exec -it musematic-neo4j-0 -n platform-data -- \
  neo4j-admin database load --from-path=/dumps/ --database=neo4j --overwrite-destination=true
kubectl exec -it musematic-neo4j-0 -n platform-data -- neo4j start

# 4. Verify recovery
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a bolt://localhost:7687 \
  "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label;"
# Expected: restored node counts
```

---

## 11. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-neo4j --image=neo4j:5 --restart=Never -- \
  cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  -a bolt://musematic-neo4j.platform-data:7687 "RETURN 1 AS ok;"
# Expected: ╒════╕ │ ok │ ╞════╡ │ 1  │

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-neo4j-deny --image=neo4j:5 --restart=Never -- \
  cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  -a bolt://musematic-neo4j.platform-data:7687 "RETURN 1;" || echo "Connection blocked (expected)"
```

---

## 12. Verify Prometheus Metrics

```bash
kubectl port-forward svc/musematic-neo4j 7474:7474 -n platform-data &
curl -s http://localhost:7474/metrics | \
  grep -E "neo4j_database_transaction_active|neo4j_database_query_execution_latency|neo4j_causal_clustering_role"
# Expected: metric lines present
```

---

## 13. Test Local Mode Fallback

```python
import asyncio
from platform.common.clients.neo4j import AsyncNeo4jClient, HopLimitExceededError
from platform.common.config import Settings

# Local mode: NEO4J_URL not set
settings = Settings()  # NEO4J_URL=None → local mode

async def test_local_mode():
    client = AsyncNeo4jClient(settings)

    health = await client.health_check()
    assert health["mode"] == "local"
    print(f"Mode: {health['mode']} — PASS")

    # 3-hop traversal should work
    paths = await client.traverse_path(
        start_id="some-id",
        rel_types=["DEPENDS_ON"],
        max_hops=3,
        workspace_id="ws-test",
    )
    print(f"Local 3-hop traversal returned {len(paths)} paths")

    # 4-hop traversal should raise
    try:
        await client.traverse_path("some-id", ["DEPENDS_ON"], 4, "ws-test")
        assert False, "Expected HopLimitExceededError"
    except HopLimitExceededError as e:
        print(f"HopLimitExceededError raised as expected: {e}")

asyncio.run(test_local_mode())
```

---

## 14. Run Neo4j Integration Tests

```bash
# Requires Docker (testcontainers) or running Neo4j
export NEO4J_TEST_MODE=testcontainers
python -m pytest apps/control-plane/tests/integration/test_neo4j*.py -v
```
