# Tasks: PostgreSQL Deployment and Schema Foundation

**Input**: Design documents from `specs/001-postgresql-schema-foundation/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- All paths relative to repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory skeleton and project manifests so all user story phases can begin.

- [X] T001 Create directory structure: `deploy/helm/postgresql/templates/`, `apps/control-plane/migrations/versions/`, `apps/control-plane/src/platform/common/models/`, `apps/control-plane/tests/unit/`, `apps/control-plane/tests/integration/`
- [X] T002 [P] Create `deploy/helm/postgresql/Chart.yaml` with name `musematic-postgresql`, version `0.1.0`, description, and CNPG operator dependency reference
- [X] T003 [P] Create `apps/control-plane/pyproject.toml` with dependencies: `sqlalchemy[asyncio]>=2.0`, `alembic>=1.13`, `asyncpg>=0.29`, `pytest>=8`, `pytest-asyncio>=0.23`, `testcontainers[postgresql]>=4`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Helm chart base values and shared Kubernetes templates that US1 and US2 build on.

**⚠️ CRITICAL**: US1 and US2 tasks cannot start until this phase is complete.

- [X] T004 Create `deploy/helm/postgresql/values.yaml` with `environment: production` default and configurable blocks for `postgresql.maxConnections`, `storage.size`, `storage.storageClass`, `resources.requests`, `pgbouncer.maxClientConn`, `pgbouncer.maxDbConnections`, `monitoring.enabled` per the contracts/helm-chart.md interface
- [X] T005 [P] Create `deploy/helm/postgresql/templates/namespace.yaml` creating the `platform-data` Kubernetes namespace
- [X] T006 [P] Create `deploy/helm/postgresql/templates/secret.yaml` templating the `postgres-credentials` Kubernetes Secret (credentials injected via Helm values or external secret operator)

**Checkpoint**: Helm chart skeleton ready — US1 and US2 can start in parallel.

---

## Phase 3: User Story 1 — Platform Operator Deploys Production Database Cluster (Priority: P1) 🎯 MVP

**Goal**: Single `helm install` creates a working 3-node (or 1-node dev) PostgreSQL cluster with monitoring and PodDisruptionBudget.

**Independent Test**: `helm install musematic-postgres deploy/helm/postgresql --set environment=production` creates 3 pods in `platform-data`; deleting the primary pod triggers failover in ≤30s; `curl http://<pod>:9187/metrics` returns `pg_up 1`.

- [X] T007 [US1] Create `deploy/helm/postgresql/templates/cluster.yaml` with `apiVersion: postgresql.cnpg.io/v1` Cluster CRD: instances conditional on `.Values.environment` (3 for production / 1 for development), `postgresql.version: "16"`, parameters block including `synchronous_commit: "on"` and `synchronous_standby_names: "*"` in production only, `storage` from values, `replicationSlots.highAvailability.enabled` conditional, `monitoring.enabled` conditional, `resources` from values
- [X] T008 [US1] Create `deploy/helm/postgresql/templates/pdb.yaml` with `{{- if eq .Values.environment "production" }}` guard, `apiVersion: policy/v1` PodDisruptionBudget, `maxUnavailable: 1`, label selector `cnpg.io/cluster: musematic-postgres` + `role: instance`
- [X] T009 [P] [US1] Create `.github/workflows/db-check.yml` with `helm lint deploy/helm/postgresql` job
- [X] T010 [P] [US1] Add `kubeconform -strict -kubernetes-version 1.29.0` manifest validation step to `.github/workflows/db-check.yml` using `helm template deploy/helm/postgresql | kubeconform`

**Checkpoint**: Helm chart lints cleanly; `helm template` produces valid Kubernetes manifests for both `environment=production` and `environment=development`.

---

## Phase 4: User Story 2 — Application Connects Through Connection Pooling (Priority: P1)

**Goal**: CNPG Pooler CRD deployed in production; all application connections go through PgBouncer in transaction mode; Prometheus metrics available.

