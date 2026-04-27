# Data Stores

Musematic uses purpose-specific stores behind bounded contexts rather than one shared persistence model.

| Store | Primary Use | Ownership Notes |
| --- | --- | --- |
| PostgreSQL | Control-plane transactional state. | Each bounded context owns tables through Alembic migrations. |
| Redis | Hot counters, sessions, leases, locks, rate limits, caches. | Keys are namespaced by feature and documented in plans. |
| Kafka | Event backbone for domain events and runtime streams. | Producers own event schemas; consumers must be idempotent. |
| MinIO / S3 | Artifacts, evidence, backups, large timelines. | Buckets are reserved per feature and referenced from rows. |
| ClickHouse | Analytics, cost, quality, and time-series rollups. | Used for read-heavy aggregates, not source-of-truth writes. |
| Qdrant | Vector search for memory, evaluation, discovery, and registry. | Collections are feature-owned. |
| Neo4j | Knowledge graph and relationship traversal. | Used where graph queries are the primary access pattern. |
| OpenSearch | Full-text search and selected audit/indexed payloads. | Indexes are lifecycle-managed and searchable by operators. |

The control plane reads and writes through local clients in `apps/control-plane/src/platform/common/clients`. Satellite services use typed clients for their own runtime dependencies.
