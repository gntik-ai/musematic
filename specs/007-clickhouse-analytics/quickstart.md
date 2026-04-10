# Quickstart: ClickHouse Analytics

**Feature**: 007-clickhouse-analytics  
**Date**: 2026-04-10

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x installed
- Python 3.12+ with `clickhouse-connect>=0.8` installed:
  ```bash
  pip install "clickhouse-connect>=0.8"
  ```
- Install the control-plane package before running Python tests:
  ```bash
  pip install -e ./apps/control-plane
  ```
- Object storage (feature 004) deployed — required for backup CronJob

---

## 1. Deploy ClickHouse Cluster (Production)

```bash
helm install musematic-clickhouse deploy/helm/clickhouse \
  -n platform-data \
  -f deploy/helm/clickhouse/values.yaml \
  -f deploy/helm/clickhouse/values-prod.yaml \
  --create-namespace

# Wait for Keeper (consensus) to be ready first
kubectl rollout status statefulset/musematic-clickhouse-keeper -n platform-data --timeout=120s

# Wait for ClickHouse server replicas
kubectl rollout status statefulset/musematic-clickhouse -n platform-data --timeout=300s

# Verify cluster health
kubectl port-forward svc/musematic-clickhouse 8123:8123 -n platform-data &
CLICKHOUSE_PASSWORD=$(kubectl get secret clickhouse-credentials -n platform-data \
  -o jsonpath='{.data.CLICKHOUSE_PASSWORD}' | base64 -d)

curl -s "http://localhost:8123/ping"
# Expected: Ok.

curl -s "http://localhost:8123/?query=SELECT+count()+FROM+system.clusters" \
  --user "default:$CLICKHOUSE_PASSWORD"
# Expected: number of cluster entries (2 for 2 replicas)
```

---

## 2. Deploy ClickHouse (Development)

```bash
helm install musematic-clickhouse deploy/helm/clickhouse \
  -n platform-data \
  -f deploy/helm/clickhouse/values.yaml \
  -f deploy/helm/clickhouse/values-dev.yaml \
  --create-namespace

kubectl rollout status statefulset/musematic-clickhouse -n platform-data --timeout=120s
```

---

## 3. Verify Schema Initialization

The schema init Job runs automatically as a Helm post-install hook.

```bash
kubectl get jobs -n platform-data -l app=clickhouse-schema-init
# Expected: COMPLETIONS 1/1

kubectl port-forward svc/musematic-clickhouse 8123:8123 -n platform-data &
CLICKHOUSE_PASSWORD=$(kubectl get secret clickhouse-credentials -n platform-data \
  -o jsonpath='{.data.CLICKHOUSE_PASSWORD}' | base64 -d)

# Verify all tables exist
curl -s "http://localhost:8123/?query=SHOW+TABLES" \
  --user "default:$CLICKHOUSE_PASSWORD"
# Expected: behavioral_drift, fleet_performance, self_correction_analytics,
#           usage_events, usage_hourly, usage_hourly_mv

# Verify partitioning on usage_events
curl -s "http://localhost:8123/" --user "default:$CLICKHOUSE_PASSWORD" \
  -d "SELECT partition_key, sorting_key FROM system.tables WHERE name = 'usage_events'"
# Expected: toYYYYMM(event_time) | workspace_id, event_time, agent_id
```

---

## 4. Test Basic Insert and Query

```python
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import Settings

settings = Settings(
    CLICKHOUSE_URL="http://localhost:8123",
    CLICKHOUSE_PASSWORD="<password>",
)

async def main():
    client = AsyncClickHouseClient(settings)

    # Insert a usage event
    await client.insert_batch(
        table="usage_events",
        column_names=[
            "event_id", "workspace_id", "user_id", "agent_id",
            "provider", "model", "input_tokens", "output_tokens",
            "estimated_cost", "event_time",
        ],
        data=[{
            "event_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_tokens": 1500,
            "output_tokens": 800,
            "estimated_cost": 0.0045,
            "event_time": datetime.now(timezone.utc),
        }],
    )
    print("Inserted 1 usage event")

    # Query it back
    rows = await client.execute_query(
        "SELECT provider, model, input_tokens FROM usage_events LIMIT 1"
    )
    print(f"Query result: {rows[0]}")

    # Health check
    health = await client.health_check()
    print(f"Health: {health}")

    await client.close()

asyncio.run(main())
```

---

## 5. Test Workspace Isolation

```python
async def test_workspace_isolation(client):
    ws_a = str(uuid4())
    ws_b = str(uuid4())

    # Insert events for two workspaces
    events = []
    for i in range(10):
        events.append({
            "event_id": str(uuid4()),
            "workspace_id": ws_a if i < 5 else ws_b,
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_tokens": 100 * (i + 1),
            "output_tokens": 50 * (i + 1),
            "estimated_cost": 0.001 * (i + 1),
            "event_time": datetime.now(timezone.utc),
        })

    await client.insert_batch(
        "usage_events",
        [
            "event_id", "workspace_id", "user_id", "agent_id",
            "provider", "model", "input_tokens", "output_tokens",
            "estimated_cost", "event_time",
        ],
        events,
    )

    # Query workspace A only
    rows = await client.execute_query(
        "SELECT count() AS cnt FROM usage_events WHERE workspace_id = {ws:UUID}",
        params={"ws": ws_a},
    )
    assert rows[0]["cnt"] == 5, f"Expected 5 events in ws-A, got {rows[0]['cnt']}"
    print(f"Workspace isolation: PASS — {rows[0]['cnt']} events in ws-A")
```