**Independent Test**: `kubectl get pooler musematic-pooler -n platform-data` shows 2 ready replicas; `psql "postgresql://...@musematic-pooler:5432/pgbouncer" -c "SHOW POOLS;"` shows active pool entries; `kubectl get podmonitor -n platform-data` shows pooler monitor.

- [X] T011 [US2] Create `deploy/helm/postgresql/templates/pooler.yaml` with `{{- if eq .Values.environment "production" }}` guard, `apiVersion: postgresql.cnpg.io/v1` Pooler CRD referencing cluster `musematic-postgres`, `instances: 2`, `pgbouncer.poolMode: transaction`, `pgbouncer.maxClientConn` from values (default 1000), `pgbouncer.defaultPoolSize` from values (default 10), `pgbouncer.maxDbConnections` from values (default 200), `monitoring.enabled: true`

**Checkpoint**: Full Helm chart (`cluster.yaml` + `pooler.yaml` + `pdb.yaml`) deploys a production-ready cluster with connection pooling in a single `helm install`.

---

## Phase 5: User Story 3 — Developer Runs Database Migrations (Priority: P1)

**Goal**: `make migrate` applies all 7 tables from a fresh database; `make migrate-rollback` cleanly undoes the last migration; CI detects branch conflicts.

**Independent Test**: `DATABASE_URL=postgresql+asyncpg://... make migrate` succeeds on empty database; `\dt` shows all 7 tables; `make migrate-rollback` removes the last migration's tables; `make migrate-check` exits 0.

- [X] T012 [US3] Run `alembic init migrations` in `apps/control-plane/` and configure `apps/control-plane/migrations/alembic.ini`: set `script_location = migrations`, leave `sqlalchemy.url` blank (overridden in env.py)
- [X] T013 [US3] Implement `apps/control-plane/migrations/env.py` with async pattern: import `asyncio`, `create_async_engine`, `pool.NullPool`; define `do_run_migrations(connection: Connection)` calling `context.configure` then `context.run_migrations()`; define `async def run_migrations_online()` creating async engine from `os.environ["DATABASE_URL"]`, using `async with engine.begin() as conn: await conn.run_sync(do_run_migrations)`, then `await engine.dispose()`; call `asyncio.run(run_migrations_online())` at module level
- [X] T014 [US3] Create `apps/control-plane/migrations/versions/001_initial_schema.py` with `upgrade()` creating tables in dependency order: (1) `users` — id UUID PK gen_random_uuid(), email VARCHAR(255) UNIQUE NOT NULL, display_name VARCHAR(255), status VARCHAR(50) DEFAULT 'pending_verification', created_at/updated_at TIMESTAMPTZ DEFAULT now(), deleted_at TIMESTAMPTZ, deleted_by/created_by/updated_by UUID nullable; add self-referencing FKs via `op.create_foreign_key()` after table creation; (2) `workspaces` — id, name, owner_id FK→users, settings JSONB DEFAULT '{}', version INTEGER DEFAULT 1, timestamps, deleted_at/deleted_by; (3) `memberships` — id, workspace_id FK→workspaces, user_id FK→users, role VARCHAR(50) DEFAULT 'member', created_at; UNIQUE(workspace_id, user_id); (4) `sessions` — id, user_id FK→users, token_hash VARCHAR(255), expires_at TIMESTAMPTZ, created_at, revoked_at; indexes on user_id and expires_at; (5) `audit_events` — id, event_type, actor_id, actor_type, workspace_id, resource_type, resource_id, action, details JSONB, occurred_at; indexes on (workspace_id, occurred_at) and (actor_id, occurred_at); (6) `execution_events` — id, execution_id UUID NOT NULL, event_type, step_id, payload JSONB, correlation JSONB, occurred_at; index on (execution_id, occurred_at); (7) `agent_namespaces` — id, name VARCHAR(255) UNIQUE NOT NULL, workspace_id FK→workspaces, description TEXT, created_at, created_by FK→users; index on workspace_id; then `op.execute()` four append-only rules: `CREATE RULE audit_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING`, `audit_no_delete`, `exec_events_no_update`, `exec_events_no_delete`; `downgrade()` drops rules then tables in reverse order
- [X] T015 [P] [US3] Add Makefile targets: `migrate` → `cd apps/control-plane && alembic upgrade head`; `migrate-rollback` → `cd apps/control-plane && alembic downgrade -1`; `migrate-create` → `cd apps/control-plane && alembic revision --autogenerate -m "$(NAME)"`; `migrate-check` → `cd apps/control-plane && alembic branches --verbose`
- [X] T016 [US3] Write `apps/control-plane/tests/integration/test_migrations.py` using `testcontainers[postgresql]` (PostgreSQL 16 image): `test_upgrade_head_from_fresh_db` — apply all migrations, assert all 7 tables exist and `alembic_version` row is present; `test_downgrade_minus_one` — upgrade then downgrade, assert tables from last migration are absent and `alembic_version` rolled back; `test_append_only_audit_events` — insert row, execute raw UPDATE, assert row unchanged; `test_append_only_execution_events` — insert row, execute raw DELETE, assert row still present; `test_migration_chain_linear` — assert `alembic branches` output is empty
- [X] T017 [US3] Add migration chain integrity CI step to `.github/workflows/db-check.yml`: start a PostgreSQL 16 service container, run `make migrate` then `make migrate-check`, fail if branches output is non-empty

