# Installation

This page covers deployment targets and the full environment-variable
reference. For quick local bring-up, see [Getting Started](getting-started.md).

## Deployment targets

musematic supports five deployment modes, selected by the `ops-cli`:

| Mode | Source | Notes |
|---|---|---|
| `kubernetes` | Helm charts under `deploy/helm/` | **Primary** target — production and staging. |
| `docker` | Single host, ad-hoc `docker run` | Dev and demos. |
| `docker-swarm` | `docker stack deploy` | Multi-host without Kubernetes. |
| `incus` / LXD | System containers | Bare-metal self-hosting. |
| `local` | Native processes | Development only. |

The target mode is set via `PLATFORM_CLI_DEPLOYMENT_MODE`
(default `kubernetes`), declared in
[`apps/ops-cli/src/platform_cli/config.py`][cli-cfg].

### Kubernetes (primary)

Helm charts ship under `deploy/helm/`. Operator-friendly defaults:

```bash
helm install musematic deploy/helm/platform \
  --namespace platform-control \
  --create-namespace \
  --values deploy/helm/platform/values.yaml
```

The chart depends on the following cluster operators being installed first:

| Operator | Purpose | Spec reference |
|---|---|---|
| CloudNativePG | PostgreSQL HA | [spec 001][s001] |
| Strimzi | Kafka with KRaft | [spec 003][s003] |

Other data stores (Qdrant, Neo4j, ClickHouse, OpenSearch, Redis, MinIO) are
deployed as StatefulSets via their official Helm charts. See the individual
infra specs ([004][s004]–[008][s008]) for operational detail.

### Docker / docker-compose

A reference docker-compose for local data stores has not yet been promoted
from test fixtures. TODO(andrea): document the canonical local-dev
compose file location once one is published at the repo root.

### Kubernetes namespaces

The platform uses six namespaces by convention (from
[`.specify/memory/constitution.md`][const]):

| Namespace | Contents |
|---|---|
| `platform-edge` | Ingress, API gateway, WebSocket gateway |
| `platform-control` | Control-plane pods (all profiles), BFFs |
| `platform-execution` | Runtime controller, reasoning engine, sandbox, connectors |
| `platform-simulation` | Simulation controller, simulation pods (network-isolated) |
| `platform-data` | Postgres, Qdrant, Neo4j, ClickHouse, Redis, OpenSearch, Kafka, MinIO |
| `platform-observability` | OTEL collector, Prometheus, Grafana, Jaeger |

## Environment variables

All settings below are declared in one of:

- `apps/control-plane/src/platform/common/config.py` (Pydantic Settings)
- `services/<go-service>/pkg/config/config.go` (Go `os.Getenv`)
- `apps/ops-cli/src/platform_cli/config.py` (CLI)
- `apps/web/.env.example` (frontend public vars)

Variables are grouped by category and alphabetised within each group.
Secrets are marked `secret` and must be supplied via Kubernetes Secret
objects (or `.env` files for dev) — **never** committed to git.

### Core platform — database

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `POSTGRES_DSN` | ✅ | `secret` | — | Postgres async DSN (`postgresql+asyncpg://user:pass@host:5432/db`). |
| `POSTGRES_MAX_OVERFLOW` | — | `int` | `10` | SQLAlchemy pool max overflow. |
| `POSTGRES_POOL_SIZE` | — | `int` | `20` | SQLAlchemy base pool size. |

### Core platform — Redis

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `REDIS_ADDR` | — | `str` | derived from `REDIS_URL` | Address used by Go services. |
| `REDIS_NODES` | — | `list[str]` | `[]` | Cluster node list (production). |
| `REDIS_PASSWORD` | — | `secret` | `""` | Redis auth password. |
| `REDIS_TEST_MODE` | — | `str` | `standalone` | `standalone` for tests, otherwise cluster. |
| `REDIS_URL` | — | `str` | `redis://localhost:6379` | Single-node Redis URL. |

