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
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, redis-py 5.x async (resend rate limiting), aiokafka 0.11+ (accounts events), secrets + SHA-256 (token hashing) (016-accounts-bounded-context)
- Accounts Bounded Context (`apps/control-plane/src/platform/accounts/`): self-registration with anti-enumeration (always 202), SHA-256 hashed email-verify tokens (24h TTL), invite tokens (7d TTL), signup modes (open/invite_only/admin_approval), state machine (pending_verification→pending_approval→active↔suspended→blocked→archived), admin approval queue, 8 lifecycle actions (suspend/reactivate/block/unblock/archive/reset-mfa/reset-password/unlock), Redis resend rate limiting (`resend_verify:{user_id}`), in-process auth service calls (credential creation + session invalidation), 17 REST endpoints, 15 Kafka event types on `accounts.events` topic (016-accounts-bounded-context)
- TypeScript 5.x + Next.js 14+ App Router, React 18+, shadcn/ui (Form, Input, Button, Dialog, InputOTP), React Hook Form 7.x + Zod 3.x, TanStack Query v5 (useMutation), Zustand 5.x (existing auth-store), qrcode.react (SVG QR codes), date-fns 4.x, Lucide React (017-login-auth)
- Login and Authentication UI (`apps/web/app/(auth)/`, `components/features/auth/`): email/password login with RHF+Zod, two-step MFA flow (TOTP + recovery code toggle via shadcn InputOTP, auto-submit at 6 digits), lockout countdown from backend `lockout_seconds` via `useEffect`+`setInterval` (no polling), forgot-password with anti-enumeration (always same confirmation), reset-password with per-rule Zod strength validation matching feature 016 backend rules (12-char min + uppercase + lowercase + digit + special), MFA enrollment dialog (QR code + text secret fallback + verify + recovery codes with mandatory acknowledgment), `?redirectTo` deep link preservation (validated relative-only), 6 TanStack Query `useMutation` hooks in `lib/hooks/use-auth-mutations.ts`, login flow state as local discriminated union (not Zustand) (017-login-auth)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (workspaces events + accounts consumer) (018-workspaces-bounded-context)
- Workspaces Bounded Context (`apps/control-plane/src/platform/workspaces/`): workspace CRUD (create/get/list/update/archive/restore/delete), membership management (add/remove/change role with workspace-scoped roles: owner/admin/member/viewer), default workspace provisioning via Kafka consumer on `accounts.user.activated` (idempotent), workspace goals with first-class GID correlation dimension + status state machine (open→in_progress→completed|cancelled), workspace-wide visibility grants (FQN pattern arrays, union with per-agent zero-trust config), workspace settings (super-context subscription metadata: agents/fleets/policies/connectors), per-user workspace limits via in-process accounts service interface, 20 REST endpoints + 2 internal service interfaces, 11 Kafka event types on `workspaces.events` topic (018-workspaces-bounded-context)
- Python 3.12+ + FastAPI 0.115+ (WebSocket via Starlette), Pydantic v2, aiokafka 0.11+ (dynamic topic consumers), PyJWT 2.x RS256 (upgrade auth), no SQLAlchemy (stateless in-memory only) (019-websocket-realtime-gateway)
- WebSocket Real-Time Gateway (`apps/control-plane/src/platform/ws_hub/`, `ws-hub` runtime profile): JWT auth on WebSocket upgrade, in-memory ConnectionRegistry + SubscriptionRegistry, 11 channel types (execution/interaction/conversation/workspace/fleet/reasoning/correction/simulation/testing/alerts/attention), per-instance unique Kafka consumer group (`ws-hub-{hostname}-{pid}`), dynamic topic subscription (zero-waste — KafkaFanout starts/stops consumers on refcount 0↔1), asyncio.Queue backpressure per client with configurable buffer + `events_dropped` notification, workspace-scoped visibility filtering via in-process workspaces_service, attention channel auto-subscribed on connect (filters `interaction.attention` by target_id), RFC 6455 ping/pong heartbeat, graceful shutdown (SIGTERM → broadcast close 1001 → stop consumers) (019-websocket-realtime-gateway)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, aiokafka 0.11+ (Kafka→ClickHouse pipeline consumer), clickhouse-connect 0.8+ (ClickHouse HTTP interface), SQLAlchemy 2.x async (CostModel pricing config only) (020-analytics-cost-intelligence)
- Analytics and Cost Intelligence (`apps/control-plane/src/platform/analytics/`): Kafka→ClickHouse usage event pipeline (batch 100 events or 5s, from `workflow.runtime`+`evaluation.events`), ClickHouse AggregatingMergeTree materialized views (hourly/daily/monthly rollups), cost-per-quality ratio (LEFT JOIN usage × quality by execution_id), rule-based optimization recommendations (model switch/self-correction tuning/context optimization/underutilization — 4 rules, confidence levels), linear regression budget forecasting (7/30/90-day horizons, confidence intervals, volatility flag), 4 REST GET endpoints + 1 internal cost summary interface, workspace-scoped access control, `analytics_cost_models` PostgreSQL table (pricing config), `analytics.events` Kafka topic (020-analytics-cost-intelligence)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), opensearch-py 2.x async (keyword indexing), qdrant-client 1.12+ async gRPC (semantic search), aioboto3 latest (MinIO package storage), httpx 0.27+ (embedding API calls) (021-agent-registry-ingest)
- PostgreSQL (5 tables: registry_namespaces, registry_agent_profiles, registry_agent_revisions, registry_maturity_records, registry_lifecycle_audit) + OpenSearch (marketplace-agents index) + Qdrant (agent_embeddings collection) + MinIO (agent-packages bucket) (021-agent-registry-ingest)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), clickhouse-connect 0.8+ (quality score time-series), qdrant-client 1.12+ async gRPC (long-term memory retrieval), APScheduler 3.x (drift monitor background task), httpx 0.27+ (optional: hierarchical compression LLM call) (022-context-engineering-service)
- PostgreSQL (5 tables: context_engineering_profiles, context_profile_assignments, context_assembly_records, context_ab_tests, context_drift_alerts) + ClickHouse (context_quality_scores time-series) + MinIO (context-assembly-records bucket for full bundle text) (022-context-engineering-service)
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer), qdrant-client 1.12+ async gRPC (vector storage and search), neo4j-python-driver 5.x async (`AsyncGraphDatabase`, knowledge graph), redis-py 5.x async (rate limiting sliding window), httpx 0.27+ (embedding API calls to model provider), APScheduler 3.x (embedding worker + consolidation worker + session cleaner) (023-memory-knowledge-subsystem)
- PostgreSQL (7 tables: memory_entries, evidence_conflicts, embedding_jobs, trajectory_records, pattern_assets, knowledge_nodes, knowledge_edges) + Qdrant (`platform_memory` collection, 1536-dim Cosine) + Neo4j (MemoryNode label, MEMORY_REL type) (023-memory-knowledge-subsystem)

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
- 023-memory-knowledge-subsystem: Added memory and knowledge bounded context — memory write gate (Redis sliding-window rate limiting, contradiction detection via Qdrant similarity + edit distance, retention enforcement, optional Laplace differential privacy), scoped vector storage (single `platform_memory` Qdrant collection, workspace/agent/scope payload filters), hybrid retrieval (vector + PostgreSQL FTS + Neo4j graph with RRF k=60, recency + authority post-fusion weights), knowledge graph (Neo4j MemoryNode/MEMORY_REL, workspace-isolated Cypher multi-hop traversal), trajectory capture (immutable records), pattern promotion workflow (pending→approved/rejected), APScheduler workers (EmbeddingWorker 30s, ConsolidationWorker 15min, SessionMemoryCleaner 60min), `retrieve_for_context()` internal interface for context engineering
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async + qdrant-client 1.12+ gRPC (`platform_memory` collection) + neo4j-python-driver 5.x async (knowledge graph) + redis-py 5.x async (rate limiting) + httpx 0.27+ (embedding API) + APScheduler 3.x (3 workers) + aiokafka 0.11+ (memory.events) (023-memory-knowledge-subsystem)
- 022-context-engineering-service: Added context engineering bounded context — deterministic assembly pipeline from 9 source types (system instructions with agent purpose+approach, workflow state, conversation history, long-term memory via Qdrant, tool outputs, connector payloads, workspace metadata, reasoning traces, workspace goal super-context), 6-dimension quality scorer (relevance/freshness/authority/contradiction/efficiency/coverage), budget enforcement with 4 compaction strategies (relevance truncation, priority eviction, hierarchical compression, semantic deduplication), mandatory privacy filtering via policies service, ClickHouse quality score time-series, APScheduler drift monitor (5-min, mean-2σ threshold), hash-based A/B testing, profile management with agent/role-type/workspace assignment hierarchy
- Python 3.12+ + FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async + clickhouse-connect 0.8+ (context_quality_scores) + qdrant-client 1.12+ gRPC (long-term memory adapter) + APScheduler 3.x (drift monitor) + aiokafka 0.11+ (context_engineering.events) + MinIO (context-assembly-records) (022-context-engineering-service)


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
