# Multi-region probe mocks

These mocks provide deterministic probe surfaces for feature 081 tests.

- `probe_mock_client()` returns an `httpx.AsyncClient` backed by an ASGI app.
- `/inject-lag/{component}` sets lag for Kafka, S3, ClickHouse, Qdrant, Neo4j, or OpenSearch.
- Store-specific endpoints return the same success and lag fields consumed by the probe adapters.
- `install_asyncpg_replication_mock()` installs an asyncpg-compatible PostgreSQL replication stub.

The mocks accept any credential string and never require or store real secrets.