### Core platform — Kafka

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `KAFKA_BROKERS` | — | `list[str]` | `["localhost:9092"]` | Bootstrap servers. |
| `KAFKA_CONSUMER_GROUP` | — | `str` | `platform` | Default consumer group. |
| `KAFKA_CONSUMER_GROUP_ID` | — | `str` | (alias) | Alias of the above; resolved at startup. |

### Core platform — object storage (S3 / MinIO)

All object storage access uses the generic S3 protocol.
MinIO is optional — any S3-compatible provider works (AWS S3, Hetzner, R2,
Wasabi, etc.). Principle XVI of the [constitution][const] forbids MinIO
references from application code.

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `MINIO_ACCESS_KEY` | — | `secret` | `minioadmin` | S3 access key. |
| `MINIO_BUCKET` | — | `str` | service-specific | Bucket name used by a Go service. |
| `MINIO_BUCKET_DEAD_LETTERS` | — | `str` | `connector-dead-letters` | DLQ archive bucket. |
| `MINIO_DEFAULT_BUCKET` | — | `str` | `platform-artifacts` | Default artifact bucket. |
| `MINIO_ENDPOINT` | — | `str` | `http://localhost:9000` | S3 endpoint URL. |
| `MINIO_SECRET_KEY` | — | `secret` | `minioadmin` | S3 secret key. |
| `MINIO_USE_SSL` | — | `bool` | `false` | Enable TLS. |

### Core platform — Qdrant (vector store)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `QDRANT_API_KEY` | — | `secret` | `""` | API key (optional). |
| `QDRANT_COLLECTION_DIMENSIONS` | — | `int` | `768` | Default vector dim for new collections. |
| `QDRANT_GRPC_PORT` | — | `int` | `6334` | gRPC port. |
| `QDRANT_HOST` | — | `str` | `localhost` | Hostname. |
| `QDRANT_PORT` | — | `int` | `6333` | HTTP port. |
| `QDRANT_URL` | — | `str` | derived | Full URL (computed from host/port). |

### Core platform — Neo4j (graph)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `GRAPH_MODE` | — | `str` | `auto` | `auto`, `native`, or `fulltext`. |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | — | `int` | `50` | Driver pool size. |
| `NEO4J_PASSWORD` | — | `secret` | `neo4j` | Driver password. |
| `NEO4J_URI` | — | `str` | `bolt://localhost:7687` | Bolt URL. |
| `NEO4J_URL` | — | `str` | (alias of `NEO4J_URI`) | Alias. |
| `NEO4J_USER` | — | `str` | `neo4j` | Driver user. |

### Core platform — ClickHouse (analytics)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `CLICKHOUSE_DATABASE` | — | `str` | `default` | Database name. |
| `CLICKHOUSE_HOST` | — | `str` | `localhost` | Hostname. |
| `CLICKHOUSE_INSERT_BATCH_SIZE` | — | `int` | `1000` | Batch size for inserts. |
| `CLICKHOUSE_INSERT_FLUSH_INTERVAL` | — | `float` | `5.0` | Flush interval (seconds). |
| `CLICKHOUSE_PASSWORD` | — | `secret` | `""` | Password. |
| `CLICKHOUSE_PORT` | — | `int` | `8123` | HTTP port. |
| `CLICKHOUSE_URL` | — | `str` | derived | HTTP base URL (computed). |
| `CLICKHOUSE_USER` | — | `str` | `default` | Username. |

### Core platform — OpenSearch (marketplace search)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `OPENSEARCH_CA_CERTS` | — | `str \| null` | `null` | Path to CA bundle. |
| `OPENSEARCH_HOSTS` | — | `str` | `http://localhost:9200` | Comma-separated endpoints. |
| `OPENSEARCH_PASSWORD` | — | `secret` | `""` | Auth password. |
| `OPENSEARCH_TIMEOUT` | — | `int` | `30` | Request timeout (seconds). |
| `OPENSEARCH_USERNAME` | — | `str` | `""` | Auth username. |
| `OPENSEARCH_USE_SSL` | — | `bool` | `false` | Enable TLS. |
| `OPENSEARCH_VERIFY_CERTS` | — | `bool` | `false` | Verify TLS certs. |

