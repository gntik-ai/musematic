# Feature Specification: ClickHouse Analytics Deployment

**Feature Branch**: `007-clickhouse-analytics`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: Deploy ClickHouse as the dedicated OLAP engine for usage analytics, cost intelligence, behavioral drift detection, fleet performance profiling, quality signal aggregation, KPI computation, and time-series operational metrics.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Analytics Database Cluster (Priority: P1)

A platform operator deploys a production-ready analytics database cluster with a single command. In production, the cluster runs 1 shard with 2 replicas for data redundancy and read scaling, coordinated by a built-in consensus service. In development, a single standalone node runs for local testing. The operator can verify cluster health through built-in metrics exposed to the monitoring stack and a web-based query console.

**Why this priority**: Without the running cluster, no service can store or query analytics data. This is the foundation for all usage metering, cost intelligence, and behavioral drift operations.

**Independent Test**: Deploy the cluster, verify all nodes are running and healthy, confirm the cluster accepts connections on the HTTP interface and native TCP port, and validate that the query console is accessible.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 2 replica nodes start in the designated namespace, both report ready status, and replica coordination is active.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single standalone node starts and accepts connections on the HTTP interface and native TCP port.
3. **Given** a running production cluster, **When** one replica node is terminated, **Then** the remaining node continues serving queries without data loss, and the terminated node rejoins and re-syncs automatically.

---

### User Story 2 - Platform Initializes Analytics Tables and Materialized Views (Priority: P1)

The platform provisions all required analytics tables (usage events, behavioral drift, fleet performance, self-correction analytics) and materialized views (hourly usage rollups) through an idempotent initialization process. Tables use time-based partitioning for query performance and configurable TTL for automatic data retention management.

**Why this priority**: Tables and materialized views must exist before any service can write analytics data. Without them, usage metering, cost tracking, and drift detection cannot function.

**Independent Test**: Run the table initialization, verify all tables and materialized views exist via the query console. Run initialization again to confirm it is idempotent (no errors, no duplicate tables).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** table initialization runs, **Then** all documented tables exist (`usage_events`, `behavioral_drift`, `fleet_performance`, `self_correction_analytics`) with correct partitioning and ordering keys.
2. **Given** initialized tables, **When** initialization runs a second time, **Then** no errors occur and no duplicate tables or views are created.
3. **Given** initialized tables, **When** the hourly rollup materialized view exists, **Then** inserting a row into `usage_events` automatically populates the corresponding hourly rollup in the target table.
4. **Given** a table with a TTL of 365 days, **When** data older than 365 days exists, **Then** the system automatically removes it during background merge operations.

---

### User Story 3 - Services Insert and Query Analytics Data (Priority: P1)

Platform services insert analytics events (usage records, drift metrics, fleet performance snapshots) into the analytics database and query them using time-range and workspace-scoped filters. All queries support workspace scoping to enforce multi-tenant data isolation. Common query patterns include: aggregating token usage by workspace and time period, computing cost breakdowns by agent and model provider, and detecting behavioral drift trends.

**Why this priority**: Data insertion and querying is the core value proposition. Without it, dashboards, cost intelligence, and drift detection cannot function.

**Independent Test**: Insert 1000 usage events across 3 workspaces and 5 time periods. Query with workspace filter and time range — verify results contain only matching records. Verify the hourly rollup materialized view has computed aggregations correctly.

**Acceptance Scenarios**:

1. **Given** a running cluster with tables, **When** a service inserts usage events via the HTTP interface, **Then** the events are persisted and queryable.
2. **Given** a table with events across multiple workspaces, **When** a service queries with a workspace filter, **Then** only events belonging to that workspace are returned.
3. **Given** time-partitioned data spanning 12 months, **When** a service queries a specific month, **Then** the query engine prunes partitions and only scans the relevant month's data (verifiable via query execution plan).
4. **Given** 10 million usage events, **When** a service executes an aggregation query with partition pruning (e.g., sum of tokens by agent for one month), **Then** results are returned within 1 second.

---

### User Story 4 - Platform Computes Materialized Rollups Automatically (Priority: P1)

When usage events are inserted, the system automatically maintains pre-aggregated rollups (hourly usage by workspace, agent, provider, and model). These rollups enable dashboard queries to read pre-computed summaries instead of scanning raw event data, reducing query latency for common analytics views.

**Why this priority**: Materialized views are essential for dashboard performance. Without them, every dashboard query would scan raw event tables, making analytics slow at scale.

**Independent Test**: Insert 100 events for the same workspace/agent/hour. Query the hourly rollup table — verify it contains exactly one aggregated row with correct sums and counts matching the 100 inserted events.

**Acceptance Scenarios**:

