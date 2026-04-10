# Tasks: FastAPI Application Scaffold — Control Plane Foundation

**Input**: Design documents from `specs/013-fastapi-app-scaffold/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/health-api.md ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Tests are required by spec (SC-007: ≥95% coverage)

---

## Phase 1: Setup

**Purpose**: Project initialization and directory structure

- [X] T001 Create `apps/control-plane/src/platform/` directory tree with all `__init__.py` files per plan.md structure (platform/, api/, common/, common/events/, common/models/, common/clients/)
- [X] T002 Write `apps/control-plane/pyproject.toml` with all dependencies: FastAPI 0.115+, Pydantic v2, pydantic-settings, SQLAlchemy 2.x, asyncpg, alembic, aiokafka 0.11+, redis-py 5.x, qdrant-client 1.12+, neo4j 5.x, clickhouse-connect 0.8+, opensearch-py 2.x, aioboto3, grpcio 1.65+, grpcio-tools, PyJWT 2.x, pyotp, opentelemetry-sdk 1.27+, opentelemetry-instrumentation-fastapi, opentelemetry-instrumentation-sqlalchemy, opentelemetry-instrumentation-redis, opentelemetry-instrumentation-grpc, httpx 0.27+, APScheduler 3.x, argon2-cffi, pytest 8.x, pytest-asyncio, pytest-cov, ruff 0.7+, mypy 1.11+
- [X] T003 [P] Configure ruff (lint rules, isort, format) and mypy (strict mode, plugins) sections in `apps/control-plane/pyproject.toml`
- [X] T004 [P] Create `apps/control-plane/tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, and `apps/control-plane/conftest.py` with pytest-asyncio mode=auto

**Checkpoint**: Directory structure and dependency manifest ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure MUST be complete before any user story can begin

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement `apps/control-plane/src/platform/common/models/base.py` — `class Base(DeclarativeBase): pass` as the SQLAlchemy declarative base shared by all bounded contexts
- [X] T006 [P] Implement `apps/control-plane/src/platform/common/config.py` — all Pydantic Settings sub-models (`DatabaseSettings`, `RedisSettings`, `KafkaSettings`, `QdrantSettings`, `Neo4jSettings`, `ClickHouseSettings`, `OpenSearchSettings`, `MinIOSettings`, `GRPCSettings`, `AuthSettings`, `OTelSettings`) and top-level `PlatformSettings` composing all sub-settings; include `PLATFORM_PROFILE` field defaulting to `"api"`

**Checkpoint**: Foundation ready — all user story phases can now begin

---

## Phase 3: User Story 1 — Application Bootstrap and Health (Priority: P1) 🎯 MVP

**Goal**: FastAPI app factory with lifespan hooks connecting all data stores, degraded mode on store failure, and `GET /health` returning per-dependency status with latency

**Independent Test**: Start API profile → `GET /health` returns 200 with all stores healthy. Stop PostgreSQL → `/health` reports `postgresql: unhealthy` while all others remain healthy. Stop all stores → `/health` still returns 200 (degraded, not crash)

### Tests for User Story 1

- [X] T007 [P] [US1] Write `apps/control-plane/tests/unit/test_health.py` — unit tests for health endpoint response schema (healthy/degraded/unhealthy status logic, per-dependency latency fields, profile field)

### Implementation for User Story 1