### Auth — sessions, JWT, MFA, lockout

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `AUTH_ACCESS_TOKEN_TTL` | — | `int` | `900` | Access-token lifetime (seconds, 15 min). |
| `AUTH_JWT_ALGORITHM` | — | `str` | `RS256` | Signing algorithm. |
| `AUTH_JWT_PRIVATE_KEY` | — | `secret` | `""` | RS256 private key PEM. |
| `AUTH_JWT_PUBLIC_KEY` | — | `secret` | `""` | RS256 public key PEM. |
| `AUTH_JWT_SECRET_KEY` | — | `secret` | `""` | Legacy HS256 key (deprecated). |
| `AUTH_LOCKOUT_DURATION` | — | `int` | `900` | Lockout window (seconds, 15 min). |
| `AUTH_LOCKOUT_THRESHOLD` | — | `int` | `5` | Failed logins before lockout. |
| `AUTH_MFA_ENCRYPTION_KEY` | — | `secret` | `""` | Fernet key for TOTP secrets. |
| `AUTH_MFA_ENROLLMENT_TTL` | — | `int` | `600` | MFA enrollment window (seconds, 10 min). |
| `AUTH_PASSWORD_RESET_TTL` | — | `int` | `3600` | Reset-link TTL (seconds, 1 hour). |
| `AUTH_REFRESH_TOKEN_TTL` | — | `int` | `604800` | Refresh-token lifetime (seconds, 7 days). |
| `AUTH_SESSION_TTL` | — | `int` | `604800` | Session lifetime (seconds, 7 days). |

### Accounts — signup & invitations

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `ACCOUNTS_EMAIL_VERIFY_TTL_HOURS` | — | `int` | `24` | Email verification TTL (hours). |
| `ACCOUNTS_INVITE_TTL_DAYS` | — | `int` | `7` | Invitation TTL (days). |
| `ACCOUNTS_RESEND_RATE_LIMIT` | — | `int` | `3` | Max resends per session. |
| `ACCOUNTS_SIGNUP_MODE` | — | `str` | `open` | `open`, `invite_only`, or `admin_approval`. |

### Workspaces

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `WORKSPACES_DEFAULT_LIMIT` | — | `int` | `0` | Per-user max workspaces (0 = unlimited). |
| `WORKSPACES_DEFAULT_NAME_TEMPLATE` | — | `str` | `{display_name}'s Workspace` | Auto-generated workspace name template. |

### WebSocket hub

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `WS_CLIENT_BUFFER_SIZE` | — | `int` | `1000` | Per-client outbound queue size. |
| `WS_HEARTBEAT_INTERVAL_SECONDS` | — | `int` | `30` | Ping interval. |
| `WS_HEARTBEAT_TIMEOUT_SECONDS` | — | `int` | `10` | Ping-response timeout. |
| `WS_MAX_MALFORMED_MESSAGES` | — | `int` | `10` | Disconnect threshold. |

### Observability — OTEL

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `OTEL_EXPORTER_ENDPOINT` | — | `str` | `""` | HTTP OTLP endpoint (Python). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | `str` | `""` | gRPC OTLP endpoint (Go). |
| `OTEL_RESOURCE_ATTRIBUTES` | — | `str` | `""` | Extra resource attributes. |
| `OTEL_SERVICE_NAME` | — | `str` | service-specific | Reported service name. |

### gRPC satellite addresses (control plane → Go services)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `GRPC_REASONING_ENGINE` | — | `str` | `localhost:50052` | Reasoning engine address. |
| `GRPC_RUNTIME_CONTROLLER` | — | `str` | `localhost:50051` | Runtime controller address. |
| `GRPC_SANDBOX_MANAGER` | — | `str` | `localhost:50053` | Sandbox manager address. |
| `GRPC_SIMULATION_CONTROLLER` | — | `str` | `localhost:50055` | Simulation controller address. |

