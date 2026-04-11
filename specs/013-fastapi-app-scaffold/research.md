# Research: FastAPI Application Scaffold — Control Plane Foundation

**Feature**: 013-fastapi-app-scaffold  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Application Factory Pattern — Lifespan-Based Initialization

**Decision**: The FastAPI application is created via an app factory function in `src/platform/main.py` using the FastAPI `lifespan` context manager (not `on_event` deprecated hooks). The lifespan async generator connects all data stores in the startup phase and closes them in the shutdown phase. Connection failures are non-fatal — the app starts in degraded mode and the health endpoint reports which stores are unhealthy.

**Rationale**: The `lifespan` API is the recommended FastAPI pattern since 0.109+. It provides clean startup/shutdown semantics with proper resource cleanup. Non-fatal startup allows the operator to see which store is failing rather than getting a crash loop.

**Alternatives considered**:
- `on_event("startup")` / `on_event("shutdown")`: Deprecated since FastAPI 0.109. Rejected.
- Lazy initialization on first request: Would cause unpredictable latency spikes on the first request. Rejected.

---

## Decision 2: Configuration — Pydantic Settings with Validation Groups

**Decision**: All configuration lives in `src/platform/common/config.py` as a `PlatformSettings(BaseSettings)` class using Pydantic v2 `model_config = SettingsConfigDict(env_prefix="PLATFORM_")`. Settings are grouped by concern: `DatabaseSettings` (PostgreSQL DSN, pool sizes), `RedisSettings` (nodes, mode), `KafkaSettings` (brokers), `QdrantSettings` (host, port, grpc_port), `Neo4jSettings` (uri, auth), `ClickHouseSettings` (host, port), `OpenSearchSettings` (hosts), `MinIOSettings` (endpoint, bucket), `GRPCSettings` (all satellite addresses), `AuthSettings` (JWT secret, algorithm, session TTL), `OTelSettings` (exporter endpoint).

The top-level `PlatformSettings` composes all sub-settings as nested models.

**Rationale**: Constitution mandates Pydantic for all schemas. Grouping by store keeps configuration organized and allows individual groups to be tested in isolation. Environment variable overrides are automatic with `BaseSettings`.

**Alternatives considered**:
- YAML configuration file: Adds a file to manage; env vars are the 12-factor standard for containers. Rejected.
- Single flat Settings class: Too many fields in one class. Rejected for readability.

---

## Decision 3: SQLAlchemy Async Engine — AsyncSession with Scoped Dependency

**Decision**: `src/platform/common/database.py` creates an `AsyncEngine` via `create_async_engine(dsn, pool_size=20, max_overflow=10)` using the `asyncpg` driver. An `async_sessionmaker` produces `AsyncSession` instances. The FastAPI dependency `get_db` yields a session per request, commits on success, rolls back on exception.

Six mixins in `src/platform/common/models/mixins.py`:
1. **UUIDMixin**: `id = Column(UUID, primary_key=True, default=uuid4)`
2. **TimestampMixin**: `created_at`, `updated_at` with `server_default=func.now()` and `onupdate=func.now()`
3. **SoftDeleteMixin**: `deleted_at` nullable timestamp; `is_deleted` hybrid property; default query filter
4. **AuditMixin**: `created_by`, `updated_by` (UUID foreign keys to users)
5. **WorkspaceScopedMixin**: `workspace_id` (UUID, indexed) with query filter
6. **EventSourcedMixin**: `version` integer for optimistic locking; `pending_events` transient list

`src/platform/common/models/base.py` defines the `Base = declarative_base()`.

**Rationale**: Constitution §2.1 mandates SQLAlchemy 2.x async mode, `AsyncSession`, `async_sessionmaker`. The mixin order is specified in CLAUDE.md: Base first, then behavior mixins, then concrete columns. Pool sizes follow PostgreSQL best practices for a connection pooler (PgBouncer/CloudNativePG pooler).

**Alternatives considered**:
- Synchronous SQLAlchemy: Violates constitution §2.1 (async only). Rejected.
- Per-bounded-context engine: Over-complex; all contexts share the same PostgreSQL instance. Rejected.

---

## Decision 4: Kafka Event Infrastructure — Canonical Envelope with DLQ

**Decision**: `src/platform/common/events/` package:

