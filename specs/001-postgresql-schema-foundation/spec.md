# Feature Specification: PostgreSQL Deployment and Schema Foundation

**Feature Branch**: `001-postgresql-schema-foundation`  
**Created**: 2026-04-09  
**Status**: Draft  
**Input**: User description: "Deploy PostgreSQL 16+ as the relational system-of-record with CloudNativePG operator, connection pooling via PgBouncer, Alembic migration framework, and production-grade HA configuration."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Production Database Cluster (Priority: P1)

A platform operator needs to deploy a highly available PostgreSQL cluster to serve as the relational system-of-record for the Musematic platform. They run a single Helm install command and get a production-ready 3-node cluster with automatic failover, connection pooling, and monitoring.

**Why this priority**: Without a running database cluster, no other platform services can persist data. This is the foundational infrastructure upon which all other features depend.

**Independent Test**: Can be fully tested by deploying the Helm chart to a Kubernetes cluster and verifying that the PostgreSQL cluster accepts connections, replicates data, and recovers from a primary pod failure.

**Acceptance Scenarios**:

1. **Given** a Kubernetes cluster with CloudNativePG operator installed, **When** the operator runs `helm install`, **Then** a 3-node PostgreSQL cluster is created in the `platform-data` namespace with 1 primary and 2 synchronous replicas.
2. **Given** a running 3-node cluster, **When** the primary pod is deleted, **Then** automatic failover promotes a replica to primary within 30 seconds.
3. **Given** a running cluster, **When** the operator checks monitoring endpoints, **Then** Prometheus scrapes pg_exporter metrics including `pg_up`, `pg_stat_activity`, and `pg_replication`.
4. **Given** a running cluster, **When** a pod is restarted, **Then** persistent volume data survives the restart without data loss.

---

### User Story 2 - Application Connects Through Connection Pooling (Priority: P1)

Application services need to connect to PostgreSQL through PgBouncer connection pooling to efficiently manage database connections at scale, preventing connection exhaustion under load.

**Why this priority**: Without connection pooling, production workloads risk exhausting database connections, causing service outages. This is co-priority with the cluster itself.

**Independent Test**: Can be tested by deploying PgBouncer alongside PostgreSQL and verifying that application connections are routed through the pooler while direct PostgreSQL connections remain below the configured maximum.

**Acceptance Scenarios**:

1. **Given** a running PostgreSQL cluster with PgBouncer deployed, **When** application services connect on port 5432, **Then** all connections are routed through PgBouncer in transaction-mode pooling.
2. **Given** PgBouncer is handling connections, **When** concurrent application connections exceed the pooler limit, **Then** connections are queued rather than rejected, and direct PostgreSQL connections remain below the configured maximum server connection count.
3. **Given** PgBouncer is running, **When** the health check endpoint is queried, **Then** it returns a healthy status and Prometheus metrics are available.

---

### User Story 3 - Developer Runs Database Migrations (Priority: P1)

A developer needs to evolve the database schema safely and reproducibly. They use Alembic migrations to apply schema changes, roll back if needed, and ensure migration history remains linear without branch conflicts.

**Why this priority**: Schema migration capability is essential before any application tables can be created. This enables the entire development workflow for data-dependent features.

**Independent Test**: Can be tested by running `alembic upgrade head` on a fresh database, verifying all tables are created, then running `alembic downgrade -1` to roll back the last migration cleanly.

**Acceptance Scenarios**:

1. **Given** a fresh PostgreSQL database, **When** a developer runs `make migrate`, **Then** all migrations are applied in order and the initial schema tables (`users`, `workspaces`, `memberships`, `sessions`, `agent_namespaces`, execution journal, and audit tables) are created.
2. **Given** an up-to-date database, **When** a developer runs `make migrate-rollback`, **Then** the last migration is rolled back cleanly without data corruption.
3. **Given** a CI pipeline, **When** the migration chain integrity check runs, **Then** it verifies no branch conflicts exist in the migration history.

---

### User Story 4 - Developer Uses SQLAlchemy Models with Standard Behaviors (Priority: P2)

A developer building application features uses SQLAlchemy base models with pre-built mixins (UUID primary keys, timestamps, soft delete, audit tracking, workspace scoping, optimistic locking) so they can focus on business logic rather than boilerplate data patterns.

**Why this priority**: Mixins standardize data patterns across the platform, reducing bugs and inconsistency. However, they are only valuable once the migration framework and base tables exist.

**Independent Test**: Can be tested by creating model instances using each mixin, performing CRUD operations with AsyncSession, and verifying the expected behavior (UUID generation, timestamp population, soft delete filtering, version conflict detection).

**Acceptance Scenarios**:

1. **Given** a model using `UUIDMixin`, **When** a new record is created, **Then** it automatically receives a UUID4 primary key.
2. **Given** a model using `TimestampMixin`, **When** a record is created or updated, **Then** `created_at` is set on creation and `updated_at` is set on every update.
3. **Given** a model using `SoftDeleteMixin`, **When** a record is soft-deleted, **Then** it is excluded from default queries but remains in the database.
4. **Given** a model using `EventSourcedMixin`, **When** two concurrent updates target the same record version, **Then** the second update raises a `StaleDataError`.
5. **Given** a model using `WorkspaceScopedMixin`, **When** records are queried, **Then** they are scoped to the correct workspace via the `workspace_id` foreign key.

---

### User Story 5 - Platform Registers Agent Namespaces and FQNs (Priority: P2)

A platform administrator creates agent namespaces to organize agents within workspaces and assigns fully qualified names (FQNs) to agents for unique identification across the platform mesh.