### Runtime controller service

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `AGENT_PACKAGE_PRESIGN_TTL` | — | `duration` | `2h` | Presigned URL TTL for package pulls. |
| `GRPC_PORT` | — | `int` | `50051` | gRPC listen port. |
| `HEARTBEAT_CHECK_INTERVAL` | — | `duration` | `10s` | Heartbeat scan interval. |
| `HEARTBEAT_TIMEOUT` | — | `duration` | `60s` | Pod heartbeat liveness timeout. |
| `HTTP_PORT` | — | `int` | `8080` | HTTP liveness/metrics port. |
| `K8S_DRY_RUN` | — | `bool` | `false` | Skip actual k8s writes (tests). |
| `K8S_NAMESPACE` | — | `str` | `platform-execution` | Namespace for agent pods. |
| `KUBECONFIG` | — | `str` | `~/.kube/config` | Kube config path. |
| `RECONCILE_INTERVAL` | — | `duration` | `30s` | Reconciliation loop cadence. |
| `STOP_GRACE_PERIOD` | — | `duration` | `30s` | Pod termination grace. |
| `WARM_POOL_IDLE_TIMEOUT` | — | `duration` | `5m` | Evict idle warm pods. |
| `WARM_POOL_REPLENISH_INTERVAL` | — | `duration` | `30s` | Replenishment cadence. |
| `WARM_POOL_TARGETS` | — | `str` | `""` | `type1=count1,type2=count2` target mix. |

### Sandbox manager service

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `DEFAULT_TIMEOUT` | — | `duration` | `30s` | Default sandbox exec timeout. |
| `IDLE_TIMEOUT` | — | `duration` | `300s` | Sandbox idle eviction. |
| `MAX_CONCURRENT_SANDBOXES` | — | `int` | `50` | Concurrency cap. |
| `MAX_OUTPUT_SIZE` | — | `int` | `10485760` | Max captured output bytes (10 MiB). |
| `MAX_TIMEOUT` | — | `duration` | `300s` | Hard ceiling on requested timeouts. |
| `ORPHAN_SCAN_INTERVAL` | — | `duration` | `60s` | Orphan sandbox scanner cadence. |

### Reasoning engine service

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `BUDGET_DEFAULT_TTL_SECONDS` | — | `int` | `3600` | Default Redis budget TTL. |
| `MAX_TOT_CONCURRENCY` | — | `int` | `10` | Tree-of-Thought concurrent branches. |
| `TRACE_BUFFER_SIZE` | — | `int` | `10000` | Per-execution trace buffer. |
| `TRACE_PAYLOAD_THRESHOLD` | — | `int` | `65536` | Inline-vs-spill trace payload threshold (bytes). |

### Simulation controller service

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `DEFAULT_MAX_DURATION_SECONDS` | — | `int` | `3600` | Default simulation runtime cap. |
| `ORPHAN_SCAN_INTERVAL_SECONDS` | — | `int` | `60` | Orphan scanner cadence. |
| `SIMULATION_BUCKET` | — | `str` | `simulation-artifacts` | Artifact bucket. |
| `SIMULATION_NAMESPACE` | — | `str` | `platform-simulation` | Kubernetes namespace. |

