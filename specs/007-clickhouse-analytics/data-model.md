# Data Model: ClickHouse Analytics

**Feature**: 007-clickhouse-analytics  
**Date**: 2026-04-10

---

## Table Registry

All analytics tables provisioned by this feature.

| Table | Engine (Prod) | Engine (Dev) | Partition Key | Order By | TTL |
|-------|--------------|-------------|---------------|----------|-----|
| `usage_events` | ReplicatedMergeTree | MergeTree | `toYYYYMM(event_time)` | `(workspace_id, event_time, agent_id)` | 365 days |
| `behavioral_drift` | ReplicatedMergeTree | MergeTree | `toYYYYMM(measured_at)` | `(agent_id, metric_name, measured_at)` | 180 days |
| `fleet_performance` | ReplicatedMergeTree | MergeTree | `toYYYYMM(measured_at)` | `(fleet_id, metric_name, measured_at)` | None |
| `self_correction_analytics` | ReplicatedMergeTree | MergeTree | `toYYYYMM(completed_at)` | `(agent_id, completed_at)` | None |
| `usage_hourly` | ReplicatedSummingMergeTree | SummingMergeTree | `toYYYYMM(hour)` | `(workspace_id, agent_id, provider, model, hour)` | None |

---

## Table Schemas

### `usage_events`

Raw usage/consumption events from platform services.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | `UUID` | Unique event identifier |
| `workspace_id` | `UUID` | Tenant scoping — part of ORDER BY |
| `user_id` | `UUID` | Triggering user |
| `agent_id` | `UUID` | Executing agent — part of ORDER BY |
| `workflow_id` | `Nullable(UUID)` | Workflow context (if applicable) |
| `execution_id` | `Nullable(UUID)` | Execution context (if applicable) |
| `provider` | `String` | Model provider (e.g., `anthropic`, `openai`) |
| `model` | `String` | Model name (e.g., `claude-sonnet-4-6`) |
| `input_tokens` | `UInt32` | Input token count |
| `output_tokens` | `UInt32` | Output token count |
| `reasoning_tokens` | `UInt32` | Reasoning/thinking token count (default 0) |
| `cached_tokens` | `UInt32` | Cached/prompt-cache token count (default 0) |
| `estimated_cost` | `Decimal64(6)` | Estimated cost in USD |
| `context_quality_score` | `Nullable(Float32)` | Context assembly quality (0.0–1.0) |
| `reasoning_depth` | `Nullable(UInt8)` | Reasoning depth level |
| `event_time` | `DateTime64(3)` | Event timestamp (ms precision) — partition key |

**TTL**: `event_time + INTERVAL 365 DAY`

---

### `behavioral_drift`

Agent behavioral drift measurements relative to baseline.

| Column | Type | Notes |
|--------|------|-------|
| `agent_id` | `UUID` | Agent being measured — part of ORDER BY |
| `revision_id` | `UUID` | Agent revision |
| `metric_name` | `String` | Metric identifier (e.g., `response_latency`, `token_usage`) — part of ORDER BY |
| `metric_value` | `Float64` | Current measured value |
| `baseline_value` | `Float64` | Baseline reference value |
| `deviation` | `Float64` | Computed deviation from baseline |
| `measured_at` | `DateTime64(3)` | Measurement timestamp — partition key |

**TTL**: `measured_at + INTERVAL 180 DAY`

---

### `fleet_performance`

Fleet-level performance metrics.

| Column | Type | Notes |
|--------|------|-------|
| `fleet_id` | `UUID` | Fleet identifier — part of ORDER BY |
| `metric_name` | `String` | Metric identifier — part of ORDER BY |
| `metric_value` | `Float64` | Measured value |
| `member_count` | `UInt16` | Number of fleet members at time of measurement |
| `measured_at` | `DateTime64(3)` | Measurement timestamp — partition key |

**TTL**: None (retained indefinitely)

---

### `self_correction_analytics`

Self-correction loop outcomes.

