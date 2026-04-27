# Dashboards Reference

The observability stack ships dashboards from feature 084 plus the trust content moderation dashboard from feature 078. Dashboard names may vary by folder, but the operational intent should remain stable.

| Dashboard | Purpose | Key Panels | On-Call Relevance |
| --- | --- | --- | --- |
| Platform Overview | End-to-end platform health. | Request rate, error rate, latency, runtime status. | First stop during broad incidents. |
| Control Plane API | FastAPI API health. | `5xx`, latency, route saturation. | Confirms API impact. |
| Auth and Sessions | Login, MFA, OAuth, sessions. | Failed auth, lockouts, OAuth errors. | Used for access incidents. |
| Accounts and Signup | Signup and approval flow. | Signup rate, resend rate, pending approvals. | Validates FR-588 controls. |
| Workspaces | Workspace activity and goals. | Goal changes, membership events. | Narrows tenant impact. |
| Workflow Execution | Execution scheduler and state. | Running, failed, waiting approval. | Core workflow triage. |
| Runtime Controller | Runtime pod lifecycle. | Dispatch latency, orphan pods. | Runtime capacity incidents. |
| Reasoning Engine | Reasoning branch and budget behavior. | Branch count, convergence, budget. | Cost and quality issues. |
| Sandbox Manager | Code execution sandbox health. | Pod starts, failures, artifact latency. | Tool execution failures. |
| Simulation Controller | Simulation runs and isolation. | Run state, artifact upload, failures. | Simulation incidents. |
| Kafka Backbone | Broker and topic health. | Consumer lag, ISR, throughput. | Event pipeline failures. |
| Redis Hot State | Cache and locks. | Command latency, errors, memory. | Lock/rate-limit/session issues. |
| PostgreSQL | Database health. | Connections, locks, replication. | Persistence incidents. |
| MinIO Object Storage | Artifact and backup storage. | Request errors, bucket growth. | Artifact or backup failures. |
| Qdrant Vector Search | Vector search health. | Search latency, collection size. | Memory/search incidents. |
| Neo4j Knowledge Graph | Graph database health. | Query latency, heap, page cache. | Knowledge graph incidents. |
| OpenSearch | Full-text search and logs indexes. | Index health, search errors. | Search and audit lookup issues. |
| ClickHouse Analytics | Analytics ingestion and queries. | Insert rate, query latency, disk. | Cost/analytics incidents. |
| Loki Logs | Log ingestion and retention. | Ingest rate, chunk errors, retention. | Log loss incidents. |
| Promtail | Log shipping agents. | Scrape errors, dropped lines. | Node log gaps. |
| Jaeger Tracing | Trace ingestion and query. | Span rate, collector errors. | Trace gaps. |
| Alertmanager | Alert delivery and silencing. | Firing alerts, notifications. | Incident routing. |
| Trust Content Moderation | Moderation decisions and provider health. | Block rate, provider errors, fairness alerts. | Safety incidents. |

Use the GID or correlation ID from user reports to jump between dashboards, logs, traces, and audit records.
