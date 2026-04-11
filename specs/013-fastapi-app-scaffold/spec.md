# Feature Specification: FastAPI Application Scaffold — Control Plane Foundation

**Feature Branch**: `013-fastapi-app-scaffold`  
**Created**: 2026-04-10  
**Status**: Draft  
**Input**: User description: "FastAPI Application Scaffold — foundational app factory, async SQLAlchemy, Kafka event infrastructure, common utilities, dependency injection, client wrappers for 8 data stores and 5 gRPC satellite services"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Application Bootstrap and Health (Priority: P1)

When a platform operator starts the control plane, the application initializes connections to all configured data stores and satellite services, then exposes a health endpoint. The health endpoint returns the connectivity status of each dependency (PostgreSQL, Redis, Kafka, Qdrant, Neo4j, ClickHouse, OpenSearch, MinIO) so operators can diagnose connectivity issues before routing traffic. The application supports multiple runtime profiles (API, scheduler, worker, WebSocket hub, etc.) that share the same codebase but activate different sets of routes and background workers.

**Why this priority**: No bounded context can function without the application factory, database connections, and health checks. This is the foundation all other features build on.

**Independent Test**: Start the application in API profile mode. Hit the health endpoint. Verify it returns 200 with per-dependency status. Stop PostgreSQL — verify the health endpoint reports PostgreSQL as unhealthy while other stores remain healthy.

**Acceptance Scenarios**:

1. **Given** all data stores are running, **When** the application starts in API profile, **Then** it connects to all configured stores and the health endpoint returns 200 with all dependencies marked healthy
2. **Given** one data store is unreachable at startup, **When** the application starts, **Then** it starts successfully (degraded mode) and the health endpoint reports that specific store as unhealthy
3. **Given** 8 different runtime profiles, **When** each profile is started, **Then** only the routes and workers relevant to that profile are activated
4. **Given** the application is running, **When** a graceful shutdown signal is received, **Then** all connections are closed cleanly and in-flight requests are drained

---

### User Story 2 — Configuration and Dependency Injection (Priority: P1)

Platform developers need a centralized configuration system and dependency injection framework. All connection strings, feature flags, and tuning parameters are managed through a single Pydantic Settings model with environment variable overrides. Database sessions, client wrappers, and the current user are provided through FastAPI's dependency injection, ensuring consistent access patterns across all bounded contexts.

**Why this priority**: Every bounded context depends on dependency injection for database access, authentication, and client access. Without this, no routes can be implemented.

**Independent Test**: Define a route that injects a database session and the current user. Verify the session is a valid async SQLAlchemy session and the user is resolved from the JWT token. Change a configuration value via environment variable — verify the application picks up the new value.

**Acceptance Scenarios**:

1. **Given** environment variables for all connection strings, **When** the settings model is loaded, **Then** all connection parameters are available as typed attributes
2. **Given** a route handler that depends on `get_db`, **When** the route is called, **Then** an async SQLAlchemy session is injected and committed/rolled back automatically
3. **Given** a route handler that depends on `get_current_user`, **When** a valid JWT is provided, **Then** the authenticated user is injected into the handler
4. **Given** a route handler that depends on `get_workspace`, **When** a workspace-scoped request is made, **Then** the workspace context is resolved and injected

---

### User Story 3 — Database Models and Mixins (Priority: P1)

Platform developers need a consistent set of SQLAlchemy model mixins that standardize common patterns across all bounded contexts. Every model that needs a UUID primary key, timestamps, soft deletion, audit tracking, workspace scoping, or event sourcing can compose these behaviors through mixins rather than reimplementing them.

**Why this priority**: All bounded contexts create SQLAlchemy models. Without standardized mixins, each context would implement its own UUID generation, timestamp management, and soft delete — leading to inconsistency and bugs.

**Independent Test**: Create a test model using all 6 mixins. Verify UUID is auto-generated, timestamps are set on create/update, soft delete marks the record instead of deleting it, audit fields track who modified the record, workspace scoping filters by workspace_id, and event sourcing appends events.