### Registry — agent packages & search

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `REGISTRY_EMBEDDINGS_COLLECTION` | — | `str` | `agent_embeddings` | Qdrant collection. |
| `REGISTRY_EMBEDDING_API_URL` | — | `str` | `http://localhost:8081/v1/embeddings` | Embedding service URL. |
| `REGISTRY_EMBEDDING_VECTOR_SIZE` | — | `int` | `1536` | Embedding dim. |
| `REGISTRY_MAX_DIRECTORY_DEPTH` | — | `int` | `10` | Max nesting inside uploaded package. |
| `REGISTRY_MAX_FILE_COUNT` | — | `int` | `256` | Max files per package. |
| `REGISTRY_PACKAGE_BUCKET` | — | `str` | `agent-packages` | S3 bucket for packages. |
| `REGISTRY_PACKAGE_SIZE_LIMIT_MB` | — | `int` | `50` | Max package size (MB). |
| `REGISTRY_REINDEX_POLL_INTERVAL_SECONDS` | — | `int` | `30` | Reindex scanner cadence. |
| `REGISTRY_SEARCH_BACKING_INDEX` | — | `str` | `marketplace-agents-000001` | OpenSearch backing index. |
| `REGISTRY_SEARCH_INDEX` | — | `str` | `marketplace-agents` | OpenSearch alias. |

### Memory subsystem

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `MEMORY_CONSOLIDATION_CLUSTER_THRESHOLD` | — | `float` | `0.85` | Similarity threshold for cluster merge. |
| `MEMORY_CONSOLIDATION_ENABLED` | — | `bool` | `true` | Enable the consolidation worker. |
| `MEMORY_CONSOLIDATION_INTERVAL_MINUTES` | — | `int` | `15` | Worker cadence. |
| `MEMORY_CONSOLIDATION_LLM_ENABLED` | — | `bool` | `false` | Use LLM for summarisation step. |
| `MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE` | — | `int` | `3` | Minimum entries to form a cluster. |
| `MEMORY_CONTRADICTION_EDIT_DISTANCE_THRESHOLD` | — | `float` | `0.15` | Contradiction edit-distance gate. |
| `MEMORY_CONTRADICTION_SIMILARITY_THRESHOLD` | — | `float` | `0.90` | Contradiction similarity gate. |
| `MEMORY_DIFFERENTIAL_PRIVACY_ENABLED` | — | `bool` | `false` | Apply differential privacy noise. |
| `MEMORY_DIFFERENTIAL_PRIVACY_EPSILON` | — | `float` | `1.0` | DP epsilon. |
| `MEMORY_EMBEDDING_API_URL` | — | `str` | `http://localhost:8081/v1/embeddings` | Embedding service. |
| `MEMORY_EMBEDDING_DIMENSIONS` | — | `int` | `1536` | Vector dim. |
| `MEMORY_EMBEDDING_MODEL` | — | `str` | `text-embedding-3-small` | Embedding model ID. |
| `MEMORY_RATE_LIMIT_PER_HOUR` | — | `int` | `500` | Per-user embed calls per hour. |
| `MEMORY_RATE_LIMIT_PER_MIN` | — | `int` | `60` | Per-user embed calls per minute. |
| `MEMORY_RECENCY_DECAY` | — | `float` | `0.08` | Recency weighting decay. |
| `MEMORY_RRF_K` | — | `int` | `60` | Reciprocal-rank-fusion parameter. |
| `MEMORY_SESSION_CLEANER_INTERVAL_MINUTES` | — | `int` | `60` | Session cleaner cadence. |

### Context engineering

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `CONTEXT_ENGINEERING_BUNDLE_BUCKET` | — | `str` | `context-assembly-records` | S3 bucket for assembly records. |
| `CONTEXT_ENGINEERING_DRIFT_RECENT_HOURS` | — | `int` | `24` | Drift "recent" window. |
| `CONTEXT_ENGINEERING_DRIFT_SCHEDULE_MINUTES` | — | `int` | `5` | Drift scanner cadence. |
| `CONTEXT_ENGINEERING_DRIFT_STDDEV_MULTIPLIER` | — | `float` | `2.0` | Drift detection σ multiplier. |
| `CONTEXT_ENGINEERING_DRIFT_WINDOW_DAYS` | — | `int` | `7` | Drift baseline window. |
| `CONTEXT_ENGINEERING_POLICY_CACHE_TTL_SECONDS` | — | `int` | `60` | Policy cache TTL. |
| `CONTEXT_ENGINEERING_QUALITY_SCORES_TABLE` | — | `str` | `context_quality_scores` | ClickHouse table. |