- [X] T008 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/redis.py` — `AsyncRedisClient` wrapping `redis.asyncio.Redis` (standalone) or `RedisCluster` (cluster mode per `REDIS_TEST_MODE`); `connect()`, `close()`, `async health_check() -> bool` via `ping()`
- [X] T009 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/qdrant.py` — `AsyncQdrantClient` wrapping `qdrant_client.AsyncQdrantClient` with gRPC transport; `connect()`, `close()`, `async health_check() -> bool` via `get_collections()`
- [X] T010 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/neo4j.py` — `AsyncNeo4jClient` wrapping `neo4j.AsyncGraphDatabase.driver()`; `connect()`, `close()`, `async health_check() -> bool` via session verify connectivity
- [X] T011 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/clickhouse.py` — `ClickHouseClient` wrapping `clickhouse_connect.get_client()` executed via `asyncio.get_event_loop().run_in_executor()`; `connect()`, `close()`, `async health_check() -> bool` via `ping()`
- [X] T012 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/opensearch.py` — `AsyncOpenSearchClient` wrapping `opensearch_py.AsyncOpenSearch`; `connect()`, `close()`, `async health_check() -> bool` via `cluster.health()`
- [X] T013 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/object_storage.py` — `AsyncObjectStorageClient` wrapping `aioboto3` S3 session targeting MinIO endpoint; `connect()`, `close()`, `async health_check() -> bool` via `list_buckets()`
- [X] T014 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/runtime_controller.py` — `RuntimeControllerClient` wrapping `grpc.aio.insecure_channel` to `GRPC_RUNTIME_CONTROLLER`; `connect()`, `close()`, `async health_check() -> bool` via gRPC channel connectivity check; expose `stub` attribute for bounded-context use
- [X] T015 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/reasoning_engine.py` — `ReasoningEngineClient` wrapping `grpc.aio.insecure_channel` to `GRPC_REASONING_ENGINE` (port 50052); same pattern as T014
- [X] T016 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/sandbox_manager.py` — `SandboxManagerClient` wrapping `grpc.aio.insecure_channel` to `GRPC_SANDBOX_MANAGER` (port 50053); same pattern as T014
- [X] T017 [P] [US1] Implement `apps/control-plane/src/platform/common/clients/simulation_controller.py` — `SimulationControllerClient` wrapping `grpc.aio.insecure_channel` to `GRPC_SIMULATION_CONTROLLER` (port 50055); same pattern as T014
- [X] T018 [US1] Implement `apps/control-plane/src/platform/common/database.py` — create `AsyncEngine` via `create_async_engine(dsn, pool_size, max_overflow, echo=False)` using `asyncpg`; create `async_sessionmaker`; expose module-level `engine` and `AsyncSessionLocal` initialized from `PlatformSettings`
- [X] T019 [US1] Implement `apps/control-plane/src/platform/main.py` — `create_app(profile: str = "api") -> FastAPI` factory; async `lifespan` context manager that attempts `connect()` on each client (catches exceptions, sets `degraded` flag, logs warning); registers exception handler; mounts `/api` router set based on `profile`; stores connected clients in `app.state`
- [X] T020 [US1] Implement `apps/control-plane/src/platform/api/health.py` — `GET /health` router; calls `health_check()` on each dependency with `time.monotonic()` latency measurement; determines overall status (`healthy` / `degraded` / `unhealthy` based on PostgreSQL being down); returns `HealthResponse` Pydantic schema matching `contracts/health-api.md`
- [X] T021 [US1] Write `apps/control-plane/entrypoints/api_main.py` — imports `create_app`, sets `profile="api"`, runs `uvicorn.run(create_app, factory=True, host="0.0.0.0", port=8000, lifespan="on")`

**Checkpoint**: `python -m entrypoints.api_main` → `GET /health` returns 200 with per-store status. Degraded mode works when a store is stopped.

---

## Phase 4: User Story 2 — Configuration and Dependency Injection (Priority: P1)

**Goal**: FastAPI dependency injection functions `get_db`, `get_current_user`, `get_workspace` so every bounded context route can access sessions, auth, and workspace context consistently

**Independent Test**: Define a test route injecting `get_db` and `get_current_user` with a valid JWT — verify async session is committed/rolled back correctly and user is resolved from token claims

### Tests for User Story 2

- [X] T022 [P] [US2] Write `apps/control-plane/tests/unit/test_config.py` — tests for `PlatformSettings` loading from env vars (override each sub-setting via os.environ), default values, nested model validation
- [X] T023 [P] [US2] Write `apps/control-plane/tests/unit/test_database.py` — tests for `get_db` generator: session yields, commits on success, rolls back on exception, session is closed after yield

### Implementation for User Story 2

- [X] T024 [US2] Implement `apps/control-plane/src/platform/common/dependencies.py` — `get_db() -> AsyncGenerator[AsyncSession, None]`: yields session from `AsyncSessionLocal`, commits on success, rolls back on `Exception`, always closes; `get_current_user(request: Request) -> dict`: extracts `Authorization: Bearer` header, decodes JWT using `AUTH_JWT_SECRET_KEY` and `AUTH_JWT_ALGORITHM`, raises `AuthorizationError` if missing/invalid/expired; `get_workspace(request: Request, db: AsyncSession) -> dict`: extracts `X-Workspace-ID` header, raises `NotFoundError` if absent

**Checkpoint**: Routes using `Depends(get_db)` and `Depends(get_current_user)` work correctly; invalid JWT returns 403.

---

## Phase 5: User Story 3 — Database Models and Mixins (Priority: P1)

**Goal**: All 6 SQLAlchemy mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`) composable by any bounded context model

