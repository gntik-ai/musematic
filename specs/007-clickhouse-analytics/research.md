# Research: ClickHouse Analytics Deployment

**Feature**: 007-clickhouse-analytics  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: ClickHouse Deployment Model (StatefulSet, No Operator)

**Decision**: Deploy ClickHouse as a Kubernetes `StatefulSet` directly — no Altinity operator or other operator is used. A custom Helm chart at `deploy/helm/clickhouse/` manages two StatefulSets: one for ClickHouse server (1 shard × 2 replicas in prod, 1 node in dev) and one for ClickHouse Keeper (3 nodes in prod for quorum, omitted in dev). The spec assumption explicitly states: "deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant (feature 005) and Neo4j (feature 006) deployment patterns."

**Rationale**: The Altinity operator adds complexity and a Kubernetes CRD dependency. The constitution does not mandate any operator for ClickHouse (unlike PostgreSQL with CloudNativePG or Kafka with Strimzi). The project's established pattern for data stores without an explicit operator (Qdrant, Neo4j) is a custom wrapper Helm chart around a StatefulSet. ClickHouse's official Docker images and configuration are well-documented for StatefulSet deployment.

**Alternatives considered**:
- Altinity ClickHouse Operator: adds CRD management, auto-scaling, and schema migrations. Overkill for a fixed 1-shard/2-replica topology. Rejected — adds operator dependency not in constitution.
- Bitnami ClickHouse Helm chart: exists but bundles ZooKeeper instead of ClickHouse Keeper. Rejected — built-in Keeper is preferred.
- ClickHouse Cloud (managed): not self-hosted Kubernetes. Rejected.

---

## Decision 2: Replica Coordination — ClickHouse Keeper (Not ZooKeeper)

**Decision**: ClickHouse Keeper (built-in Raft-based consensus) is used for replica coordination in production. Deployed as a separate 3-node StatefulSet (`musematic-clickhouse-keeper`) in the same `platform-data` namespace. Development mode skips Keeper entirely (uses non-replicated `MergeTree` engine).

**Rationale**: ClickHouse Keeper is the official replacement for ZooKeeper in ClickHouse deployments. It uses the Raft protocol, requires fewer resources, and is maintained by the ClickHouse team. The spec assumption confirms: "ClickHouse Keeper (built-in consensus) is used for replica coordination in production — external ZooKeeper is not required." Three Keeper nodes provide quorum tolerance for one-node failure.

**Alternatives considered**:
- Apache ZooKeeper: legacy approach, heavier footprint, separate JVM dependency. Rejected.
- Embedded Keeper (inside ClickHouse server process): simpler but co-locates Keeper with the data node, reducing isolation. Rejected for production — Keeper should survive data node restart.

---

## Decision 3: Table Engine Selection

**Decision**: Production tables use `ReplicatedMergeTree` engine (replication via ClickHouse Keeper). Development tables use `MergeTree` (no replication). The SQL init scripts use a conditional macro: `{engine}` is set to `ReplicatedMergeTree` or `MergeTree` at init time based on the deployment mode. Alternatively, the init script provides separate SQL files for prod and dev, or uses ClickHouse's `{replica}` and `{shard}` macros.

**Rationale**: `ReplicatedMergeTree` is the standard production engine for ClickHouse with data redundancy. `MergeTree` is the base engine without replication — suitable for single-node dev. The spec states: "Production uses ReplicatedMergeTree engine (requires a coordination service); development uses MergeTree (no coordination needed)."

**Alternatives considered**:
- `ReplicatedMergeTree` for dev too: requires Keeper even for single-node, adds unnecessary complexity in dev. Rejected.
- `Distributed` table on top: needed for multi-shard setups. Current topology is 1 shard, so `Distributed` is not needed. Rejected.

---

## Decision 4: Table Initialization Pattern

**Decision**: SQL scripts are placed in `deploy/clickhouse/init/` directory. A Kubernetes `Job` (Helm post-install/post-upgrade hook) executes `clickhouse-client` against each SQL file in order. All `CREATE TABLE` and `CREATE MATERIALIZED VIEW` statements use `IF NOT EXISTS` for idempotency. The init Job uses the official ClickHouse Docker image (which includes `clickhouse-client`). Script execution order: (1) base tables, (2) rollup target tables, (3) materialized views.

**Rationale**: `clickhouse-client` is included in the official ClickHouse image. The `IF NOT EXISTS` pattern is supported by ClickHouse and ensures idempotent re-runs. This is consistent with the Neo4j schema init pattern (feature 006) using `cypher-shell` in a Job.

**Alternatives considered**:
- Python script using `clickhouse-connect`: requires a separate Python image in the Job. `clickhouse-client` is simpler and already in the server image. Rejected.
- Init container on the ClickHouse pod: blocks pod start; post-install Job is cleaner. Rejected.