**Acceptance Scenarios**:

1. **Given** a model using `UUIDMixin`, **When** a record is created without specifying an ID, **Then** a UUID is automatically generated as the primary key
2. **Given** a model using `TimestampMixin`, **When** a record is created or updated, **Then** `created_at` and `updated_at` are set automatically
3. **Given** a model using `SoftDeleteMixin`, **When** a record is deleted, **Then** it is marked as deleted (not removed from the database) and filtered from default queries
4. **Given** a model using `AuditMixin`, **When** a record is modified, **Then** the modifying user and timestamp are recorded
5. **Given** a model using `WorkspaceScopedMixin`, **When** queries are executed, **Then** results are automatically filtered to the current workspace
6. **Given** a model using `EventSourcedMixin`, **When** state changes occur, **Then** events are appended to the event log for that entity

---

### User Story 4 — Kafka Event Infrastructure (Priority: P1)

The platform needs a reliable asynchronous event system for inter-context communication. The event infrastructure provides an async Kafka producer, consumer group manager, canonical event envelope with Pydantic validation, dead-letter queue handling for failed events, and an event type registry that validates event schemas before publishing.

**Why this priority**: Multiple bounded contexts depend on Kafka events for decoupled communication (execution journal projection, analytics ingestion, notification triggers). Without event infrastructure, the platform cannot coordinate across contexts.

**Independent Test**: Publish an event using the canonical envelope. Verify it appears on the correct Kafka topic with proper correlation context. Simulate a processing failure 3 times — verify the event is sent to the dead-letter topic on the 4th attempt.

**Acceptance Scenarios**:

1. **Given** a valid event payload, **When** the producer publishes it, **Then** the event is wrapped in the canonical envelope with correlation context, trace context, and timestamp
2. **Given** a consumer group subscribed to a topic, **When** events arrive, **Then** the consumer deserializes them using the envelope schema and dispatches to registered handlers
3. **Given** an event that fails processing 3 times, **When** the retry limit is exceeded, **Then** the event is published to the dead-letter topic with failure details
4. **Given** an event type registered in the event type registry, **When** an event with that type is published, **Then** the payload is validated against the registered schema before sending
5. **Given** an unregistered event type, **When** someone attempts to publish it, **Then** the publish is rejected with a validation error

---

### User Story 5 — Request Middleware (Priority: P2)

Every HTTP request needs correlation ID propagation (for distributed tracing) and authentication validation (JWT/session). The correlation middleware generates or extracts a correlation ID from request headers and attaches it to the request context, logging context, and outbound Kafka events. The auth middleware validates JWT tokens or session cookies and rejects unauthenticated requests (except for exempted paths like health checks).

**Why this priority**: Correlation and auth are cross-cutting concerns needed before any route can go to production, but bounded contexts can be developed and tested with mock auth during initial development.

**Independent Test**: Send a request without a correlation ID header — verify one is generated and appears in the response headers. Send a request with a correlation ID — verify the same ID is propagated. Send a request without a JWT — verify 401 is returned. Send a valid JWT — verify the request proceeds.

**Acceptance Scenarios**:

1. **Given** a request without an `X-Correlation-ID` header, **When** the middleware processes it, **Then** a new UUID correlation ID is generated and attached to the response and logging context
2. **Given** a request with an `X-Correlation-ID` header, **When** the middleware processes it, **Then** the existing correlation ID is preserved and propagated
3. **Given** a request to a protected endpoint without a valid JWT, **When** the auth middleware processes it, **Then** a 401 Unauthorized response is returned
4. **Given** a request to the health endpoint without a JWT, **When** the auth middleware processes it, **Then** the request is allowed through (health is exempt)
5. **Given** a valid JWT with user claims, **When** the auth middleware processes it, **Then** the user context is available to downstream handlers via dependency injection