**Independent Test**: Create a test model using all 6 mixins → verify UUID auto-generated, `created_at`/`updated_at` set, `deleted_at` set on soft delete with `is_deleted` hybrid property, `created_by`/`updated_by` present, `workspace_id` indexed, `version` int defaults to 1

### Tests for User Story 3

- [X] T025 [P] [US3] Write `apps/control-plane/tests/unit/test_mixins.py` — create in-memory SQLite async engine per test; verify each mixin individually: UUID default, timestamps on create/update via `func.now()`, `SoftDeleteMixin.is_deleted` hybrid property, `AuditMixin` nullable UUID fields, `WorkspaceScopedMixin` index exists, `EventSourcedMixin` version default=1

### Implementation for User Story 3

- [X] T026 [US3] Implement `apps/control-plane/src/platform/common/models/mixins.py` — all 6 mixins per `data-model.md`: `UUIDMixin` (UUID primary key with `default=uuid.uuid4`), `TimestampMixin` (`created_at`/`updated_at` with `server_default=func.now()` and `onupdate=func.now()`), `SoftDeleteMixin` (`deleted_at` nullable + `is_deleted` hybrid property returning `self.deleted_at is not None`), `AuditMixin` (`created_by`/`updated_by` UUID nullable), `WorkspaceScopedMixin` (`workspace_id` UUID non-null indexed), `EventSourcedMixin` (`version` Integer default=1, `pending_events: list` as non-mapped attribute via `__init_subclass__` or `@event.listens_for`)

**Checkpoint**: `from src.platform.common.models.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin` works; test model creation in SQLite passes all 6 mixin verifications.

---

## Phase 6: User Story 4 — Kafka Event Infrastructure (Priority: P1)

**Goal**: Async Kafka producer + consumer group manager + canonical `EventEnvelope` + event type registry with schema validation + DLQ retry handler (3 retries, exponential backoff)

**Independent Test**: Publish event via producer → appears on topic with correct envelope fields. Simulate handler failure 3 times → event appears on `{topic}.dlq` with failure metadata. Register event type schema → invalid payload rejected before publish.

### Tests for User Story 4

- [X] T027 [P] [US4] Write `apps/control-plane/tests/unit/test_events.py` — unit tests for: `EventEnvelope` serialization/deserialization roundtrip; `CorrelationContext` field validation; `EventTypeRegistry` register + validate + reject unknown type; `RetryHandler` retry count tracking and DLQ routing logic (mock the producer and consumer)

### Implementation for User Story 4