**Checkpoint**: `make migrate && make migrate-rollback` succeeds against a fresh PostgreSQL container; all integration tests pass; CI job exits 0.

---

## Phase 6: User Story 4 — Developer Uses SQLAlchemy Models with Standard Behaviors (Priority: P2)

**Goal**: Six reusable mixins (UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, WorkspaceScopedMixin, EventSourcedMixin) work correctly with `AsyncSession`; model files for all core entities exist; ≥95% test coverage.

**Independent Test**: `pytest apps/control-plane/tests/unit/test_mixins.py --cov=platform.common.models` exits 0 with coverage ≥95%.

- [X] T018 [P] [US4] Create `apps/control-plane/src/platform/common/models/base.py` with `from sqlalchemy.orm import DeclarativeBase` and `class Base(DeclarativeBase): pass`
- [X] T019 [US4] Create `apps/control-plane/src/platform/common/models/mixins.py` with all six mixins using SQLAlchemy 2.x `Mapped[]`/`mapped_column()` style: `UUIDMixin` — `id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())`; `TimestampMixin` — `created_at: Mapped[datetime]` with `server_default=func.now()`, `updated_at: Mapped[datetime]` with `server_default=func.now()` and Python-side `onupdate`; `SoftDeleteMixin` — `deleted_at: Mapped[Optional[datetime]]` nullable, `deleted_by: Mapped[Optional[UUID]]` nullable, `@hybrid_property def is_deleted` returning `self.deleted_at is not None`, `@is_deleted.expression` returning `cls.deleted_at.isnot(None)`, classmethod `filter_deleted(cls)` returning `cls.deleted_at.is_(None)`; `AuditMixin` — `created_by: Mapped[Optional[UUID]]` nullable FK→users, `updated_by: Mapped[Optional[UUID]]` nullable FK→users (nullable to support bootstrap); `WorkspaceScopedMixin` — `workspace_id: Mapped[UUID]` non-null FK→workspaces with `index=True`; `EventSourcedMixin` — `version: Mapped[int]` with `default=1`, `__mapper_args__ = {"version_id_col": version}`
- [X] T020 [US4] Create `apps/control-plane/src/platform/common/database.py` with module-level `create_async_engine` from `DATABASE_URL` env var (raise `RuntimeError` if missing), `async_sessionmaker` with `expire_on_commit=False`, `autocommit=False`, `autoflush=False`; `async def get_async_session()` as async generator yielding `AsyncSession` via context manager
- [X] T021 [P] [US4] Create `apps/control-plane/src/platform/common/models/user.py` — `class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin)` with `__tablename__ = "users"`, `email: Mapped[str]`, `display_name: Mapped[Optional[str]]`, `status: Mapped[str]` with `server_default="pending_verification"`
- [X] T022 [P] [US4] Create `apps/control-plane/src/platform/common/models/workspace.py` — `class Workspace(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, EventSourcedMixin)` with `__tablename__ = "workspaces"`, `name: Mapped[str]`, `owner_id: Mapped[UUID]` FK→users, `settings: Mapped[dict]` as `mapped_column(JSONB, server_default="{}")`
- [X] T023 [P] [US4] Create `apps/control-plane/src/platform/common/models/membership.py` — `class Membership(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin)` with `user_id: Mapped[UUID]` FK→users, `role: Mapped[str]` with `server_default="member"`, `UniqueConstraint("workspace_id", "user_id")` in `__table_args__`
- [X] T024 [P] [US4] Create `apps/control-plane/src/platform/common/models/session.py` — `class Session(Base, UUIDMixin, TimestampMixin)` with `user_id: Mapped[UUID]` FK→users, `token_hash: Mapped[str]`, `expires_at: Mapped[datetime]`, `revoked_at: Mapped[Optional[datetime]]`
- [X] T025 [US4] Create `apps/control-plane/src/platform/common/models/__init__.py` re-exporting `Base`, all six mixins, `User`, `Workspace`, `Membership`, `Session`
- [X] T026 [US4] Write `apps/control-plane/tests/unit/test_mixins.py` with 11 test functions covering: UUID auto-generation after flush; `created_at` set on insert; `updated_at` changes on update while `created_at` is invariant; `is_deleted` returns False when `deleted_at` is None; `is_deleted` returns True after soft deletion; `filter_deleted()` classmethod excludes deleted records from query; `filter_deleted()` classmethod includes active records; `version` increments from 1→2 on update; `StaleDataError` raised when two sessions update same record version; records are filterable by `workspace_id`; `created_by`/`updated_by` are nullable for bootstrap scenario