### Interactions & conversations

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `INTERACTIONS_DEFAULT_PAGE_SIZE` | — | `int` | `20` | Default list page size. |
| `INTERACTIONS_MAX_MESSAGES_PER_CONVERSATION` | — | `int` | `10000` | Conversation message cap. |

### Connectors (Slack, Telegram, Email, Webhook)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `CONNECTOR_DELIVERY_CONSUMER_GROUP` | — | `str` | `connector-delivery-worker` | Kafka consumer group. |
| `CONNECTOR_DELIVERY_MAX_CONCURRENT` | — | `int` | `10` | Max concurrent deliveries. |
| `CONNECTOR_DELIVERY_TOPIC` | — | `str` | `connector.delivery` | Outbound topic. |
| `CONNECTOR_EMAIL_POLL_INTERVAL_SECONDS` | — | `int` | `60` | IMAP poll cadence. |
| `CONNECTOR_INGRESS_TOPIC` | — | `str` | `connector.ingress` | Inbound topic. |
| `CONNECTOR_MAX_PAYLOAD_SIZE_BYTES` | — | `int` | `1048576` | Max payload (1 MiB). |
| `CONNECTOR_RETRY_SCAN_INTERVAL_SECONDS` | — | `int` | `30` | Retry scanner cadence. |
| `CONNECTOR_ROUTE_CACHE_TTL_SECONDS` | — | `int` | `60` | Route cache TTL. |
| `CONNECTOR_WORKER_ENABLED` | — | `bool` | `true` | Enable delivery worker. |
| `EMAIL_POLL_INTERVAL_SECONDS` | — | `int` | `60` | Alias. |
| `VAULT_MOCK_SECRETS_FILE` | — | `str` | `.vault-secrets.json` | Mock vault file path. |
| `VAULT_MODE` | — | `str` | `mock` | `mock` or `vault` (HashiCorp not yet implemented). |

### Trust & certification

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `TRUST_ATTENTION_TARGET_IDENTITY` | — | `str` | `platform_admin` | Role alerted on trust events. |
| `TRUST_DEFAULT_WORKSPACE_ID` | — | `str` | `00000000-0000-0000-0000-000000000000` | Default workspace for certifications. |
| `TRUST_EVIDENCE_BUCKET` | — | `str` | `trust-evidence` | S3 bucket for evidence. |
| `TRUST_OUTPUT_MODERATION_URL` | — | `str` | `""` | External moderator URL. |
| `TRUST_RECERTIFICATION_EXPIRY_THRESHOLD_DAYS` | — | `int` | `30` | Alert N days before cert expiry. |

### AgentOps

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `AGENTOPS_CANARY_MAX_TRAFFIC_PCT` | — | `int` | `50` | Max canary traffic percentage. |
| `AGENTOPS_CANARY_MONITOR_INTERVAL_MINUTES` | — | `int` | `5` | Canary monitor cadence. |
| `AGENTOPS_DEFAULT_MIN_SAMPLE_SIZE` | — | `int` | `50` | Min samples for health scoring. |
| `AGENTOPS_DEFAULT_ROLLING_WINDOW_DAYS` | — | `int` | `30` | Rolling window for health metrics. |
| `AGENTOPS_HEALTH_SCORING_INTERVAL_MINUTES` | — | `int` | `15` | Health scoring cadence. |
| `AGENTOPS_RECERTIFICATION_GRACE_PERIOD_DAYS` | — | `int` | `7` | Grace period for recert. |
| `AGENTOPS_REGRESSION_NORMALITY_SAMPLE_MIN` | — | `int` | `30` | Min samples for normality test. |
| `AGENTOPS_REGRESSION_SIGNIFICANCE_THRESHOLD` | — | `float` | `0.05` | α for regression significance. |
| `AGENTOPS_RETIREMENT_CRITICAL_INTERVALS` | — | `int` | `5` | Critical intervals before retirement. |
| `AGENTOPS_RETIREMENT_GRACE_PERIOD_DAYS` | — | `int` | `14` | Grace period before retirement. |