1. **Given** a running cluster with materialized views, **When** usage events are inserted, **Then** the hourly rollup target table is updated automatically within the same insert operation.
2. **Given** 100 events for workspace "ws-A" in the 14:00 hour, **When** querying the hourly rollup for "ws-A" at 14:00, **Then** the total input tokens equals the sum of all 100 events' input tokens, and the event count equals 100.
3. **Given** rollup data, **When** a dashboard queries hourly aggregations for the past 7 days, **Then** results are returned within 200 milliseconds (pre-aggregated, no raw scan).

---

### User Story 5 - Operator Backs Up and Restores Analytics Data (Priority: P2)

An operator can trigger a backup of all analytics tables. Backups are automatically uploaded to the platform's object storage. A scheduled backup runs daily. The operator can restore from any backup to recover after data loss or corruption.

**Why this priority**: Backup and restore is essential for operational resilience but not needed for initial deployment.

**Independent Test**: Create test data, trigger a backup, verify it uploads to object storage. Drop a table. Restore from the backup. Verify all data is recovered.

**Acceptance Scenarios**:

1. **Given** a running cluster with data, **When** a backup is triggered, **Then** a backup of all tables is created and uploaded to the configured object storage location within 30 minutes for up to 100 million rows.
2. **Given** a scheduled backup, **When** the configured time arrives (default: daily at 04:00 UTC), **Then** an automated backup is created and uploaded.
3. **Given** a backup in object storage, **When** the operator restores from that backup, **Then** all tables, data, and materialized views are recovered.

---

### User Story 6 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control` and `platform-execution`) can connect to the analytics database. All other namespaces are blocked by network policy. The monitoring system can scrape metrics from the designated monitoring namespace.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** a service in `platform-control` connects via the HTTP interface, **Then** the connection succeeds and the service can execute queries.
2. **Given** a running cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.
3. **Given** a running cluster, **When** the monitoring system scrapes metrics, **Then** the metrics endpoint is accessible from the monitoring namespace.

---

### User Story 7 - TTL Automatically Evicts Expired Data (Priority: P2)

Tables with configured TTL (time-to-live) automatically remove data older than the retention period during background merge operations. Usage events are retained for 365 days, behavioral drift metrics for 180 days. Fleet performance and self-correction analytics have no TTL (retained indefinitely). Operators can verify TTL configuration and monitor eviction through the query console.

**Why this priority**: Automatic data lifecycle management prevents unbounded storage growth but is not needed for initial deployment.

**Independent Test**: Insert data with timestamps older than the TTL. Trigger a background merge. Verify the expired data is no longer queryable.

**Acceptance Scenarios**:

1. **Given** usage events with a 365-day TTL, **When** data older than 365 days exists and a merge completes, **Then** the expired data is removed from the table.
2. **Given** behavioral drift metrics with a 180-day TTL, **When** data older than 180 days exists and a merge completes, **Then** the expired data is removed from the table.
3. **Given** fleet performance data with no TTL, **When** data of any age exists, **Then** the data is retained indefinitely.
4. **Given** a table with TTL, **When** the operator queries the table's TTL configuration, **Then** the configured retention period is visible.

---

### Edge Cases

- What happens when a batch insert partially fails? The analytics database handles batch inserts atomically per block. If a block insert fails (e.g., schema mismatch), the entire block is rejected and the client receives an error. Previously inserted blocks are not rolled back (no cross-block transactions). The client should retry the failed block.
- What happens when the materialized view target table does not exist? The materialized view creation fails with an error. The initialization script must create the target table before the materialized view.
- What happens when a query scans partitions without a time filter? The query scans all partitions (full table scan). This is permitted but may be slow for large tables. The platform client wrapper should log a warning when queries lack partition-pruning conditions.
- What happens when both replicas go down simultaneously? The cluster is unavailable for writes and reads. On recovery, replicas re-sync from the last consistent state. No data corruption occurs due to the merge-tree architecture. Monitoring alerts trigger when both replicas are unhealthy.
- What happens when a TTL merge removes data that a running query is reading? The analytics engine uses snapshot isolation for reads. Running queries continue to read from the pre-merge snapshot. TTL removal only affects new queries after the merge completes.
- What happens when a materialized view receives an insert with NULL values in aggregated fields? NULL values are handled according to standard aggregation rules: `sum()` ignores NULLs, `count()` counts all rows, `avg()` ignores NULLs. The materialized view produces correct aggregations regardless of NULL presence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy an analytics database cluster with configurable topology: 1 shard with 2 replicas for production, 1 standalone node for development.
- **FR-002**: System MUST replicate data across cluster nodes in production for fault tolerance during single-node failures.
- **FR-003**: System MUST create all documented analytics tables (`usage_events`, `behavioral_drift`, `fleet_performance`, `self_correction_analytics`) with time-based partitioning and configurable ordering keys.
- **FR-004**: System MUST create a target table (`usage_hourly`) and materialized view (`usage_hourly_mv`) for automatic hourly rollup of usage events.
- **FR-005**: System MUST support data insertion via the HTTP interface and native TCP protocol.
- **FR-006**: System MUST support workspace-scoped queries that filter results to a single tenant's data.
- **FR-007**: System MUST support partition pruning for time-range queries to avoid full table scans.
- **FR-008**: System MUST configure TTL on `usage_events` (365 days) and `behavioral_drift` (180 days) tables for automatic data expiration.
- **FR-009**: System MUST authenticate all connections with platform-managed credentials.
- **FR-010**: System MUST expose cluster and query metrics for monitoring (node health, query latency, active queries, storage usage, merge status).
- **FR-011**: System MUST enforce network access restrictions so only authorized namespaces can connect.
- **FR-012**: System MUST support backup of all analytics data and table definitions.
- **FR-013**: System MUST support automated scheduled backups (configurable schedule, default: daily at 04:00 UTC).
- **FR-014**: System MUST support restore from backup, recovering all tables, data, and materialized views.
- **FR-015**: System MUST upload backup files to the platform's object storage for durable backup retention.
- **FR-016**: System MUST provide a web-based query console for operators to inspect data, run ad-hoc queries, and view cluster status.

