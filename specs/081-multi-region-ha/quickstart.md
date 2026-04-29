# Quickstart: Multi-Region Operations

1. Enable `FEATURE_MULTI_REGION=true` and configure one primary plus one secondary through `/api/v1/admin/regions`.
2. Store per-store endpoint references in `region_configs.endpoint_urls`; store credentials in the configured `SecretProvider`, not in the region row.
3. Start the `scheduler` profile. The replication probe runner writes `replication_statuses` for each component.
4. Open `/api/v1/regions/replication-status` and verify all seven components are present. Missing rows appear as explicit unhealthy gaps.
5. Create a maintenance window with `/api/v1/admin/maintenance/windows`, then enable it. Mutating HTTP verbs return `503` while reads pass.
6. Create a failover plan with typed steps and rehearse it before any production execution.

Probe mocks used by tests should accept arbitrary credential strings and expose lag-injection controls for PostgreSQL, Kafka, S3-compatible storage, ClickHouse, Qdrant, Neo4j, and OpenSearch. Never place real credentials in mock configuration.

## Provider Mock Smoke

Use `tests/fixtures/multi_region_ops/probe_mocks/` when a local environment does not have real secondary data stores:

1. Create an ASGI-backed mock client with `probe_mock_client()`.
2. Set lag with `POST /inject-lag/{component}` for `kafka`, `s3`, `clickhouse`, `qdrant`, `neo4j`, or `opensearch`.
3. Use `AsyncpgReplicationMock(lag_seconds=N)` for PostgreSQL `pg_stat_replication` probes.
4. Point test-only endpoint references at the mock routes. The mocks accept arbitrary credential strings and never require real secrets.

Smoke commands:

```sh
cd apps/control-plane
pytest tests/integration/multi_region_ops/test_probe_mocks_smoke.py --run-integration -q
pytest tests/integration/multi_region_ops --run-integration -q
```

Full local control-plane smoke after `make dev-up`:

```sh
cd tests/e2e
PLATFORM_API_URL=http://localhost:8081 .venv/bin/python -m pytest journeys/test_j11_multi_region_journey.py -v -m j11_multi_region_journey
```

The local walkthrough should pass with `FEATURE_MULTI_REGION=true` and `FEATURE_MAINTENANCE_MODE=true`: declare a secondary, inject lag through the mock, observe the RPO alert, schedule and enable maintenance, verify mutating writes return `503`, disable maintenance, then rehearse a failover plan.
