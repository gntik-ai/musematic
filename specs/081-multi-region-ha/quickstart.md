# Quickstart: Multi-Region Operations

1. Enable `FEATURE_MULTI_REGION=true` and configure one primary plus one secondary through `/api/v1/admin/regions`.
2. Store per-store endpoint references in `region_configs.endpoint_urls`; store credentials in the configured `SecretProvider`, not in the region row.
3. Start the `scheduler` profile. The replication probe runner writes `replication_statuses` for each component.
4. Open `/api/v1/regions/replication-status` and verify all seven components are present. Missing rows appear as explicit unhealthy gaps.
5. Create a maintenance window with `/api/v1/admin/maintenance/windows`, then enable it. Mutating HTTP verbs return `503` while reads pass.
6. Create a failover plan with typed steps and rehearse it before any production execution.

Probe mocks used by tests should accept arbitrary credential strings and expose lag-injection controls for PostgreSQL, Kafka, S3-compatible storage, ClickHouse, Qdrant, Neo4j, and OpenSearch. Never place real credentials in mock configuration.