### Composition (agent-builds-agent)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `COMPOSITION_DESCRIPTION_MAX_CHARS` | — | `int` | `10000` | Max purpose/approach length. |
| `COMPOSITION_LLM_API_URL` | — | `str` | `http://localhost:8080/v1/chat/completions` | LLM endpoint. |
| `COMPOSITION_LLM_MAX_RETRIES` | — | `int` | `2` | LLM retry count. |
| `COMPOSITION_LLM_MODEL` | — | `str` | `claude-opus-4-6` | Model identifier. |
| `COMPOSITION_LLM_TIMEOUT_SECONDS` | — | `float` | `25.0` | LLM request timeout. |
| `COMPOSITION_LOW_CONFIDENCE_THRESHOLD` | — | `float` | `0.5` | Validation gate. |
| `COMPOSITION_VALIDATION_TIMEOUT_SECONDS` | — | `float` | `10.0` | Validation request timeout. |

### Discovery (scientific hypothesis)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `DISCOVERY_CONVERGENCE_STABLE_ROUNDS` | — | `int` | `2` | Rounds of stability for convergence. |
| `DISCOVERY_CONVERGENCE_THRESHOLD` | — | `float` | `0.05` | Convergence delta threshold. |
| `DISCOVERY_ELO_DEFAULT_SCORE` | — | `float` | `1000.0` | Initial Elo score. |
| `DISCOVERY_ELO_K_FACTOR` | — | `int` | `32` | Elo K-factor. |
| `DISCOVERY_EMBEDDING_VECTOR_SIZE` | — | `int` | `1536` | Hypothesis embedding dim. |
| `DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS` | — | `int` | `120` | Experiment sandbox timeout. |
| `DISCOVERY_MAX_CYCLES_DEFAULT` | — | `int` | `10` | Default exploration cycle cap. |
| `DISCOVERY_MIN_HYPOTHESES` | — | `int` | `3` | Minimum hypotheses per exploration. |
| `DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD` | — | `float` | `0.3` | Cluster radius. |
| `DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD` | — | `float` | `0.5` | Gap detection distance. |
| `DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE` | — | `int` | `5` | Over-exploration minimum size. |
| `DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY` | — | `float` | `0.85` | Over-exploration similarity. |
| `DISCOVERY_QDRANT_COLLECTION` | — | `str` | `discovery_hypotheses` | Qdrant collection. |

### Simulation

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `SIMULATION_BEHAVIORAL_HISTORY_DAYS` | — | `int` | `30` | Behavior history window. |
| `SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA` | — | `float` | `0.05` | α for comparison tests. |
| `SIMULATION_DEFAULT_STRICT_ISOLATION` | — | `bool` | `true` | Strict network isolation by default. |
| `SIMULATION_MAX_DURATION_SECONDS` | — | `int` | `1800` | Per-simulation cap (30 min). |
| `SIMULATION_MIN_PREDICTION_HISTORY_DAYS` | — | `int` | `7` | Min history for predictions. |
| `SIMULATION_PREDICTION_WORKER_INTERVAL_SECONDS` | — | `int` | `30` | Prediction worker cadence. |

### Analytics / cost

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `ANALYTICS_BUDGET_THRESHOLD_USD` | — | `float` | `0.0` | Budget alert threshold in USD (0 disables). |

### Feature flags

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `MEMORY_CONSOLIDATION_ENABLED` | — | `bool` | `true` | See above. |
| `MEMORY_CONSOLIDATION_LLM_ENABLED` | — | `bool` | `false` | See above. |
| `MEMORY_DIFFERENTIAL_PRIVACY_ENABLED` | — | `bool` | `false` | See above. |
| `CONNECTOR_WORKER_ENABLED` | — | `bool` | `true` | See above. |
| `SIMULATION_DEFAULT_STRICT_ISOLATION` | — | `bool` | `true` | See above. |
| `VISIBILITY_ZERO_TRUST_ENABLED` | — | `bool` | `false` | Enforce zero-trust visibility for existing workspaces. |