- [X] T028 [P] [US4] Implement `apps/control-plane/src/platform/common/events/envelope.py` — `CorrelationContext(BaseModel)` with optional `workspace_id`, `conversation_id`, `interaction_id`, `execution_id`, `fleet_id`, `goal_id` (all `UUID | None`) and required `correlation_id: UUID`; `EventEnvelope(BaseModel)` with `event_type: str`, `version: str = "1.0"`, `source: str`, `correlation_context: CorrelationContext`, `trace_context: dict[str, str] = {}`, `occurred_at: datetime = Field(default_factory=datetime.utcnow)`, `payload: dict[str, Any]`
- [X] T029 [P] [US4] Implement `apps/control-plane/src/platform/common/events/registry.py` — `EventTypeRegistry` class: `register(event_type: str, schema: type[BaseModel]) -> None` stores mapping; `validate(event_type: str, payload: dict) -> BaseModel` validates or raises `ValidationError`; `is_registered(event_type: str) -> bool`; module-level singleton `event_registry = EventTypeRegistry()`
- [X] T030 [US4] Implement `apps/control-plane/src/platform/common/events/producer.py` — `EventProducer` class wrapping `aiokafka.AIOKafkaProducer`; `async connect(brokers: str)` starts producer; `async close()`; `async publish(topic: str, key: str, event_type: str, payload: dict, correlation_ctx: CorrelationContext, source: str) -> None` — validates payload via registry, builds `EventEnvelope`, serializes to JSON, sends with key; raise `ValidationError` on unregistered event type
- [X] T031 [US4] Implement `apps/control-plane/src/platform/common/events/consumer.py` — `EventConsumerManager` class; `subscribe(topic: str, group_id: str, handler: Callable[[EventEnvelope], Awaitable[None]]) -> None` registers handler; `async start()` creates `AIOKafkaConsumer` per subscription, starts tasks; `async stop()` drains and closes consumers; deserializes each message as `EventEnvelope`
- [X] T032 [US4] Implement `apps/control-plane/src/platform/common/events/retry.py` — `RetryHandler` wrapping a consumer handler: on `Exception`, retries up to 3 times with `asyncio.sleep(2 ** attempt)` (1s, 2s, 4s); after 3 failures, calls `producer.publish` to `f"{topic}.dlq"` with original payload + `failure_reason`, `attempt_count`, `failed_at` in metadata; logs each retry at WARNING, DLQ routing at ERROR

**Checkpoint**: `EventEnvelope(event_type="test.event", source="test", correlation_context=..., payload={}).model_dump_json()` produces valid JSON. Registry rejects unregistered types. DLQ test passes (mock assertions on producer).

---

## Phase 7: User Story 5 — Request Middleware (Priority: P2)

**Goal**: `CorrelationMiddleware` generating/propagating `X-Correlation-ID` across all requests + `AuthMiddleware` validating JWT (RS256) with path exemptions for `/health`, `/docs`, `/openapi.json`, `/redoc`

**Independent Test**: `GET /health` without JWT → 200. `GET /api/v1/protected` without JWT → 401. Request without `X-Correlation-ID` → response has auto-generated UUID in `X-Correlation-ID`. Request with `X-Correlation-ID: test-123` → same ID propagated in response.

### Tests for User Story 5

- [X] T033 [P] [US5] Write `apps/control-plane/tests/unit/test_middleware.py` — unit tests for `CorrelationMiddleware`: auto-generate UUID when header absent, propagate existing header, store in `ContextVar`; tests for `AuthMiddleware`: exempt paths pass without JWT, protected paths return 401 without JWT, valid RS256 JWT passes, expired JWT returns 401

### Implementation for User Story 5

- [X] T034 [US5] Implement `apps/control-plane/src/platform/common/correlation.py` — `correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")` module-level; `CorrelationMiddleware(BaseHTTPMiddleware)`: extracts `X-Correlation-ID` header (validates UUID format, ignores invalid), generates `str(uuid4())` if absent, sets `correlation_id_var`, calls `await call_next(request)`, sets `X-Correlation-ID` and `X-Request-ID: str(uuid4())` on response
- [X] T035 [US5] Implement `apps/control-plane/src/platform/common/auth_middleware.py` — `EXEMPT_PATHS: set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}`; `AuthMiddleware(BaseHTTPMiddleware)`: skips exempt paths; extracts `Authorization: Bearer <token>` header; decodes JWT with `PyJWT.decode(token, key, algorithms=[algorithm])`; on `ExpiredSignatureError` returns 401 with `{"error": {"code": "TOKEN_EXPIRED", "message": "..."}}` JSON; on missing header returns 401 with `UNAUTHORIZED`; stores decoded payload in `request.state.user`
- [X] T036 [US5] Register `CorrelationMiddleware` and `AuthMiddleware` in `apps/control-plane/src/platform/main.py` `create_app()` — add `app.add_middleware(AuthMiddleware)` then `app.add_middleware(CorrelationMiddleware)` (order matters: correlation wraps auth)

**Checkpoint**: `curl -H "X-Correlation-ID: abc" /health` → response contains `X-Correlation-ID: abc`. `curl /health` without JWT → 200. `curl /api/v1/anything` without JWT → 401.

---

