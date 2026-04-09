# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-09

## Active Technologies
- Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client) + `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart (002-redis-cache-hot-state)
- Redis 7 with AOF persistence (append-only file, fsync every second) (002-redis-cache-hot-state)
- Python 3.12+ (control plane), Go 1.22+ (reasoning engine) + aiokafka 0.11+ (Python producer/consumer), confluent-kafka-go v2 (Go producer), Strimzi operator (Kubernetes Kafka), Helm 3.x (003-kafka-event-backbone)
- Apache Kafka 3.7+ with KRaft consensus (no ZooKeeper) (003-kafka-event-backbone)
- Python 3.12+ (control plane client) + aioboto3 latest (Python async S3 client), MinIO Operator (Kubernetes), Helm 3.x (004-minio-object-storage)
- MinIO (S3-compatible object storage) (004-minio-object-storage)

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
- 004-minio-object-storage: Added Python 3.12+ (control plane client) + aioboto3 latest (Python async S3 client), MinIO Operator (Kubernetes), Helm 3.x
- 003-kafka-event-backbone: Added Python 3.12+ (control plane), Go 1.22+ (reasoning engine) + aiokafka 0.11+ (Python producer/consumer), confluent-kafka-go v2 (Go producer), Strimzi operator (Kubernetes Kafka), Helm 3.x
- 002-redis-cache-hot-state: Added Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client) + `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart


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
