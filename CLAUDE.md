# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-10

## Active Technologies
- Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client) + `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart (002-redis-cache-hot-state)
- Redis 7 with AOF persistence (append-only file, fsync every second) (002-redis-cache-hot-state)
- Python 3.12+ (control plane), Go 1.22+ (reasoning engine) + aiokafka 0.11+ (Python producer/consumer), confluent-kafka-go v2 (Go producer), Strimzi operator (Kubernetes Kafka), Helm 3.x (003-kafka-event-backbone)
- Apache Kafka 3.7+ with KRaft consensus (no ZooKeeper) (003-kafka-event-backbone)
- Python 3.12+ (control plane client) + aioboto3 latest (Python async S3 client), MinIO Operator (Kubernetes), Helm 3.x (004-minio-object-storage)
- MinIO (S3-compatible object storage) (004-minio-object-storage)
- Python 3.12+ + qdrant-client[grpc] 1.12+ (Python async gRPC client), Helm 3.x (Qdrant official chart: qdrant/qdrant) (005-qdrant-vector-search)
- Qdrant (vector search engine, deployed as StatefulSet — no operator) (005-qdrant-vector-search)
- Python 3.12+ + `neo4j-python-driver 5.x` (`AsyncGraphDatabase`), Helm 3.x (`neo4j/neo4j` official chart), APOC plugin (via `NEO4J_PLUGINS` env var) (006-neo4j-knowledge-graph)
- Neo4j 5.x (graph database, StatefulSet — no operator) (006-neo4j-knowledge-graph)
- Python 3.12+ + `clickhouse-connect 0.8+` (HTTP interface), Helm 3.x (custom chart), `altinity/clickhouse-backup` (backup tool) (007-clickhouse-analytics)
- ClickHouse 24.3+ (OLAP database, StatefulSet — no operator) + ClickHouse Keeper (Raft consensus, separate StatefulSet) (007-clickhouse-analytics)
- Python 3.12+ + `opensearch-py 2.x` (`AsyncOpenSearch`), Helm 3.x (wrapper chart: opensearch-project/opensearch + opensearch-dashboards deps), ICU plugin via init container (008-opensearch-full-text-search)
- OpenSearch 2.18.x (full-text search, StatefulSet — no operator) + OpenSearch Dashboards (separate Deployment); ISM for lifecycle policies; Snapshot Management (SM) for backups to MinIO (008-opensearch-full-text-search)
- Go 1.22+ + `client-go 0.31+` (Kubernetes pod management), `google.golang.org/grpc 1.67+` (gRPC server), `pgx/v5` (PostgreSQL), `go-redis/v9` (heartbeat TTL), `confluent-kafka-go/v2` (events), `aws-sdk-go-v2` (MinIO artifacts), multi-stage distroless Docker image (<100MB) (009-runtime-controller)
- Runtime Controller Go satellite service (`services/runtime-controller/`): gRPC RuntimeControlService (7 RPCs), reconciliation loop (30s), heartbeat scanner (Redis TTL 60s), warm pool (in-memory + PostgreSQL), secrets isolation (Kubernetes projected volumes), TaskPlanRecord persistence (PostgreSQL + MinIO) (009-runtime-controller)
- Go 1.22+ + `client-go 0.31+` (Kubernetes pod management + remotecommand exec), `google.golang.org/grpc 1.67+` (gRPC server), `pgx/v5` (PostgreSQL), `confluent-kafka-go/v2` (events), `aws-sdk-go-v2` (MinIO artifacts), multi-stage distroless Docker image (<50MB) (010-sandbox-manager)
- Sandbox Manager Go satellite service (`services/sandbox-manager/`): gRPC SandboxService (5 RPCs), remotecommand pod exec for code execution, 4 templates (python3.12, node20, go1.22, code-as-reasoning), security hardening (UID 65534, drop ALL caps, read-only rootfs, deny-all NetworkPolicy), in-memory state + PostgreSQL metadata, orphan scanner (010-sandbox-manager)
- Go 1.22+ + `google.golang.org/grpc 1.67+` (gRPC server), `go-redis/v9` (Redis budget hot state), `pgx/v5` (PostgreSQL), `confluent-kafka-go/v2` (events), `aws-sdk-go-v2` (MinIO payloads), multi-stage distroless Docker image (<50MB) (011-reasoning-engine)
- Reasoning Engine Go satellite service (`services/reasoning-engine/`): gRPC ReasoningEngineService (9 RPCs) on port 50052, Redis Lua scripts (EVALSHA) for atomic budget tracking, goroutine pool + bounded semaphore for tree-of-thought branches, client-streaming gRPC for CoT traces, rule-based mode selector (6 modes), two-sample convergence window, fan-out registry for budget event streaming (011-reasoning-engine)

- Python 3.12+ (application), PostgreSQL 16 (database) + SQLAlchemy 2.x (async ORM), Alembic (migrations), asyncpg (async PostgreSQL driver), CloudNativePG operator (Kubernetes) (HEAD)

## Project Structure

```text
src/
tests/
```

## Commands

cd src && pytest && ruff check .

## Code Style

Python 3.12+ (application), PostgreSQL 16 (database): Follow standard conventions

## Recent Changes
- 011-reasoning-engine: Added Go 1.22+ satellite service — gRPC ReasoningEngineService (9 RPCs, port 50052), Redis Lua EVALSHA for atomic budget tracking, goroutine pool for ToT branch management, client-streaming gRPC for CoT traces, rule-based mode selector, two-sample convergence detection
- 010-sandbox-manager: Added Go 1.22+ satellite service — gRPC SandboxService (5 RPCs), remotecommand pod exec, 4 sandbox templates, max security hardening (non-root, read-only rootfs, no caps, deny-all network), in-memory state + PostgreSQL metadata
- 009-runtime-controller: Added Go 1.22+ satellite service — gRPC RuntimeControlService, client-go pod lifecycle, Redis heartbeat TTL, warm pool, secrets isolation (projected volumes), TaskPlanRecord persistence


<!-- MANUAL ADDITIONS START -->
  `Base` first, then behavior mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`), then concrete columns
  `make migrate`
  `make migrate-rollback`
  `make migrate-create NAME=add_feature`
  `make migrate-check`
  application traffic goes through `musematic-pooler:5432` in production
  migrations and admin operations go directly to `musematic-postgres-rw:5432`
  production uses cluster-aware nodes such as `["musematic-redis-cluster.platform-data:6379"]`
  tests use `REDIS_TEST_MODE=standalone` plus `REDIS_URL=redis://host:port`
  `session:{user}:{session}`
  `budget:{execution}:{step}`
  `ratelimit:{resource}:{key}`
  `lock:{resource}:{id}`
  `leaderboard:{tournament}`
  `cache:{context}:{key}`
  `budget_decrement.lua` for atomic budget enforcement
  `rate_limit_check.lua` for sliding-window limits
  `lock_acquire.lua` and `lock_release.lua` for token-verified locks
<!-- MANUAL ADDITIONS END -->