### Key Entities

- **Analytics Cluster**: The node ensemble that stores and serves analytics data. Defined by shard count, replica count, storage configuration, and authentication.
- **Usage Event**: A single record of resource consumption (tokens, cost, quality scores) associated with a workspace, agent, and model provider. Partitioned by month, ordered by workspace and time.
- **Behavioral Drift Metric**: A measured deviation of an agent's behavior from its baseline. Partitioned by month, ordered by agent and metric name.
- **Fleet Performance Metric**: A measured performance indicator for a fleet of coordinated agents. Partitioned by month, ordered by fleet and metric name.
- **Self-Correction Analytic**: A record of a self-correction loop's outcome (convergence, cost, quality delta). Partitioned by month, ordered by agent.
- **Hourly Rollup**: A pre-aggregated summary of usage events by workspace, agent, provider, model, and hour. Automatically maintained by a materialized view.
- **Backup**: A full database export for recovery. Includes all table definitions, data, and materialized view definitions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All documented tables (4 base + 1 rollup) and materialized views (1) are created and active after a single initialization command.
- **SC-002**: The cluster survives termination of one replica without data loss or query service interruption.
- **SC-003**: Aggregation queries over 10 million rows with partition pruning complete under 1 second at p99.
- **SC-004**: Materialized view rollups are consistent with raw data — hourly sums match within 0.01% of manual re-aggregation.
- **SC-005**: Workspace-scoped queries return zero rows from other workspaces — 100% tenant isolation.
- **SC-006**: Automated backup completes and uploads to object storage within 30 minutes for up to 100 million rows.
- **SC-007**: Restore from backup recovers all tables, data, and materialized views with zero data loss.
- **SC-008**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-009**: TTL eviction removes data older than configured retention period within 24 hours of the expiration threshold.
- **SC-010**: Cluster metrics (node health, query latency, active queries, storage usage) are visible in the monitoring system within 60 seconds.

## Assumptions

- No dedicated Kubernetes operator is used for the analytics database — it is deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant (feature 005) and Neo4j (feature 006) deployment patterns.
- Production uses replicated table engines (requires a coordination service); development uses non-replicated table engines (no coordination needed).
- A built-in consensus service (ClickHouse Keeper) is used for replica coordination in production — external ZooKeeper is not required. ClickHouse Keeper runs as a separate StatefulSet (3 nodes for quorum).
- The platform's Python client (`clickhouse-connect 0.8+`, HTTP interface) is used by platform services but the full client wrapper is not part of this feature's scope — this feature covers cluster and table infrastructure plus a basic Python client wrapper.
- Backup data is uploaded to the `backups/clickhouse/` prefix in the object storage bucket deployed by feature 004 (minio-object-storage).
- Table initialization uses `CREATE TABLE IF NOT EXISTS` syntax for idempotency.
- Data flows into the analytics database from Kafka consumers (feature 003) — but the consumer integration is not part of this feature's scope. This feature provides the schema and client; consumers are implemented in downstream bounded contexts.
- Materialized views use the `TO` syntax (writing to a separate target table) rather than implicit inner tables — this gives explicit control over the target table schema and lifecycle.
- The Prometheus metrics endpoint is exposed on the HTTP port at `/metrics` — no separate metrics port is needed.
- The web-based query console is the built-in HTTP interface with `play` endpoint (ClickHouse Play UI) — no external tool is installed for this purpose.