| Column | Type | Notes |
|--------|------|-------|
| `execution_id` | `UUID` | Execution where self-correction occurred |
| `agent_id` | `UUID` | Agent under self-correction — part of ORDER BY |
| `loop_id` | `UUID` | Self-correction loop identifier |
| `iterations` | `UInt8` | Number of correction iterations |
| `converged` | `UInt8` | 1 if converged, 0 if not (bool equivalent) |
| `initial_quality` | `Float32` | Quality score before correction |
| `final_quality` | `Float32` | Quality score after correction |
| `total_cost` | `Decimal64(6)` | Total cost of the correction loop |
| `completed_at` | `DateTime64(3)` | Completion timestamp — partition key |

**TTL**: None (retained indefinitely)

---

### `usage_hourly` (Materialized View Target)

Pre-aggregated hourly rollup of usage events.

| Column | Type | Notes |
|--------|------|-------|
| `workspace_id` | `UUID` | Tenant scoping — part of ORDER BY |
| `agent_id` | `UUID` | Agent — part of ORDER BY |
| `provider` | `String` | Model provider — part of ORDER BY |
| `model` | `String` | Model name — part of ORDER BY |
| `hour` | `DateTime` | Start of hour — part of ORDER BY |
| `total_input_tokens` | `UInt64` | Sum of input tokens |
| `total_output_tokens` | `UInt64` | Sum of output tokens |
| `total_reasoning_tokens` | `UInt64` | Sum of reasoning tokens |
| `total_cost` | `Decimal128(6)` | Sum of estimated costs |
| `event_count` | `UInt64` | Count of events |
| `avg_context_quality` | `Float64` | Average context quality score |

**Engine**: `SummingMergeTree` (prod: `ReplicatedSummingMergeTree`) — automatically sums numeric columns on merge for same ORDER BY key.

---

### `usage_hourly_mv` (Materialized View)

```sql
CREATE MATERIALIZED VIEW usage_hourly_mv TO usage_hourly AS
SELECT
    workspace_id,
    agent_id,
    provider,
    model,
    toStartOfHour(event_time) AS hour,
    sum(input_tokens) AS total_input_tokens,
    sum(output_tokens) AS total_output_tokens,
    sum(reasoning_tokens) AS total_reasoning_tokens,
    sum(estimated_cost) AS total_cost,
    count() AS event_count,
    avg(context_quality_score) AS avg_context_quality
FROM usage_events
GROUP BY workspace_id, agent_id, provider, model, hour;
```

---

## Helm Values Schema

```yaml
# deploy/helm/clickhouse/values.yaml (shared defaults)
clickhouse:
  image: clickhouse/clickhouse-server:24.3
  replicaCount: 2               # override: 1 in values-dev.yaml
  shardCount: 1
  keeper:
    enabled: true               # override: false in values-dev.yaml
    replicaCount: 3
    image: clickhouse/clickhouse-keeper:24.3

  auth:
    user: default
    password: ""                # set from Secret: clickhouse-credentials

  resources:
    requests:
      memory: 4Gi
      cpu: "2"
    limits:
      memory: 8Gi
      cpu: "4"

  config:
    max_memory_usage: "4000000000"           # 4GB per query
    max_bytes_before_external_sort: "2000000000"
    max_insert_block_size: 1048576
    merge_tree_max_rows_to_use_cache: 1000000

persistence:
  storageClassName: standard
  size: 50Gi                    # override: 100Gi in values-prod.yaml

service:
  type: ClusterIP
  httpPort: 8123
  nativePort: 9000

schemaInit:
  enabled: true
  image: clickhouse/clickhouse-server:24.3   # same image (has clickhouse-client)

backup:
  enabled: true
  schedule: "0 4 * * *"        # daily at 04:00 UTC
  image: altinity/clickhouse-backup:2.5
  bucket: "backups"
  prefix: "clickhouse"

networkPolicy:
  enabled: true
```

---

## Kubernetes Resources