---

### User Story 6 — Client Wrappers for External Services (Priority: P2)

Platform developers need thin client wrappers for all external data stores and satellite services. Each wrapper provides async connection management, health check methods, and a minimal API surface appropriate for the store type. The wrappers abstract connection configuration so bounded contexts interact with stores through a consistent interface.

**Why this priority**: Bounded contexts need store access, but can be developed with mocked wrappers initially. Real client wrappers are needed before integration testing.

**Independent Test**: Initialize each client wrapper with valid connection settings. Call the health check method on each. Verify all return healthy. Call a basic operation on each (e.g., insert/query for databases, publish for Kafka, upload for MinIO).

**Acceptance Scenarios**:

1. **Given** valid Qdrant connection settings, **When** the client wrapper is initialized, **Then** it connects and provides async methods for collection operations and vector search
2. **Given** valid Neo4j connection settings, **When** the client wrapper is initialized, **Then** it connects via the async driver and provides methods for Cypher query execution
3. **Given** valid ClickHouse connection settings, **When** the client wrapper is initialized, **Then** it connects via HTTP interface and provides batch insert and query methods
4. **Given** valid OpenSearch connection settings, **When** the client wrapper is initialized, **Then** it provides async search, index, and bulk operations
5. **Given** valid gRPC addresses for satellite services, **When** the RuntimeController/ReasoningEngine/SandboxManager/SimulationController clients are initialized, **Then** they connect via async gRPC channels and provide typed stub methods

---

### User Story 7 — Exception Hierarchy and Pagination (Priority: P2)

The platform needs standardized error handling and pagination patterns. The exception hierarchy maps domain errors to HTTP status codes consistently. Pagination helpers support both cursor-based (for real-time feeds) and offset-based (for admin dashboards) patterns.

**Why this priority**: These utilities are needed by all bounded contexts but are simple enough that bounded contexts can temporarily use raw exceptions and manual pagination during early development.

**Independent Test**: Raise a `NotFoundError` from a route handler — verify 404 is returned with the correct error body format. Request a paginated list with cursor parameters — verify the response includes items and a next cursor.

**Acceptance Scenarios**:

1. **Given** a `PlatformError` subclass raised in a route handler, **When** the exception handler catches it, **Then** the correct HTTP status code and structured error body are returned
2. **Given** a `NotFoundError`, **When** caught by the handler, **Then** 404 is returned; for `AuthorizationError` 403; for `ValidationError` 422; for `PolicyViolationError` 403; for `BudgetExceededError` 429; for `ConvergenceFailedError` 500
3. **Given** a cursor-based pagination request, **When** results are returned, **Then** the response includes items, a next cursor, and indicates whether more results exist
4. **Given** an offset-based pagination request, **When** results are returned, **Then** the response includes items, total count, current page, and total pages

---

### Edge Cases

