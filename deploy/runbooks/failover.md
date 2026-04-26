# Region Failover Runbook

Use this runbook with a named failover plan in `/api/v1/regions/failover-plans`. Rehearse quarterly and after any infrastructure topology change.

## Pre-checks

- Confirm the secondary region is enabled and replication status is visible for PostgreSQL, Kafka, S3-compatible object storage, ClickHouse, Qdrant, Neo4j, and OpenSearch.
- Confirm every component is below the target RPO or explicitly record which data may be stale.
- Confirm maintenance mode policy for the cutover: either complete maintenance first or document the emergency override reason.

## Typed steps

1. `drain_workers`: stop accepting new worker dispatches while allowing in-flight executions to finish.
2. `promote_postgres`: promote the secondary PostgreSQL replica after confirming WAL replay is current enough for the declared RPO.
3. `flip_kafka_mirrormaker`: reverse or pause MirrorMaker flow so producers target the promoted region.
4. `cutover_s3`: verify cross-region replication rules and promote the destination bucket or endpoint alias.
5. `cutover_clickhouse`: switch analytics readers to replicated tables and verify recent partitions.
6. `cutover_qdrant`: verify collection replication and move vector-search traffic to the target endpoint.
7. `cutover_neo4j`: verify follower state and switch graph reads/writes to the target cluster.
8. `cutover_opensearch`: verify cross-cluster replication and move full-text aliases.
9. `update_dns`: update operator-approved DNS or routing records.
10. `verify_health`: run API, workflow, auth, registry, marketplace, and dashboard health checks.
11. `resume_workers`: resume worker dispatch in the target region.

## Failure handling

- A failed step halts the plan. Do not continue manually without adding an audit note and a new run record.
- If the promoted region has partial replication coverage, keep the operator dashboard open and announce the data gap.
- If rollback is safer than proceeding, reverse DNS/routing first, then restore worker dispatch only after relational state is consistent.