## Phase 8: User Story 6 — Client Wrappers for External Services (Priority: P2)

**Goal**: All 10 client wrappers (8 stores + 4 gRPC satellites) provide full typed domain methods beyond health_check, enabling bounded contexts to use stores without raw client management

**Independent Test**: Initialize each wrapper with valid settings → `health_check()` returns True. Call a typed method on each (e.g., `qdrant.search_vectors()`, `neo4j.run_cypher()`, `clickhouse.execute_query()`, `opensearch.search()`, `object_storage.put_object()`)

### Tests for User Story 6

- [X] T037 [P] [US6] Write `apps/control-plane/tests/integration/test_store_connections.py` — integration test (requires live services or docker-compose): test `health_check()` on each of the 10 wrappers; test one typed operation per wrapper to verify connectivity end-to-end; mark with `@pytest.mark.integration` for optional execution

### Implementation for User Story 6

- [X] T038 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/redis.py` — add typed methods: `async get(key: str) -> bytes | None`, `async set(key: str, value: bytes, ttl: int | None = None) -> None`, `async delete(key: str) -> None`, `async hgetall(key: str) -> dict`, `async evalsha(sha: str, keys: list, args: list) -> Any`
- [X] T039 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/qdrant.py` — add typed methods: `async upsert_vectors(collection: str, points: list[dict]) -> None`, `async search_vectors(collection: str, query_vector: list[float], limit: int, filter: dict | None) -> list[dict]`, `async create_collection(collection: str, vector_size: int, distance: str) -> None`
- [X] T040 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/neo4j.py` — add typed methods: `async run_cypher(query: str, parameters: dict | None = None) -> list[dict]`, `async run_in_transaction(queries: list[tuple[str, dict]]) -> None`
- [X] T041 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/clickhouse.py` — add typed methods: `async execute_query(query: str, parameters: dict | None = None) -> list[dict]`, `async insert(table: str, rows: list[dict], column_names: list[str]) -> None`
- [X] T042 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/opensearch.py` — add typed methods: `async index(index: str, doc_id: str, body: dict) -> None`, `async search(index: str, query: dict, size: int = 10) -> dict`, `async bulk(operations: list[dict]) -> dict`
- [X] T043 [P] [US6] Extend `apps/control-plane/src/platform/common/clients/object_storage.py` — add typed methods: `async put_object(bucket: str, key: str, body: bytes, content_type: str = "application/octet-stream") -> None`, `async get_object(bucket: str, key: str) -> bytes`, `async list_objects(bucket: str, prefix: str = "") -> list[str]`, `async create_bucket_if_not_exists(bucket: str) -> None`

**Checkpoint**: All 10 wrappers pass `health_check()` with live services. Integration tests pass with `--run-integration` flag.

---

## Phase 9: User Story 7 — Exception Hierarchy and Pagination (Priority: P2)

**Goal**: `PlatformError` hierarchy with HTTP status code mapping + FastAPI exception handler + `CursorPage` / `OffsetPage` with SQLAlchemy query helpers

**Independent Test**: Raise `NotFoundError("X", "msg")` from route → 404 with `{"error": {"code": "X", "message": "msg", "details": {}}}`. `CursorPage(items=[1,2,3], next_cursor="abc", has_more=True)` serializes correctly.

### Tests for User Story 7

- [X] T044 [P] [US7] Write `apps/control-plane/tests/unit/test_exceptions.py` — verify each `PlatformError` subclass has correct `status_code`; test `platform_exception_handler` returns correct HTTP status and body shape; test `details` dict is included; test `AuthorizationError` → 403, `BudgetExceededError` → 429, `ConvergenceFailedError` → 500
- [X] T045 [P] [US7] Write `apps/control-plane/tests/unit/test_pagination.py` — test `CursorPage[int]` with and without next cursor; test `OffsetPage[str]` with total_pages computation; test `apply_cursor_pagination` modifies query correctly (mock SQLAlchemy select); test `apply_offset_pagination` adds correct OFFSET/LIMIT

### Implementation for User Story 7

- [X] T046 [US7] Implement `apps/control-plane/src/platform/common/exceptions.py` — `PlatformError(Exception)` with `status_code: int = 500`, `__init__(self, code: str, message: str, details: dict | None = None)`; subclasses: `NotFoundError` (404), `AuthorizationError` (403), `ValidationError` (422), `PolicyViolationError` (403), `BudgetExceededError` (429), `ConvergenceFailedError` (500); `async platform_exception_handler(request: Request, exc: PlatformError) -> JSONResponse` returning `{"error": {"code": exc.code, "message": exc.message, "details": exc.details}}`; register with `app.add_exception_handler(PlatformError, platform_exception_handler)` in `main.py`
- [X] T047 [US7] Implement `apps/control-plane/src/platform/common/pagination.py` — `CursorPage(BaseModel, Generic[T])` with `items: list[T]`, `next_cursor: str | None = None`, `has_more: bool = False`; `OffsetPage(BaseModel, Generic[T])` with `items: list[T]`, `total: int`, `page: int`, `page_size: int`, `total_pages: int`; `decode_cursor(cursor: str) -> tuple[UUID, datetime]` base64-decode; `encode_cursor(id: UUID, created_at: datetime) -> str` base64-encode; `apply_cursor_pagination(query, cursor: str | None, page_size: int)` adds `WHERE (id, created_at) > decoded ORDER BY created_at, id LIMIT page_size + 1`; `apply_offset_pagination(query, page: int, page_size: int)` adds `OFFSET (page-1)*page_size LIMIT page_size`
- [X] T048 [US7] Register `platform_exception_handler` in `apps/control-plane/src/platform/main.py` `create_app()` via `app.add_exception_handler(PlatformError, platform_exception_handler)`

**Checkpoint**: Routes raising `PlatformError` subclasses return correct HTTP codes. `CursorPage` and `OffsetPage` serialize with Generic type resolution.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: OpenTelemetry instrumentation, all 7 remaining entrypoints, integration wiring, coverage

- [X] T049 [P] Implement `apps/control-plane/src/platform/common/telemetry.py` — `setup_telemetry(service_name: str, exporter_endpoint: str | None) -> None`: configures OTLP `TracerProvider`; calls `FastAPIInstrumentor().instrument_app(app)`, `SQLAlchemyInstrumentor().instrument()`, `RedisInstrumentor().instrument()`, `GrpcInstrumentorClient().instrument()`; no-op if `OTEL_EXPORTER_ENDPOINT` is empty; call from `create_app()` after engine creation
- [X] T050 [P] Write `apps/control-plane/entrypoints/scheduler_main.py` — imports `create_app(profile="scheduler")`; configures APScheduler and adds placeholder scheduled jobs; starts uvicorn on port 8001
- [X] T051 [P] Write `apps/control-plane/entrypoints/worker_main.py` — imports `create_app(profile="worker")`; starts Kafka `EventConsumerManager` subscription loops; no HTTP server
- [X] T052 [P] Write `apps/control-plane/entrypoints/projection_indexer_main.py` — imports `create_app(profile="projection-indexer")`; starts consumer group for journal events, projects to read models
- [X] T053 [P] Write `apps/control-plane/entrypoints/trust_certifier_main.py` — imports `create_app(profile="trust-certifier")`; starts certification evaluation loop
- [X] T054 [P] Write `apps/control-plane/entrypoints/context_engineering_main.py` — imports `create_app(profile="context-engineering")`; starts context assembly workers
- [X] T055 [P] Write `apps/control-plane/entrypoints/agentops_testing_main.py` — imports `create_app(profile="agentops-testing")`; starts evaluation and testing workers
- [X] T056 [P] Write `apps/control-plane/entrypoints/ws_main.py` — imports `create_app(profile="ws-hub")`; starts WebSocket hub on port 8002 with connection management
- [X] T057 Run `ruff check apps/control-plane/src/ --fix` and `mypy --strict apps/control-plane/src/` — resolve all violations before marking complete
- [X] T058 Run `pytest apps/control-plane/tests/ --cov=src/platform --cov-report=term-missing --cov-fail-under=95` — verify ≥95% coverage; add targeted unit tests for any uncovered branches

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2 — MVP deliverable
- **Phase 4 (US2)**: Depends on Phase 2; reads `AsyncEngine` from database.py built in T018
- **Phase 5 (US3)**: Depends on Phase 2 (Base model); independent of US1/US2
- **Phase 6 (US4)**: Depends on Phase 2; independent of US1/US2/US3
- **Phase 7 (US5)**: Depends on Phase 3 (app factory must exist to add middleware)
- **Phase 8 (US6)**: Depends on Phase 3 (extends wrappers started in US1)
- **Phase 9 (US7)**: Depends on Phase 3 (exception handler registered in main.py)
- **Phase 10 (Polish)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational — delivers runnable app + health endpoint
- **US2 (P1)**: Depends on Foundational + T018 (database.py engine) — can parallelize with US1 except for T018 dependency
- **US3 (P1)**: Depends on Foundational only — fully parallel with US1 and US2
- **US4 (P1)**: Depends on Foundational only — fully parallel with US1/US2/US3
- **US5 (P2)**: Depends on US1 (app factory) — middleware added to existing app
- **US6 (P2)**: Depends on US1 (extends wrappers) — add typed methods to existing clients
- **US7 (P2)**: Depends on US1 (exception handler registered in main.py)

### Parallel Opportunities

All T008–T017 (client wrappers in US1) can run in parallel — different files, no cross-dependencies.
All T038–T043 (typed method extensions in US6) can run in parallel.
All entrypoints T050–T056 can run in parallel.
US3, US4 can run fully in parallel with US1 and US2 after Phase 2.

---

## Parallel Example: User Story 1 Client Wrappers

```bash
# All 10 client wrappers can be implemented simultaneously:
Task T008: "Implement redis.py wrapper"
Task T009: "Implement qdrant.py wrapper"
Task T010: "Implement neo4j.py wrapper"
Task T011: "Implement clickhouse.py wrapper"
Task T012: "Implement opensearch.py wrapper"
Task T013: "Implement object_storage.py wrapper"
Task T014: "Implement runtime_controller.py gRPC wrapper"
Task T015: "Implement reasoning_engine.py gRPC wrapper"
Task T016: "Implement sandbox_manager.py gRPC wrapper"
Task T017: "Implement simulation_controller.py gRPC wrapper"