- What happens when a data store connection fails during startup? The application starts in degraded mode — the health endpoint reports the specific store as unhealthy, but other stores continue to function.
- What happens when a Kafka broker is unreachable? Events are buffered in memory (up to a configurable limit) and retried. If the buffer overflows, events are dropped and logged.
- What happens when a gRPC satellite service is unreachable? The client wrapper returns a connection error. The calling bounded context handles it — the scaffold does not retry at the wrapper level.
- What happens when an event fails schema validation in the event type registry? The publish call raises a `ValidationError` immediately; the event is never sent to Kafka.
- What happens when a JWT token is expired? The auth middleware returns 401 with an "expired" error code. The client must re-authenticate.
- What happens when correlation ID header contains an invalid format? The middleware ignores the invalid value and generates a new UUID.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a FastAPI application factory with configurable lifespan hooks that connect and disconnect all data stores
- **FR-002**: System MUST provide a Pydantic Settings model that reads all connection strings and feature flags from environment variables
- **FR-003**: System MUST provide async SQLAlchemy engine and session factory with 6 composable mixins (UUID, Timestamp, SoftDelete, Audit, WorkspaceScoped, EventSourced)
- **FR-004**: System MUST provide FastAPI dependency injection functions for database sessions (`get_db`), current user (`get_current_user`), and workspace context (`get_workspace`)
- **FR-005**: System MUST provide an async Kafka producer that wraps events in a canonical envelope with correlation context and trace context
- **FR-006**: System MUST provide an async Kafka consumer group manager that deserializes events and dispatches to registered handlers
- **FR-007**: System MUST provide dead-letter queue handling that routes events to a DLQ topic after a configurable number of retries (default: 3)
- **FR-008**: System MUST provide an event type registry that validates event payloads against registered schemas before publishing
- **FR-009**: System MUST provide correlation ID middleware that generates or propagates correlation IDs across requests, logs, and Kafka events
- **FR-010**: System MUST provide JWT/session authentication middleware with configurable path exemptions
- **FR-011**: System MUST provide a health endpoint that returns per-dependency connectivity status
- **FR-012**: System MUST provide client wrappers for all 8 data stores (PostgreSQL, Redis, Qdrant, Neo4j, ClickHouse, OpenSearch, Kafka, MinIO)
- **FR-013**: System MUST provide gRPC client wrappers for all satellite services (RuntimeController, ReasoningEngine, SandboxManager, SimulationController)
- **FR-014**: System MUST provide a domain exception hierarchy mapping to HTTP status codes (404, 403, 422, 429, 500)
- **FR-015**: System MUST provide cursor-based and offset-based pagination helpers
- **FR-016**: System MUST support 8 runtime profiles that share codebase but activate different routes and workers
- **FR-017**: System MUST provide OpenTelemetry instrumentation for traces and metrics across all HTTP and Kafka operations
- **FR-018**: System MUST provide entrypoint scripts for all 8 profiles (api, scheduler, worker, projection-indexer, trust-certifier, context-engineering, agentops-testing, ws-hub)

### Key Entities

- **PlatformSettings**: Centralized configuration model with all connection strings, feature flags, and tuning parameters
- **EventEnvelope**: Canonical event wrapper containing event_type, version, source, correlation_context, trace_context, occurred_at, and typed payload
- **CorrelationContext**: Request-scoped context carrying workspace_id, conversation_id, interaction_id, execution_id, fleet_id, and goal_id
- **PlatformError**: Base exception with code, message, and details; subtypes map to specific HTTP status codes

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Application startup completes within 30 seconds with all stores connected
- **SC-002**: Health endpoint responds within 500 milliseconds with per-store status
- **SC-003**: Correlation ID is present in 100% of request logs, response headers, and outbound Kafka events
- **SC-004**: Event envelope serialization/deserialization roundtrip passes Pydantic validation for all registered event types
- **SC-005**: Dead-letter queue receives events after exactly 3 failed processing attempts
- **SC-006**: All 8 runtime profiles start successfully with their respective route subsets
- **SC-007**: Automated test suite achieves at least 95% code coverage
- **SC-008**: All 8 data store client wrappers pass health check with running dependencies
- **SC-009**: All 4 gRPC client wrappers successfully establish connections to their satellite services
- **SC-010**: JWT validation rejects expired or malformed tokens with correct error codes

## Assumptions

- The control plane codebase already exists at `apps/control-plane/` with the `src/platform/` package structure defined in the constitution
- PostgreSQL database and Alembic migration infrastructure are already in place from feature 001
- Redis cluster is already deployed from feature 002
- Kafka cluster is already deployed from feature 003
- All other data stores (Qdrant, Neo4j, ClickHouse, OpenSearch, MinIO) are deployed from features 004–008
- All gRPC satellite services (RuntimeController, ReasoningEngine, SandboxManager, SimulationController) have proto definitions from features 009–012
- The `common/` package structure follows the constitution repository layout
- This feature creates the scaffold only — individual bounded contexts are implemented in subsequent features