**Checkpoint**: All unit tests pass; `pytest --cov` reports ≥95% on `platform.common.models`.

---

## Phase 7: User Story 5 — Platform Registers Agent Namespaces and FQNs (Priority: P2)

**Goal**: `agent_namespaces` table is created with platform-global unique constraint on `name`; SQLAlchemy model exists; uniqueness violation is verifiable; FQN design is documented for future agent_profiles migration.

**Independent Test**: Insert two `AgentNamespace` rows with the same `name` from different workspaces → second insert raises `IntegrityError`; confirm `psql -c "\d agent_namespaces"` shows UNIQUE constraint on `name`.

- [X] T027 [P] [US5] Create `apps/control-plane/src/platform/common/models/agent_namespace.py` — `class AgentNamespace(Base, UUIDMixin, TimestampMixin)` with `__tablename__ = "agent_namespaces"`, `name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)`, `workspace_id: Mapped[UUID]` FK→workspaces with `index=True`, `description: Mapped[Optional[str]]`, `created_by: Mapped[Optional[UUID]]` FK→users
- [X] T028 [US5] Add `AgentNamespace` to `apps/control-plane/src/platform/common/models/__init__.py` exports
- [X] T029 [US5] Write `apps/control-plane/tests/integration/test_agent_namespaces.py` using `testcontainers`: `test_namespace_unique_name_constraint` — create namespace "finance-ops" for workspace A, attempt same name for workspace B, assert `IntegrityError` is raised; `test_namespace_created_with_workspace_link` — create namespace, query back, assert `workspace_id` matches; `test_fqn_pattern_documented` — assert `AgentNamespace.name` column has unique constraint via SQLAlchemy `inspect()`

