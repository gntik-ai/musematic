# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-09

## Active Technologies
- Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client) + `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart (002-redis-cache-hot-state)
- Redis 7 with AOF persistence (append-only file, fsync every second) (002-redis-cache-hot-state)

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
- 002-redis-cache-hot-state: Added Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client) + `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart

- HEAD: Added Python 3.12+ (application), PostgreSQL 16 (database) + SQLAlchemy 2.x (async ORM), Alembic (migrations), asyncpg (async PostgreSQL driver), CloudNativePG operator (Kubernetes)

<!-- MANUAL ADDITIONS START -->
- Database session import path: `from platform.common.database import get_async_session`
- Mixin composition convention:
  `Base` first, then behavior mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`), then concrete columns
- Migration workflow:
  `make migrate`
  `make migrate-rollback`
  `make migrate-create NAME=add_feature`
  `make migrate-check`
- PostgreSQL routing:
  application traffic goes through `musematic-pooler:5432` in production
  migrations and admin operations go directly to `musematic-postgres-rw:5432`
- Redis client import path: `from platform.common.clients.redis import AsyncRedisClient`
- Redis initialization:
  production uses cluster-aware nodes such as `["musematic-redis-cluster.platform-data:6379"]`
  tests use `REDIS_TEST_MODE=standalone` plus `REDIS_URL=redis://host:port`
- Redis key namespaces:
  `session:{user}:{session}`
  `budget:{execution}:{step}`
  `ratelimit:{resource}:{key}`
  `lock:{resource}:{id}`
  `leaderboard:{tournament}`
  `cache:{context}:{key}`
- Redis Lua scripts:
  `budget_decrement.lua` for atomic budget enforcement
  `rate_limit_check.lua` for sliding-window limits
  `lock_acquire.lua` and `lock_release.lua` for token-verified locks
<!-- MANUAL ADDITIONS END -->
