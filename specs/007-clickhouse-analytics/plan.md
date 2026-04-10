# Implementation Plan: ClickHouse Analytics

**Branch**: `007-clickhouse-analytics` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/007-clickhouse-analytics/spec.md`

## Summary

Deploy ClickHouse as the dedicated OLAP engine for the Agentic Mesh Platform. The implementation delivers: a Helm chart managing ClickHouse server StatefulSet (1 shard × 2 replicas in prod, single node in dev) with ClickHouse Keeper for replica coordination, idempotent SQL init scripts for 4 analytics tables + 1 materialized view, a Python async client wrapper (`clickhouse-connect 0.8+`) with a `BatchBuffer` utility for efficient batch ingestion, a daily backup CronJob using `clickhouse-backup`, and network policy restricting access to authorized namespaces.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: `clickhouse-connect 0.8+` (HTTP interface), Helm 3.x (custom chart), `altinity/clickhouse-backup` (backup tool)  
**Storage**: ClickHouse 24.3+ (OLAP database, StatefulSet — no operator) + ClickHouse Keeper (Raft consensus, separate StatefulSet)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (ClickHouse) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python ClickHouse client) + scripts  
**Performance Goals**: Aggregation over 10M rows with partition pruning < 1s p99; hourly rollup query < 200ms  
**Constraints**: Workspace-scoped queries mandatory; password auth required; backup to object storage (feature 004 dependency); no local mode fallback (analytics require running cluster)  
**Scale/Scope**: 4 base tables + 1 rollup + 1 materialized view, 2 production replicas, 3 Keeper nodes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS |
| ClickHouse client | `clickhouse-connect 0.8+` per constitution §2.1 | PASS |
| HTTP interface | "HTTP interface, batch inserts" per constitution §2.1 | PASS |
| ClickHouse technology | ClickHouse per constitution §2.4 | PASS |
| ClickHouse ports | 8123 (HTTP), 9000 (TCP) per constitution §2.4 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS |
| Namespace: observability | `platform-observability` per constitution | PASS — metrics at `:8123/metrics` |
| No analytics in PostgreSQL | Constitution AD-3.3: "Never compute rollups in PostgreSQL" | PASS — all OLAP in ClickHouse |
| No time-series in PostgreSQL | Constitution AD-3.3 | PASS — all time-series in ClickHouse |
| Helm chart conventions | No operator sub-dependencies | PASS — StatefulSet direct, no Altinity operator |
| Async everywhere | `clickhouse-connect` async mode | PASS |
| Secrets not in LLM context | Password managed via Kubernetes Secret `clickhouse-credentials` | PASS |
| Observability | ClickHouse Prometheus metrics at `/metrics` | PASS |
| Backup storage | Feature 004 (minio-object-storage) dependency documented | PASS |
| Kafka data source | Feature 003 (kafka-event-backbone) — consumers out of scope | PASS — documented |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/007-clickhouse-analytics/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (tables, views, Helm schema, client interface)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── clickhouse-cluster.md          # Cluster infrastructure contract
│   └── python-clickhouse-client.md   # Python client interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/clickhouse/
├── Chart.yaml                      # Chart metadata (no external chart dependency — custom StatefulSet)
├── values.yaml                     # Shared defaults (2 replicas, Keeper enabled, auth, resources)
├── values-prod.yaml                # Production overrides (ReplicatedMergeTree, 100Gi PVC, full resources)
├── values-dev.yaml                 # Development overrides (MergeTree, 1 replica, no Keeper, no backup)
└── templates/
    ├── statefulset-server.yaml     # ClickHouse server StatefulSet
    ├── statefulset-keeper.yaml     # ClickHouse Keeper StatefulSet (prod only)
    ├── configmap-server.yaml       # ClickHouse server config (config.xml overrides)
    ├── configmap-keeper.yaml       # Keeper config (prod only)
    ├── configmap-backup.yaml       # clickhouse-backup config (prod only)
    ├── secret-credentials.yaml     # Secret: clickhouse-credentials with CLICKHOUSE_PASSWORD
    ├── service-server.yaml         # ClusterIP service for HTTP (8123) + TCP (9000)
    ├── service-keeper.yaml         # ClusterIP service for Keeper client (9181) — headless
    ├── schema-init-job.yaml        # Helm post-install/post-upgrade hook (clickhouse-client)
    ├── network-policy.yaml         # NetworkPolicy (HTTP 8123, TCP 9000, inter-replica, Keeper)
    └── backup-cronjob.yaml         # CronJob running clickhouse-backup daily

deploy/clickhouse/init/
├── 001-usage-events.sql                # usage_events table
├── 002-behavioral-drift.sql            # behavioral_drift table
├── 003-fleet-performance.sql           # fleet_performance table
├── 004-self-correction-analytics.sql   # self_correction_analytics table
├── 005-usage-hourly.sql                # usage_hourly target table
└── 006-usage-hourly-mv.sql             # usage_hourly_mv materialized view

apps/control-plane/src/platform/common/clients/clickhouse.py
    # AsyncClickHouseClient using clickhouse-connect 0.8+ (HTTP interface)
    # Methods: execute_query, execute_command, insert_batch, health_check, close
    # BatchBuffer: add, flush, start, stop (async timer-based batch flushing)
    # Exceptions: ClickHouseClientError, ClickHouseConnectionError, ClickHouseQueryError

apps/control-plane/tests/integration/
├── test_clickhouse_basic.py            # Insert, query, workspace isolation
├── test_clickhouse_materialized.py     # Materialized view rollup consistency
├── test_clickhouse_batch_buffer.py     # BatchBuffer auto-flush, timer flush, stop flush
└── test_clickhouse_partition.py        # Partition pruning verification, TTL config check
```