**Why this priority**: The agent namespace and FQN system is foundational for the agentic mesh but depends on the core tables (users, workspaces) being in place first.

**Independent Test**: Can be tested by creating agent namespaces, verifying uniqueness constraints, and confirming that FQN patterns (namespace:local_name) are enforced as unique across the platform.

**Acceptance Scenarios**:

1. **Given** a workspace exists, **When** an administrator creates an agent namespace with a unique name, **Then** the namespace is created and linked to the workspace.
2. **Given** a namespace `finance-ops` exists, **When** another workspace attempts to create a namespace with the same name, **Then** the operation fails with a uniqueness constraint violation.
3. **Given** an agent namespace exists, **When** an agent profile is created with a namespace and local name, **Then** the FQN (namespace:local_name) is unique across the entire platform.

---

### Edge Cases

- What happens when the primary database pod and all replicas fail simultaneously? The system should surface clear error states and not silently lose data.
- How does the system behave when PgBouncer is restarted while active connections exist? Active transactions should complete or fail gracefully.
- What happens when two developers create migrations simultaneously? The CI migration chain integrity check should detect and reject branch conflicts.
- What happens when a soft-deleted record is referenced by a foreign key? Cascading behavior should be defined per-relationship.
- How does optimistic locking behave when the version column is manually set? The system should always use the ORM-managed version.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a highly available PostgreSQL cluster with 1 primary and 2 synchronous replicas in production environments.
- **FR-002**: System MUST provide a single-instance PostgreSQL deployment for development environments.
- **FR-003**: System MUST automatically fail over to a replica within 30 seconds when the primary pod becomes unavailable.
- **FR-004**: System MUST persist data across pod restarts using persistent volume claims.
- **FR-005**: System MUST expose Prometheus-compatible metrics for database monitoring (connection counts, replication status, general health).
- **FR-006**: System MUST route all application database connections through PgBouncer connection pooling in production.
- **FR-007**: System MUST support transaction-mode pooling with a configurable maximum server connection count (default: 200).
- **FR-008**: System MUST provide a migration framework that applies schema changes in a reproducible, ordered sequence.
- **FR-009**: System MUST support rolling back the most recent migration without data corruption.
- **FR-010**: System MUST enforce linear migration history with no branch conflicts, verified in CI.
- **FR-011**: System MUST provide base data models with automatic UUID4 primary key generation.
- **FR-012**: System MUST automatically set creation and update timestamps on all records using the provided timestamp mixin.
- **FR-013**: System MUST support soft deletion with automatic exclusion of deleted records from default queries.
- **FR-014**: System MUST support optimistic locking via version tracking, raising an error on concurrent version conflicts.
- **FR-015**: System MUST support workspace-scoped data access via a workspace identifier on all tenant-scoped entities.
- **FR-016**: System MUST support audit tracking (created by, updated by) on applicable entities.
- **FR-017**: System MUST enforce append-only constraints on audit tables and execution journal (no updates or deletes allowed).
- **FR-018**: System MUST provide an agent namespaces table with a platform-wide unique constraint on namespace name.
- **FR-019**: System MUST enforce uniqueness of agent fully qualified names (namespace:local_name) across the platform.
- **FR-020**: System MUST provide `make migrate` and `make migrate-rollback` targets for developer workflow.

### Key Entities

- **User**: Represents a platform user. Core identity entity referenced by audit and ownership fields across the system.
- **Workspace**: A tenant boundary that groups users, agents, and resources. All tenant-scoped entities reference a workspace.
- **Membership**: Associates users with workspaces, defining which users belong to which tenants.
- **Session**: Tracks active user sessions for authentication and activity purposes.
- **Agent Namespace**: A named grouping for agents within a workspace, unique across the platform. Enables the FQN addressing system for the agentic mesh.
- **Execution Journal**: An append-only log of execution events, supporting event sourcing patterns for audit and replay.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Platform operators can deploy a production-ready database cluster with a single command, completing setup in under 5 minutes.
- **SC-002**: The system recovers from primary database failure within 30 seconds without manual intervention.
- **SC-003**: Database connection pooling supports at least 200 concurrent application connections without connection exhaustion.
- **SC-004**: Developers can apply all schema migrations to a fresh database and have a working schema in under 30 seconds.
- **SC-005**: Rolling back the most recent migration completes without data corruption or orphaned objects.
- **SC-006**: All standard data behaviors (unique identifiers, timestamps, soft delete, optimistic locking) work correctly with 95% or higher test coverage.
- **SC-007**: Agent namespace names are guaranteed unique across the entire platform, with no duplicate entries possible.
- **SC-008**: Monitoring dashboards display database health, connection, and replication metrics within 60 seconds of cluster deployment.

## Assumptions

- CloudNativePG operator is pre-installed on the target Kubernetes cluster before deploying the PostgreSQL Helm chart.
- The target Kubernetes cluster has a storage class available that supports persistent volume claims.
- Prometheus is available in the cluster for scraping metrics from the pg_exporter sidecar.
- PostgreSQL is the sole relational data store; other data stores (Qdrant, OpenSearch, ClickHouse, Redis, Neo4j) handle their respective domains.
- All application code accesses PostgreSQL through SQLAlchemy async sessions; no raw SQL is used in application code.
- Direct PostgreSQL connections (bypassing PgBouncer) are only used by migration scripts and admin tools.
- The agent_profiles table referenced by the FQN fields will be created in a subsequent registry migration; the initial migration only creates the agent_namespaces table and defines the FQN pattern.
- Development environments use a single PostgreSQL instance without PgBouncer for simplicity.