- `envelope.py`: `EventEnvelope` Pydantic model: `event_type`, `version`, `source`, `correlation_context` (CorrelationContext model), `trace_context` (dict), `occurred_at` (datetime), `payload` (dict). Serialized as JSON for Kafka.
- `producer.py`: `EventProducer` class wrapping `aiokafka.AIOKafkaProducer`. `publish(topic, key, event_type, payload, correlation_ctx)` builds the envelope, validates against registry, serializes, and sends.
- `consumer.py`: `EventConsumerManager` class wrapping `aiokafka.AIOKafkaConsumer`. Manages consumer groups with `subscribe(topic, group_id, handler)`. Handlers are async callables receiving `EventEnvelope`.
- `registry.py`: `EventTypeRegistry` — dict mapping event_type strings to Pydantic models. `register(event_type, schema)`. `validate(event_type, payload)` validates payload against registered schema. Unregistered types raise `ValidationError`.
- `retry.py`: `RetryHandler` wrapping consumer handlers. On failure: retry up to 3 times with exponential backoff (1s, 2s, 4s). After 3 failures: publish original event to `{topic}.dlq` with failure metadata.

**Rationale**: Constitution mandates aiokafka 0.11+ and canonical `EventEnvelope`. DLQ pattern prevents event loss while isolating poison pills. The registry prevents schema drift by validating before publish.

**Alternatives considered**:
- confluent-kafka-python: Constitution §2.1 mandates `aiokafka` for Python. Rejected.
- No event registry: Schema drift is a real risk with 20+ event types. Rejected.

---

## Decision 5: Client Wrappers — Thin Async Wrappers with Health Check

**Decision**: All client wrappers live in `src/platform/common/clients/`. Each wrapper:
1. Takes connection settings from `PlatformSettings`
2. Provides `async connect()` and `async close()` lifecycle methods
3. Provides `async health_check() -> bool`
4. Exposes the underlying client for advanced use

Wrappers:
- `redis.py`: `redis.asyncio.RedisCluster` or `Redis` depending on `REDIS_TEST_MODE`
- `qdrant.py`: `qdrant_client.AsyncQdrantClient` with gRPC transport
- `neo4j.py`: `neo4j.AsyncGraphDatabase.driver()` → `AsyncDriver`
- `clickhouse.py`: `clickhouse_connect.get_client()` (sync but wrapped in `run_in_executor`)
- `opensearch.py`: `opensearch_py.AsyncOpenSearch`
- `object_storage.py`: `aioboto3` S3 client for MinIO
- `reasoning_engine.py`: `grpc.aio.insecure_channel` to port 50052
- `runtime_controller.py`: `grpc.aio.insecure_channel` to port 50051
- `sandbox_manager.py`: `grpc.aio.insecure_channel` to port 50053
- `simulation_controller.py`: `grpc.aio.insecure_channel` to port 50055

**Rationale**: Constitution §2.1 mandates specific client libraries for each store. Thin wrappers add only lifecycle management and health checks — no business logic. The gRPC clients are auto-generated stubs; the wrapper just manages the channel lifecycle.

**Alternatives considered**:
- No wrappers (raw clients in bounded contexts): Duplicates connection management across contexts. Rejected.
- Thick wrappers with business logic: Violates bounded context ownership. Rejected.

---

## Decision 6: Middleware Stack — Correlation ID + JWT Auth

**Decision**: Two middleware classes in `src/platform/common/`:

- `correlation.py`: `CorrelationMiddleware(BaseHTTPMiddleware)` — extracts `X-Correlation-ID` header (or generates UUID). Stores in `contextvars.ContextVar`. Available to all downstream handlers, logging, and Kafka event publishing. Sets `X-Correlation-ID` response header.
- `auth_middleware.py`: `AuthMiddleware(BaseHTTPMiddleware)` — exempts configurable paths (`/health`, `/docs`, `/openapi.json`). For all other paths: validates `Authorization: Bearer {JWT}` header using PyJWT with RS256. On valid token: stores user context in request state. On invalid/missing: returns 401 JSON response. Also supports Redis-backed session cookies as an alternative auth mechanism.

**Rationale**: Correlation IDs are critical for distributed tracing per constitution. JWT with RS256 matches constitution §2.1 (PyJWT 2.x, RS256). Redis-backed sessions use the async Redis client for session validation.

**Alternatives considered**:
- FastAPI `Depends` for auth instead of middleware: Works for per-route auth but doesn't enforce auth globally. Rejected — middleware ensures no route accidentally omits auth.
- HMAC JWT (HS256): RS256 is specified in the constitution. Rejected.

---

## Decision 7: Exception Hierarchy — PlatformError with HTTP Mapping

**Decision**: `src/platform/common/exceptions.py`:

