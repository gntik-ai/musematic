# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-11

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
- Go 1.22+ + `client-go 0.31+` (Kubernetes pod lifecycle in `platform-simulation`), `google.golang.org/grpc 1.67+` (gRPC server), `pgx/v5` (PostgreSQL), `confluent-kafka-go/v2` (events), `aws-sdk-go-v2` (MinIO simulation-artifacts bucket), multi-stage distroless Docker image (<50MB) (012-simulation-controller)
- Simulation Controller Go satellite service (`services/simulation-controller/`): gRPC SimulationControlService (6 RPCs) on port 50055, `platform-simulation` namespace isolation, NetworkPolicy deny-all production egress, remotecommand tar artifact collection, Kafka `simulation.events` topic, ATE with ConfigMap-injected scenarios, in-memory state + PostgreSQL, orphan scanner (012-simulation-controller)
- Python 3.12+ + FastAPI 0.115+ (app factory with lifespan), Pydantic v2 (settings + schemas), SQLAlchemy 2.x async (`AsyncSession` + 6 mixins), aiokafka 0.11+ (producer/consumer/DLQ), redis-py 5.x async, grpcio 1.65+ (4 satellite clients), PyJWT 2.x RS256, opentelemetry-sdk 1.27+ (013-fastapi-app-scaffold)
- FastAPI Application Scaffold (`apps/control-plane/src/platform/common/`): app factory, PlatformSettings, canonical EventEnvelope + event type registry + DLQ, correlation ID + JWT auth middleware, 10 client wrappers (8 stores + 4 gRPC satellites), PlatformError exception hierarchy, cursor/offset pagination, 8 runtime profile entrypoints (013-fastapi-app-scaffold)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, argon2-cffi 23+ (Argon2id, OWASP params), PyJWT 2.x RS256 (15min access + 7d refresh), pyotp 2.x (TOTP MFA), redis-py 5.x async (sessions + lockout), aiokafka 0.11+ (auth events), cryptography (Fernet for TOTP secret encryption) (014-auth-bounded-context)
- Auth Bounded Context (`apps/control-plane/src/platform/auth/`): email/password login with Argon2id, RS256 JWT pair (access+refresh), Redis-backed sessions (`session:{user_id}:{session_id}`), TOTP MFA with encrypted secrets + recovery codes, account lockout via Redis counters (`auth:lockout:{user_id}`, `auth:locked:{user_id}`), RBAC engine with 10 roles + workspace-scoped permissions, purpose-bound agent authorization, service account API keys (`msk_` prefix, Argon2id hashed), 7 REST endpoints, 6 Kafka event types on `auth.events` topic (014-auth-bounded-context)
- TypeScript 5.x + Next.js 14+ App Router, React 18+, shadcn/ui (ALL UI primitives), Tailwind CSS 3.4+ (utility-first, CSS custom properties for dark mode), TanStack Query v5, TanStack Table v8, Zustand 5.x, Recharts 2.x, next-themes, cmdk (via shadcn Command), highlight.js (lazy), date-fns 4.x, Lucide React, Zod 3.x, React Hook Form 7.x, pnpm 9+ (015-nextjs-app-scaffold)
- Next.js App Scaffold (`apps/web/`): route groups `(main)` + `(auth)` for shell separation, CSS custom property dark mode (`:root`/`.dark` tokens, no FOIT), `lib/api.ts` fetch wrapper (JWT injection + 401-refresh-retry + 3x exponential backoff + ApiError normalization), `lib/ws.ts` WebSocketClient (topic subscriptions, exponential backoff reconnect 1s→30s cap), Zustand stores (auth: persists only refreshToken; workspace: invalidates TanStack Query on workspace switch), `lib/hooks/use-api.ts` factory hooks, sidebar RBAC filter via `requiredRoles: RoleType[]`, shadcn Command palette (Cmd+K), 11 shared components (DataTable/StatusBadge/MetricCard/ScoreGauge/EmptyState/ConfirmDialog/CodeBlock/JsonViewer/Timeline/SearchInput/FilterBar), Vitest + RTL + Playwright + MSW (015-nextjs-app-scaffold)

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
- 015-nextjs-app-scaffold: Added Next.js 14+ App Router scaffold — route groups (main)/(auth), CSS var dark mode, typed fetch API client (JWT+refresh+retry), WebSocket client (topics+reconnect), Zustand auth+workspace stores, TanStack Query v5 factory hooks, app shell (collapsible sidebar RBAC nav, header, breadcrumb, Cmd+K command palette), 11 shared UI components
- 014-auth-bounded-context: Added auth bounded context — email/password (Argon2id), RS256 JWT pair, Redis sessions + lockout, TOTP MFA, RBAC engine (10 roles, workspace-scoped), purpose-bound agent auth, service account API keys, 7 REST endpoints, 6 Kafka event types
- 013-fastapi-app-scaffold: Added FastAPI app factory with lifespan hooks, PlatformSettings (Pydantic v2), async SQLAlchemy with 6 mixins, Kafka event infrastructure (EventEnvelope + DLQ + registry), correlation ID + JWT middleware, 10 client wrappers, exception hierarchy, pagination, 8 profile entrypoints


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