---

## Decision 5: Python Client Wrapper

**Decision**: `apps/control-plane/src/platform/common/clients/clickhouse.py` implements `AsyncClickHouseClient` using `clickhouse-connect 0.8+` (HTTP interface). The client provides: `execute_query(sql, params)`, `insert_batch(table, data, column_names)`, `health_check()`, and `close()`. Batch inserts use `clickhouse-connect`'s native `insert()` method which sends data as columnar blocks over HTTP. A `BatchBuffer` utility class buffers events in memory and flushes every 5 seconds or 1000 events (whichever comes first), using `asyncio.Task` for the timer.

**Rationale**: Constitution §2.1 mandates `clickhouse-connect 0.8+` with "HTTP interface, batch inserts." The HTTP interface is simpler than the native TCP protocol and works through standard load balancers and network policies. `clickhouse-connect` handles connection pooling, retry, and columnar data formatting internally. The batch buffer is specified in the user input as a key requirement for efficient ingestion from Kafka consumers.

**Alternatives considered**:
- `asynch` (async native protocol client): not in constitution; `clickhouse-connect` is mandated. Rejected.
- `clickhouse-driver` (native TCP): constitution specifies HTTP interface. Rejected.
- Row-by-row inserts: extremely inefficient for OLAP workloads. User input explicitly states "Kafka consumers write batches to ClickHouse (not row-by-row)." Rejected.

---

## Decision 6: Backup via `clickhouse-backup`

**Decision**: A Kubernetes `CronJob` runs daily (default: `0 4 * * *` — 04:00 UTC) using the `altinity/clickhouse-backup` image. The backup tool creates a local backup of all tables, then uploads to S3-compatible storage at `s3://backups/clickhouse/{date}/`. Configuration is provided via a ConfigMap (`clickhouse-backup` config YAML) specifying the S3 endpoint, credentials, and ClickHouse connection. Restore is a manual operation documented in the quickstart.

**Rationale**: `clickhouse-backup` is the community-standard backup tool for ClickHouse. It handles consistent snapshots of MergeTree-family tables, supports S3-compatible storage, and includes freeze/unfreeze semantics for consistent backups. The user input explicitly requests "Create backup CronJob using `clickhouse-backup`." Using the `altinity/clickhouse-backup` image avoids building a custom backup tool.

**Alternatives considered**:
- Manual `ALTER TABLE FREEZE` + `aws s3 cp`: requires scripting the freeze/copy/unfreeze flow manually. `clickhouse-backup` encapsulates this. Rejected.
- ClickHouse built-in `BACKUP` command (23.3+): newer feature, limited S3 support compared to `clickhouse-backup`. Rejected for now — can migrate later.

---

## Decision 7: Network Policy

**Decision**: One `NetworkPolicy` in `platform-data` namespace:
- HTTP (8123) ingress from `platform-control` and `platform-execution` namespaces.
- Native TCP (9000) ingress from `platform-control` and `platform-execution` namespaces.
- HTTP (8123) ingress from `platform-observability` (Prometheus metrics scrape at `/metrics`).
- Inter-pod (9000, 9009) within `platform-data` for ClickHouse inter-replica and Keeper communication.
- Keeper ports (9181, 9234, 9444) within `platform-data` for Keeper client and Raft communication.

**Rationale**: ClickHouse uses port 9009 for inter-replica data exchange and port 9000 for native TCP. ClickHouse Keeper uses 9181 (client), 9234 (Raft), and 9444 (Raft internal). Metrics are served on the HTTP port (8123) at `/metrics`. Network policy mirrors the established pattern from features 005 (Qdrant) and 006 (Neo4j).

**Alternatives considered**:
- Separate policy per namespace: more verbose, same security outcome. Rejected.

---

## Decision 8: ClickHouse Play UI for Query Console

**Decision**: The built-in ClickHouse Play UI (available at `http://<host>:8123/play`) serves as the web-based query console for operators. No external tool (e.g., Tabix, DBeaver) is installed. The Play UI is included in the standard ClickHouse Docker image and requires no additional configuration.

**Rationale**: The spec requires "a web-based query console for operators" (FR-016). ClickHouse Play is the official embedded UI, available at `/play` on the HTTP port. It supports ad-hoc queries, result visualization, and cluster status inspection. This matches the spec assumption: "The web-based query console is the built-in HTTP interface with play endpoint."

**Alternatives considered**:
- Tabix: external tool, requires separate deployment. Rejected — adds complexity.
- Grafana with ClickHouse plugin: useful for dashboards but not an ad-hoc query console. Rejected for this scope.

---

## Resolution Summary

All technical unknowns resolved. No NEEDS CLARIFICATION markers remain. Plan can proceed to Phase 1.
