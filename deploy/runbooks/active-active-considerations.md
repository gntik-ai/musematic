# Active-Active Considerations

The default multi-region posture is active-passive. The platform refuses a second enabled primary region unless an operator has explicitly designed and documented conflict resolution for every stateful subsystem.

## Active-active safe by default

- API instances, websocket hubs, schedulers, workers, workflow orchestration code, runtime-controller clients, and stateless projection workers can run in more than one region when they point at one authoritative state plane.
- Read-only dashboards can be served from either region when their backing stores have declared replication status and freshness.

## Not active-active safe by default

- PostgreSQL remains the relational system of record with a single writable primary.
- The FQN namespace registry requires global uniqueness and cannot accept two independent writers without a conflict-resolution protocol.
- Kafka, object storage, ClickHouse, Qdrant, Neo4j, and OpenSearch can replicate across regions, but this feature treats the secondary as passive unless an operator has documented bidirectional write rules.

## Requirements before active-active

- Define a conflict-resolution strategy for every mutable table, stream, object prefix, graph label, vector collection, and full-text index.
- Document how workspace residency rules and privacy-compliance transfer policies apply to every cross-region write.
- Rehearse a rollback to active-passive and verify no namespace, identity, or audit-chain fork remains.
- Keep a dated operator acknowledgement with the failover plan and link it from the region configuration change record.

Until those requirements exist, enabling two primary regions risks split-brain behavior and is blocked by both application validation and the partial unique index on enabled primary regions.

