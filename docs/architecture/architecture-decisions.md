# Architecture Decisions

This page summarizes the constitutional and audit-pass decisions that shape the system.

| Decision | Summary |
| --- | --- |
| AD-1 | Kubernetes is the primary deployment target. |
| AD-2 | The control plane starts as a modular monolith with extraction-ready bounded contexts. |
| AD-3 | Kafka is the asynchronous event backbone. |
| AD-4 | PostgreSQL stores transactional source-of-truth data. |
| AD-5 | Redis is used only for hot state, locks, counters, and caches. |
| AD-6 | MinIO/S3 stores artifacts, backups, and large evidence payloads. |
| AD-7 | ClickHouse is used for analytics and cost rollups. |
| AD-8 | Qdrant handles vector search workloads. |
| AD-9 | Neo4j handles graph workloads. |
| AD-10 | OpenSearch handles full-text search and selected indexed payloads. |
| AD-11 | Runtime execution is delegated to satellite services through gRPC. |
| AD-12 | WebSockets provide realtime client updates. |
| AD-13 | GID and correlation ID are first-class observability dimensions. |
| AD-14 | Secrets are stored by reference and resolved through providers. |
| AD-15 | Audit evidence is append-only and cryptographically verifiable. |
| AD-16 | Policy enforcement is fail-safe for protected actions. |
| AD-17 | Zero-trust visibility is default-deny. |
| AD-18 | Localization is limited to user-facing docs unless a section is explicitly localized. |
| AD-19 | OpenAPI snapshots are generated and checked for drift. |
| AD-20 | Helm value docs are generated from chart annotations. |
| AD-21 | Runbooks are checked into documentation and linked from incident response. |
| AD-22 | Logs route through Promtail to Loki, not through OTEL Collector. |
| AD-23 | External verification gates remain documented when they require cloud accounts or vendors. |

Audit-pass additions for recent features add cost governance, incident response, multi-region operations, log aggregation, public signup, and multilingual documentation controls.