**Checkpoint**: `AgentNamespace` model usable in application code; integration tests confirm database-level uniqueness enforcement.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T030 [P] Run `helm lint deploy/helm/postgresql --strict` and fix any warnings or errors
- [X] T031 [P] Run `pytest apps/control-plane/tests/ --cov=platform.common --cov-report=term-missing` and confirm coverage ≥95% on `models/` and `database.py`
- [X] T032 Update `CLAUDE.md` with usage patterns: database session import path, mixin composition conventions, migration workflow commands, connection routing rules (pooler for app, direct for migrations)
- [X] T033 Walk through `specs/001-postgresql-schema-foundation/quickstart.md` steps against actual implementation and fix any discrepancies

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — blocks US1/US2
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2, US3, US4, US5
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (both edit chart, complete US1 first to avoid conflicts)
- **US3 (Phase 5)**: Depends on Phase 1 (directory structure) — independent of US1/US2
- **US4 (Phase 6)**: Depends on Phase 1 (directory structure) — independent of US1/US2; US3 migrations must exist to test against a real DB
- **US5 (Phase 7)**: Depends on US3 (T014 creates `agent_namespaces` table) and US4 (T019 provides mixin patterns)
- **Polish (Final)**: Depends on all desired stories being complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no story dependencies
- **US2 (P1)**: After US1 (adds Pooler to the same Helm chart; complete T007–T010 first to avoid file conflicts)
- **US3 (P1)**: After Phase 1 — no story dependencies; runs in parallel with US1/US2 (different tech stack)
- **US4 (P2)**: After Phase 1 — parallel with US1/US2/US3; needs a running database for integration assertions
- **US5 (P2)**: After US3 (T014) and after US4 (T019) — sequential

### Parallel Opportunities

Within the same phase, all `[P]`-marked tasks use different files and can be executed concurrently by different agents or developers.

---

## Parallel Example: Phase 1 + Phase 5 simultaneously

```bash
# These run in parallel (different tech stacks, different files):
Task (Agent A): "Create deploy/helm/postgresql/Chart.yaml"         # T002
Task (Agent B): "Create apps/control-plane/pyproject.toml"         # T003
```

## Parallel Example: User Story 4

```bash
# After T019 (mixins.py) is complete, these run in parallel:
Task (Agent A): "Create models/user.py"                            # T021
Task (Agent B): "Create models/workspace.py"                       # T022
Task (Agent C): "Create models/membership.py"                      # T023
Task (Agent D): "Create models/session.py"                         # T024
```

---

## Implementation Strategy

### MVP First (US1 + US3 only — runnable platform foundation)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3 (US1): Deployable PostgreSQL cluster
4. Complete Phase 5 (US3): Database schema via migrations
5. **STOP and VALIDATE**: `helm install` + `make migrate` works end-to-end
6. Everything else adds operational quality and developer ergonomics

### Incremental Delivery

1. Phase 1 + 2 → Project scaffold ready
2. US1 → Deployable cluster (operators can verify infra)
3. US2 → Connection pooling live (application traffic safe)
4. US3 → Schema in place (dev team unblocked)
5. US4 → ORM layer (feature development enabled)
6. US5 → Agent mesh foundation (agentic features unblocked)

### Parallel Team Strategy

With multiple developers after Phase 1 + 2:
- **Dev A**: US1 → US2 (Helm chart, infrastructure focus)
- **Dev B**: US3 → US5 (Python, migrations focus)
- **Dev C**: US4 (SQLAlchemy models, can start with mocks while DB is not yet deployed)

---

## Notes

- `[P]` tasks touch different files with no cross-dependencies — safe to parallelize
- `[Story]` labels provide traceability back to `spec.md` user stories
- Append-only rules in T014 use `CREATE RULE ... DO INSTEAD NOTHING` — not triggers — verify with `\d+ audit_events` in psql
- `EventSourcedMixin.__mapper_args__` must be carefully inherited: subclasses that define their own `__mapper_args__` must merge, not replace
- Migration self-referencing FKs in `users` table: create the table first, then add FKs via `op.create_foreign_key()` to avoid forward-reference errors
- All Helm values that are numeric (e.g., `maxClientConn`) must be quoted if used as PostgreSQL parameters