### Production Resources

| Resource | Kind | Count |
|---------|------|-------|
| ClickHouse server StatefulSet | `StatefulSet` | 1 (2 replicas) |
| ClickHouse Keeper StatefulSet | `StatefulSet` | 1 (3 replicas) |
| PersistentVolumeClaims (server) | `PVC` | 2 (one per replica) |
| PersistentVolumeClaims (keeper) | `PVC` | 3 (one per keeper node) |
| `Secret` (credentials) | `Secret` | 1 (`clickhouse-credentials`) |
| Schema init `Job` | `Job` | 1 (Helm post-install/post-upgrade hook) |
| Backup `CronJob` | `CronJob` | 1 (daily) |
| `NetworkPolicy` | `NetworkPolicy` | 1 |
| `ConfigMap` (server config) | `ConfigMap` | 1 |
| `ConfigMap` (keeper config) | `ConfigMap` | 1 |
| `ConfigMap` (backup config) | `ConfigMap` | 1 |
| `Service` (ClusterIP) | `Service` | 2 (server + keeper) |

### Development Resources

| Resource | Kind | Count |
|---------|------|-------|
| ClickHouse server StatefulSet | `StatefulSet` | 1 (1 replica) |
| PersistentVolumeClaim | `PVC` | 1 |
| `Secret` (credentials) | `Secret` | 1 |
| Schema init `Job` | `Job` | 1 |
| `ConfigMap` (server config) | `ConfigMap` | 1 |
| `Service` (ClusterIP) | `Service` | 1 |

### Namespace: `platform-data`

All ClickHouse infrastructure lives in `platform-data`.

### Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 8123 | HTTP | Application queries + Prometheus metrics (`/metrics`) + Play UI (`/play`) |
| 9000 | TCP | Native protocol (bulk inserts, inter-replica exchange) |
| 9009 | TCP | ClickHouse inter-replica data exchange |
| 9181 | TCP | ClickHouse Keeper client port |
| 9234 | TCP | ClickHouse Keeper Raft port |
| 9444 | TCP | ClickHouse Keeper Raft internal |

### Service Reference

| Service Name | Port | Target |
|-------------|------|--------|
| `musematic-clickhouse` | 8123, 9000 | HTTP API + native TCP |
| `musematic-clickhouse-keeper` | 9181 | Keeper client |

---

## AsyncClickHouseClient Interface

Located at: `apps/control-plane/src/platform/common/clients/clickhouse.py`

```
AsyncClickHouseClient
├── execute_query(sql: str, params: dict = {}) → list[dict[str, Any]]
│       # Execute a SELECT query; returns rows as list of dicts
├── execute_command(sql: str, params: dict = {}) → None
│       # Execute DDL/DML (CREATE, INSERT single, ALTER); no return value
├── insert_batch(table: str, data: list[dict], column_names: list[str]) → None
│       # Batch insert using clickhouse-connect columnar protocol
├── health_check() → dict[str, Any]
│       # Returns {"status": "ok", "version": "24.x.x", "uptime_seconds": int}
└── close() → None
│       # Close HTTP connection pool

BatchBuffer
├── __init__(client: AsyncClickHouseClient, table: str, column_names: list[str],
│            max_size: int = 1000, flush_interval: float = 5.0)
├── add(row: dict) → None
│       # Add row to buffer; auto-flushes when max_size reached
├── flush() → None
│       # Manually flush buffered rows via insert_batch
├── start() → None
│       # Start background flush timer (asyncio.Task)
└── stop() → None
        # Stop timer and flush remaining rows

ClickHouseClientError(Exception)
├── ClickHouseConnectionError    # HTTP connectivity failure
└── ClickHouseQueryError         # Query execution error (syntax, timeout)
```

**Mode detection**: Unlike Neo4j, ClickHouse has no local mode fallback. If `CLICKHOUSE_URL` is not set, the client raises `ClickHouseConnectionError` at construction time. Analytics are only available when the cluster is deployed.