---

## 6. Test Materialized View Rollup

```python
async def test_materialized_view(client):
    ws = str(uuid4())
    agent = str(uuid4())

    # Insert 100 events for the same workspace/agent/hour
    events = []
    for i in range(100):
        events.append({
            "event_id": str(uuid4()),
            "workspace_id": ws,
            "user_id": str(uuid4()),
            "agent_id": agent,
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_cost": 0.001,
            "event_time": datetime(2026, 4, 10, 14, 30, 0),
        })

    await client.insert_batch("usage_events", [...column_names...], events)

    # Check rollup
    rows = await client.execute_query(
        "SELECT total_input_tokens, total_output_tokens, event_count "
        "FROM usage_hourly "
        "WHERE workspace_id = {ws:UUID} AND agent_id = {agent:UUID}",
        params={"ws": ws, "agent": agent},
    )
    assert rows[0]["total_input_tokens"] == 10000  # 100 * 100
    assert rows[0]["event_count"] == 100
    print(f"Materialized view rollup: PASS — {rows[0]['event_count']} events aggregated")
```

---

## 7. Test Partition Pruning

```bash
CLICKHOUSE_PASSWORD=$(kubectl get secret clickhouse-credentials -n platform-data \
  -o jsonpath='{.data.CLICKHOUSE_PASSWORD}' | base64 -d)

# Query with time filter — should show partition pruning in EXPLAIN
curl -s "http://localhost:8123/" --user "default:$CLICKHOUSE_PASSWORD" -d "
EXPLAIN PLAN
SELECT sum(input_tokens) FROM usage_events
WHERE event_time >= '2026-04-01' AND event_time < '2026-05-01'
AND workspace_id = '00000000-0000-0000-0000-000000000000'
"
# Expected: output includes "Parts: X/Y" showing partition pruning (X < Y)
```

---

## 8. Test Backup

```bash
CLICKHOUSE_PASSWORD=$(kubectl get secret clickhouse-credentials -n platform-data \
  -o jsonpath='{.data.CLICKHOUSE_PASSWORD}' | base64 -d)

# Trigger manual backup
kubectl create job --from=cronjob/clickhouse-backup manual-backup -n platform-data
kubectl wait --for=condition=complete job/manual-backup -n platform-data --timeout=1800s

# Verify in object storage
mc ls local/backups/clickhouse/
# Expected: directory with today's date containing backup files
```

---

## 9. Test Restore from Backup

```bash
# WARNING: Restoring overwrites current data

# 1. List available backups
kubectl exec -it musematic-clickhouse-0 -n platform-data -c clickhouse-backup -- \
  clickhouse-backup list remote

# 2. Restore from backup (specify backup name from list above)
kubectl exec -it musematic-clickhouse-0 -n platform-data -c clickhouse-backup -- \
  clickhouse-backup restore_remote <backup-name>

# 3. Verify recovery
curl -s "http://localhost:8123/" --user "default:$CLICKHOUSE_PASSWORD" \
  -d "SELECT count() FROM usage_events"
# Expected: restored row count
```

---

## 10. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-ch --image=curlimages/curl:latest --restart=Never -- \
  curl -s "http://musematic-clickhouse.platform-data:8123/ping"
# Expected: Ok.

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-ch-deny --image=curlimages/curl:latest --restart=Never -- \
  curl --connect-timeout 5 "http://musematic-clickhouse.platform-data:8123/ping"
# Expected: connection refused or timeout
```

---

## 11. Verify Prometheus Metrics

```bash
curl -s "http://localhost:8123/metrics" --user "default:$CLICKHOUSE_PASSWORD" | \
  grep -E "ClickHouseMetrics_Query|ClickHouseMetrics_Merge|ClickHouseProfileEvents_InsertedRows"
# Expected: metric lines present
```

---

## 12. Verify Authentication

```bash
# Without auth (should fail)
curl -i "http://localhost:8123/?query=SELECT+1"
# Expected: HTTP 401 or authentication error

# With wrong password (should fail)
curl -i "http://localhost:8123/?query=SELECT+1" --user "default:wrong-password"
# Expected: HTTP 403 or authentication error

# With correct password (should succeed)
curl -i "http://localhost:8123/?query=SELECT+1" --user "default:$CLICKHOUSE_PASSWORD"
# Expected: HTTP 200, body: 1
```

---

## 13. Test BatchBuffer

```python
async def test_batch_buffer(client):
    from platform.common.clients.clickhouse import BatchBuffer

    buffer = BatchBuffer(
        client=client,
        table="usage_events",
        column_names=[
            "event_id", "workspace_id", "user_id", "agent_id",
            "provider", "model", "input_tokens", "output_tokens",
            "estimated_cost", "event_time",
        ],
        max_size=50,           # flush every 50 events for testing
        flush_interval=1.0,    # flush every 1 second for testing
    )
    await buffer.start()

    # Add 120 events — should trigger 2 auto-flushes (at 50 and 100)
    for i in range(120):
        await buffer.add({
            "event_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_cost": 0.001,
            "event_time": datetime.now(timezone.utc),
        })

    await buffer.stop()  # flushes remaining 20

    rows = await client.execute_query("SELECT count() AS cnt FROM usage_events")
    print(f"BatchBuffer: inserted {rows[0]['cnt']} rows total")
```

---

## 14. Run ClickHouse Integration Tests

```bash
# Requires Docker (testcontainers) or running ClickHouse
export CLICKHOUSE_TEST_MODE=testcontainers
python -m pytest apps/control-plane/tests/integration/test_clickhouse*.py -v
```