```
PlatformError(code: str, message: str, details: dict)
├── NotFoundError → 404
├── AuthorizationError → 403
├── ValidationError → 422
├── PolicyViolationError → 403
├── BudgetExceededError → 429
└── ConvergenceFailedError → 500
```

A FastAPI exception handler `platform_exception_handler` registered in the app factory catches `PlatformError` and returns the appropriate HTTP response with structured body: `{"error": {"code": str, "message": str, "details": dict}}`.

**Rationale**: Constitution error handling section defines exactly this hierarchy and status code mapping. Structured error bodies enable consistent client-side error handling.

**Alternatives considered**:
- FastAPI `HTTPException` subclasses: Couples domain errors to HTTP transport. Rejected — domain errors should be transport-agnostic.
- Exception codes as integers: Strings are more descriptive and grep-friendly. Rejected.

---

## Decision 8: Pagination Helpers — Cursor and Offset

**Decision**: `src/platform/common/pagination.py`:

- `CursorPage(Generic[T])`: Pydantic model with `items: list[T]`, `next_cursor: str | None`, `has_more: bool`. The cursor is an opaque base64-encoded `(id, created_at)` tuple.
- `OffsetPage(Generic[T])`: Pydantic model with `items: list[T]`, `total: int`, `page: int`, `page_size: int`, `total_pages: int`.
- `apply_cursor_pagination(query, cursor, page_size)`: Modifies SQLAlchemy query with `WHERE (id, created_at) > decoded_cursor ORDER BY created_at, id LIMIT page_size + 1`.
- `apply_offset_pagination(query, page, page_size)`: Adds `OFFSET` and `LIMIT`.

**Rationale**: Cursor pagination is required for real-time feeds (consistent under concurrent inserts). Offset pagination is simpler for admin dashboards where exact page numbers matter. Both are used across the platform.

**Alternatives considered**:
- Keyset pagination only: Offset is needed for admin UIs. Rejected.
- Third-party pagination library: Adds unnecessary dependency for simple helpers. Rejected.

---

## Decision 9: Runtime Profiles — Entrypoint per Profile

**Decision**: 8 entrypoint scripts in `apps/control-plane/entrypoints/`:
- `api_main.py`: Mounts all public REST routers, runs uvicorn
- `scheduler_main.py`: Starts APScheduler with registered jobs, no HTTP routes
- `worker_main.py`: Starts Kafka consumer groups for background processing
- `projection_indexer_main.py`: Consumes journal events, projects to read models
- `trust_certifier_main.py`: Runs certification evaluation loops
- `context_engineering_main.py`: Runs context assembly workers
- `agentops_testing_main.py`: Runs evaluation and testing workers
- `ws_main.py`: Starts WebSocket hub with connection management

Each profile calls the same app factory with a `profile` parameter. The factory activates routes and workers based on the profile. All profiles share the same `PlatformSettings` and connection infrastructure.

**Rationale**: Constitution §3.1 defines these exact 8 runtime profiles as deployments of the same codebase. Separate entrypoints keep startup minimal per profile while sharing all common infrastructure.

**Alternatives considered**:
- CLI flags instead of separate entrypoints: Kubernetes deployments benefit from separate `command:` entries; entrypoints are cleaner. Rejected.
- Separate codebases per profile: Violates constitution §3.1 (modular monolith). Rejected.

---

## Decision 10: OpenTelemetry Instrumentation — Auto-Instrumentation + Manual Spans

**Decision**: `src/platform/common/telemetry.py` sets up:
- `opentelemetry-sdk` TracerProvider with OTLP exporter
- `opentelemetry-instrumentation-fastapi` for automatic HTTP span creation
- `opentelemetry-instrumentation-sqlalchemy` for database query spans
- `opentelemetry-instrumentation-redis` for Redis command spans
- `opentelemetry-instrumentation-grpc` for outbound gRPC call spans
- Manual span creation in Kafka producer/consumer for event tracing
- Trace context propagation: HTTP headers → `CorrelationContext` → Kafka headers → gRPC metadata

**Rationale**: Constitution §2.1 mandates `opentelemetry-sdk 1.27+`. Auto-instrumentation covers the common cases; manual spans fill gaps (Kafka). Trace context propagation ensures end-to-end visibility from HTTP request through Kafka events to gRPC satellite calls.

**Alternatives considered**:
- Manual-only instrumentation: Too much boilerplate for HTTP/SQL. Rejected.
- Datadog/New Relic SDK: Constitution mandates OpenTelemetry. Rejected.