# Then sequentially:
Task T018: "Implement database.py AsyncEngine + sessionmaker"
Task T019: "Implement main.py app factory with lifespan"  # depends on T008-T018
Task T020: "Implement health.py GET /health endpoint"      # depends on T019
```

---

## Implementation Strategy

### MVP First (User Story 1 Only — Runnable App)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T006)
3. Complete Phase 3: US1 (T007–T021)
4. **STOP and VALIDATE**: `python -m entrypoints.api_main` → `/health` returns correct response
5. Demo degraded mode by stopping one store

### Incremental Delivery

1. Setup + Foundational → Base infrastructure
2. US1 → Runnable app with health endpoint (MVP)
3. US2 → Dependency injection for all routes
4. US3 → Mixin library for all bounded context models
5. US4 → Kafka event infrastructure for async coordination
6. US5 → Correlation + auth middleware (production-ready)
7. US6 → Full client wrapper API surface
8. US7 → Standardized errors + pagination
9. Polish → Telemetry, all entrypoints, 95%+ coverage

### Parallel Team Strategy

After Phase 2 (Foundational):
- **Developer A**: US1 (app factory + health + client wrappers)
- **Developer B**: US3 (mixins) + US4 (Kafka events) in sequence
- **Developer C**: US2 (config/DI) then US7 (exceptions/pagination)

---

## Notes

- [P] tasks = different files, no cross-dependencies within the phase
- [Story] label maps task to user story for traceability and independent testing
- All code must pass `ruff check` and `mypy --strict` before T057 (enforce continuously)
- Client wrappers in US1 provide `connect/close/health_check` — US6 adds typed domain methods
- US5 (middleware) must be added AFTER US1 app factory exists (T036 modifies main.py)
- `EventSourcedMixin.pending_events` is a non-mapped transient list — use `__init_subclass__` or a `@declared_attr` with a non-Column attribute to avoid SQLAlchemy mapping it
- Test isolation: unit tests use `AsyncMock` + in-memory SQLite; integration tests require live services (mark with `@pytest.mark.integration`)