### Platform profile (runtime selector)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `PLATFORM_PROFILE` | — | `str` | `api` | Runtime profile — `api`, `ws-hub`, `worker`, `scheduler`, `cli`, etc. |
| `RUNTIME_PROFILE` | — | `str` | (alias) | Alias of `PLATFORM_PROFILE`. |

### Operations CLI

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `PLATFORM_CLI_AIR_GAPPED` | — | `bool` | `false` | Enable air-gapped install flow. |
| `PLATFORM_CLI_DATA_DIR` | — | `str` | `~/.platform-cli/data` | CLI data directory. |
| `PLATFORM_CLI_DEPLOYMENT_MODE` | — | `str` | `kubernetes` | Target deploy mode. |
| `PLATFORM_CLI_IMAGE_REGISTRY` | — | `str` | `ghcr.io` | Container registry. |
| `PLATFORM_CLI_IMAGE_TAG` | — | `str` | `latest` | Image tag. |
| `PLATFORM_CLI_NAMESPACE` | — | `str` | `platform` | Target namespace. |
| `PLATFORM_CLI_STORAGE_CLASS` | — | `str` | `standard` | Default PVC storage class. |

### Web frontend (`apps/web/.env.example`)

| Name | Required | Type | Default | Purpose |
|---|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | — | `str` | `http://localhost:8000` | Control-plane base URL. |
| `NEXT_PUBLIC_APP_ENV` | — | `str` | `development` | Environment label. |
| `NEXT_PUBLIC_WS_URL` | — | `str` | `ws://localhost:8000/ws` | WebSocket URL. |

## Secrets handling

- Secrets live in Kubernetes `Secret` objects, referenced by
  `ConfigMap` + `Secret` envFrom refs in the Helm chart.
- For dev, use a `.env` file loaded by `pydantic-settings` — **never commit
  it**. The repo ships a pre-commit check with `gitleaks` (`.gitleaks.toml`)
  to catch accidental commits.
- `AUTH_JWT_PRIVATE_KEY`, `AUTH_JWT_PUBLIC_KEY`, and
  `AUTH_MFA_ENCRYPTION_KEY` MUST be rotated at platform creation time —
  the defaults are empty strings for safety.
- Connector credentials (`CONNECTOR_SECRET_*`) resolve through the vault
  abstraction — see
  [Administration › Integrations & Credentials](administration/integrations-and-credentials.md).

## Troubleshooting

TODO(andrea): the repo ships individual service-level troubleshooting notes
in `specs/<feature>/quickstart.md`; a consolidated troubleshooting guide has
not yet been authored. Typical failure modes worth testing locally:

- **`POSTGRES_DSN` not reachable** — migrations fail immediately with
  `Connection refused`. Verify the container port is exposed.
- **Kafka not reachable** — API comes up, but `POST /api/v1/executions`
  stalls and logs `KafkaError: Broker not available`.
- **MFA enrollment fails** — `AUTH_MFA_ENCRYPTION_KEY` must be a
  Fernet-valid (44-char urlsafe base64) key.
- **Agent registration rejects FQN** — see
  [Agents › FQN validation rules](agents.md#fqn-validation).

[cli-cfg]: https://github.com/gntik-ai/musematic/blob/main/apps/ops-cli/src/platform_cli/config.py
[const]: https://github.com/gntik-ai/musematic/blob/main/.specify/memory/constitution.md
[s001]: https://github.com/gntik-ai/musematic/tree/main/specs/001-postgresql-schema-foundation
[s003]: https://github.com/gntik-ai/musematic/tree/main/specs/003-kafka-event-backbone
[s004]: https://github.com/gntik-ai/musematic/tree/main/specs/004-minio-object-storage
[s008]: https://github.com/gntik-ai/musematic/tree/main/specs/008-opensearch-full-text-search