**Structure Decision**: Python client at `apps/control-plane/src/platform/common/clients/clickhouse.py` (pre-defined in constitution §4 repo structure). SQL init scripts at `deploy/clickhouse/init/` (numbered for execution order, separate from Helm to allow standalone execution). Helm chart at `deploy/helm/clickhouse/` — custom chart (no upstream dependency chart) because ClickHouse's official chart is tightly coupled to the Altinity operator.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- ClickHouse as StatefulSet (no operator) — custom Helm chart
- ClickHouse Keeper for replica coordination (not ZooKeeper)
- `ReplicatedMergeTree` (prod) / `MergeTree` (dev)
- Schema init via `clickhouse-client` Job with `IF NOT EXISTS`
- Backup via `clickhouse-backup` (Altinity tool) + S3 upload
- Python client: `clickhouse-connect 0.8+` (HTTP interface, batch inserts)
- `BatchBuffer` for efficient Kafka consumer ingestion
- ClickHouse Play UI for query console (`/play`)

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Table schemas (4 base + 1 rollup + 1 MV), Helm values schema, Kubernetes resources, `AsyncClickHouseClient` + `BatchBuffer` interface
- [contracts/clickhouse-cluster.md](contracts/clickhouse-cluster.md) — Cluster infrastructure contract
- [contracts/python-clickhouse-client.md](contracts/python-clickhouse-client.md) — Python client interface contract
- [quickstart.md](quickstart.md) — 14-section deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: ClickHouse cluster deployment (Helm chart, StatefulSet, Keeper, Secret)  
**P1 — US2**: Table initialization (SQL scripts, init Job, idempotency)  
**P1 — US3**: Insert/query operations (AsyncClickHouseClient, workspace filter, integration tests)  
**P1 — US4**: Materialized view rollups (verify auto-aggregation, consistency test)  
**P2 — US5**: Backup/restore (clickhouse-backup CronJob, S3 upload)  
**P2 — US6**: Network policy (NetworkPolicy template)  
**P2 — US7**: TTL eviction (verify TTL config, expiration test)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | Custom Helm chart with StatefulSet | No operator; official chart requires Altinity operator |
| Replica coordination | ClickHouse Keeper (built-in Raft) | Lighter than ZooKeeper; maintained by ClickHouse team |
| Table engine | ReplicatedMergeTree (prod) / MergeTree (dev) | Replication requires Keeper; dev doesn't need it |
| Schema init | `clickhouse-client` Job with `IF NOT EXISTS` | Idempotent; client included in ClickHouse image |
| Python client | `clickhouse-connect 0.8+` (HTTP) | Constitution-mandated; HTTP interface for queries |
| Batch insert | `BatchBuffer` (1000 rows or 5s timer) | User requirement; efficient for Kafka consumer ingestion |
| Backup | `altinity/clickhouse-backup` | User requirement; community-standard backup tool |
| Query console | ClickHouse Play UI (`/play`) | Built-in; no external tool needed |
| Rollup engine | SummingMergeTree for `usage_hourly` | Auto-sums numeric columns on merge; optimal for pre-aggregation |

## Dependencies

- **Upstream**: Feature 003 (kafka-event-backbone) — Kafka consumers write to ClickHouse tables (consumer integration out of scope); Feature 004 (minio-object-storage) — backup upload to `backups/clickhouse/`
- **Downstream**: All bounded contexts using analytics, cost intelligence, behavioral drift, fleet performance
- **Parallel with**: Neo4j (006), Qdrant (005), Redis (002) — no dependency relationship
- **Blocks**: Usage metering dashboards, cost intelligence, behavioral drift detection, fleet performance profiles

## Complexity Tracking

No constitution violations. Standard complexity for this feature. ClickHouse Keeper adds a second StatefulSet (3 nodes) in production — this is inherent to ClickHouse replication and cannot be avoided without ZooKeeper (which would be heavier). The additional Keeper StatefulSet is documented in the Helm chart and data model.
