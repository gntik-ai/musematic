# Implementation Plan: PostgreSQL Deployment and Schema Foundation

**Branch**: `001-postgresql-schema-foundation` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-postgresql-schema-foundation/spec.md`

## Summary

Deploy PostgreSQL 16+ as the platform's relational system-of-record via CloudNativePG operator (Helm chart), with connection pooling via the CNPG Pooler CRD, Alembic migrations for schema versioning, and SQLAlchemy 2.x async models with reusable mixins for all standard data patterns (UUID keys, timestamps, soft delete, audit, workspace scoping, optimistic locking). This is the foundational infrastructure feature — all other platform data features depend on it.

## Technical Context

**Language/Version**: Python 3.11 (application), PostgreSQL 16 (database)  
**Primary Dependencies**: SQLAlchemy 2.x (async ORM), Alembic (migrations), asyncpg (async PostgreSQL driver), CloudNativePG operator (Kubernetes)  
**Storage**: PostgreSQL 16 via CloudNativePG operator (persistent volume claims)  
**Testing**: pytest + pytest-asyncio; `testcontainers` for migration integration tests  
**Target Platform**: Kubernetes (production), local Docker Compose (development)  
**Project Type**: Infrastructure / platform library  
**Performance Goals**: ≤30s failover SLA; PgBouncer supports 200 backend connections  
**Constraints**: All app code uses SQLAlchemy async — no raw SQL; PgBouncer mandatory in production  
**Scale/Scope**: 3-node production cluster; initial schema for 7 tables

## Constitution Check

The project constitution is unfilled (default template). No blocking gates apply. Proceed.

## Project Structure

### Documentation (this feature)

```text
specs/001-postgresql-schema-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 — all unknowns resolved
├── data-model.md        # Phase 1 — entity definitions and mixin reference
├── quickstart.md        # Phase 1 — operator and developer getting-started guide
├── contracts/
│   ├── database-session.md   # Session factory + mixin contracts
│   └── helm-chart.md         # Chart values and Kubernetes resources contract
└── tasks.md             # Phase 2 — created by /speckit.tasks
```

### Source Code (repository root)

```text
deploy/
└── helm/
    └── postgresql/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
            ├── cluster.yaml          # CloudNativePG Cluster CRD
            ├── pooler.yaml           # CNPG Pooler CRD (production only)
            ├── pdb.yaml              # PodDisruptionBudget (production only)
            ├── secret.yaml           # PostgreSQL credentials Secret
            └── namespace.yaml        # platform-data namespace

apps/
└── control-plane/
    ├── migrations/
    │   ├── alembic.ini
    │   ├── env.py
    │   ├── script.py.mako
    │   └── versions/
    │       └── 001_initial_schema.py
    └── src/
        └── platform/
            └── common/
                ├── database.py       # Async engine + session factory
                └── models/
                    ├── __init__.py
                    ├── base.py       # Base declarative base
                    └── mixins.py     # All 6 reusable mixins

Makefile                              # migrate, migrate-rollback, migrate-create targets
```

**Structure Decision**: Infrastructure + application library hybrid. Helm chart lives in `deploy/helm/`; Python code in `apps/control-plane/src/platform/common/`.

## Phase 0: Research — Complete

See [research.md](research.md) for full findings. Key decisions:

| Topic | Decision |
|-------|---------|
| PgBouncer deployment | CNPG Pooler CRD (not standalone Deployment) |
| Synchronous replicas | `synchronous_standby_names: "*"` PostgreSQL parameter |
| PodDisruptionBudget | Separate resource (`maxUnavailable: 1`) |
| Alembic async driver | `asyncpg` + `run_sync` bridge pattern |
| SQLAlchemy version | 2.x `Mapped[]` / `mapped_column()` style |
| Append-only enforcement | PostgreSQL `CREATE RULE` in migrations |
| FQN uniqueness | Derived value; composite unique constraint on future `agent_profiles` |

## Phase 1: Implementation Steps

### Step 1 — Helm Chart: PostgreSQL Cluster CRD

**File**: `deploy/helm/postgresql/templates/cluster.yaml`

Create a CloudNativePG `Cluster` resource templated by `environment` value:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: musematic-postgres
  namespace: platform-data
spec:
  instances: {{ if eq .Values.environment "production" }}3{{ else }}1{{ end }}
  postgresql:
    version: "16"
    parameters:
      max_connections: {{ .Values.postgresql.maxConnections | quote }}
      shared_buffers: "256MB"
      {{- if eq .Values.environment "production" }}
      synchronous_commit: "on"
      synchronous_standby_names: "*"
      {{- end }}
  storage:
    size: {{ .Values.storage.size }}
    storageClass: {{ .Values.storage.storageClass }}
  replicationSlots:
    highAvailability:
      enabled: {{ eq .Values.environment "production" }}
  monitoring:
    enabled: {{ eq .Values.environment "production" }}
  resources:
    requests:
      cpu: {{ .Values.resources.requests.cpu }}
      memory: {{ .Values.resources.requests.memory }}
```

**File**: `deploy/helm/postgresql/values.yaml`

```yaml
environment: production    # Override to "development" for single instance

postgresql:
  maxConnections: "200"

storage:
  size: 100Gi
  storageClass: standard

resources:
  requests:
    cpu: 1000m
    memory: 2Gi
  limits:
    cpu: 2000m
    memory: 4Gi

pgbouncer:
  maxClientConn: 1000
  defaultPoolSize: 10
  maxDbConnections: 200

monitoring:
  enabled: true
```

---

### Step 2 — Helm Chart: CNPG Pooler CRD (Production Only)

**File**: `deploy/helm/postgresql/templates/pooler.yaml`

```yaml
{{- if eq .Values.environment "production" }}
apiVersion: postgresql.cnpg.io/v1
kind: Pooler
metadata:
  name: musematic-pooler
  namespace: platform-data
spec:
  cluster:
    name: musematic-postgres
  instances: 2
  pgbouncer:
    poolMode: transaction
    maxClientConn: {{ .Values.pgbouncer.maxClientConn }}
    defaultPoolSize: {{ .Values.pgbouncer.defaultPoolSize }}
    maxDbConnections: {{ .Values.pgbouncer.maxDbConnections }}
  monitoring:
    enabled: true
{{- end }}
```

---

### Step 3 — Helm Chart: PodDisruptionBudget (Production Only)

**File**: `deploy/helm/postgresql/templates/pdb.yaml`

```yaml
{{- if eq .Values.environment "production" }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: musematic-postgres-pdb
  namespace: platform-data
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      cnpg.io/cluster: musematic-postgres
      role: instance
{{- end }}
```

---

### Step 4 — Async Database Engine Factory

**File**: `apps/control-plane/src/platform/common/database.py`

```python
import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker
)

def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return url

_engine = create_async_engine(
    _database_url(),
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)

_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session
```

---

### Step 5 — SQLAlchemy Base

**File**: `apps/control-plane/src/platform/common/models/base.py`

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

---

### Step 6 — SQLAlchemy Mixins

**File**: `apps/control-plane/src/platform/common/models/mixins.py`

Six mixins using SQLAlchemy 2.x `Mapped[]` / `mapped_column()` style:

- **`UUIDMixin`**: `id: Mapped[UUID]` with `server_default=func.gen_random_uuid()`, `primary_key=True`
- **`TimestampMixin`**: `created_at`, `updated_at` with `server_default=func.now()`; `updated_at` uses `onupdate`
- **`SoftDeleteMixin`**: `deleted_at: Mapped[Optional[datetime]]`, `deleted_by: Mapped[Optional[UUID]]`; `@hybrid_property is_deleted` with SQL expression; `filter_deleted()` classmethod
- **`AuditMixin`**: `created_by`, `updated_by` as `Mapped[Optional[UUID]]` with FK to `users.id` (nullable to support bootstrap)
- **`WorkspaceScopedMixin`**: `workspace_id: Mapped[UUID]` with FK to `workspaces.id` and `index=True`
- **`EventSourcedMixin`**: `version: Mapped[int]` with `__mapper_args__ = {"version_id_col": version}`

Key implementation notes:
- `AuditMixin` columns are nullable for the bootstrap user (first user creation bootstraps itself)
- `EventSourcedMixin.__mapper_args__` is a class variable; subclasses must merge, not replace, it
- `SoftDeleteMixin.filter_deleted()` returns a `ColumnElement` for use in `.where()`, not a pre-filtered query

---

### Step 7 — Alembic Initialization

```bash
cd apps/control-plane
alembic init migrations
```

Configure `migrations/alembic.ini`:
```ini
script_location = migrations
# sqlalchemy.url left blank — overridden from DATABASE_URL in env.py
```

---

### Step 8 — Alembic env.py (Async)

**File**: `apps/control-plane/migrations/env.py`

```python
import asyncio, os
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from platform.common.models.base import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()

asyncio.run(run_migrations_online())
```

---

### Step 9 — Initial Migration

**File**: `apps/control-plane/migrations/versions/001_initial_schema.py`

Creates all 7 tables in dependency order:

1. `users` (self-referencing FKs for `deleted_by`, `created_by`, `updated_by` added after table creation via `op.create_foreign_key()`)
2. `workspaces` (FK → users)
3. `memberships` (FK → workspaces, users; composite unique on `workspace_id, user_id`)
4. `sessions` (FK → users; indexes on `user_id`, `expires_at`)
5. `audit_events` (no external FKs; append-only rules applied after creation)
6. `execution_events` (no external FKs; append-only rules applied after creation)
7. `agent_namespaces` (FK → workspaces, users; global unique on `name`)

Append-only rules (applied in `upgrade()`):
```python
op.execute("CREATE RULE audit_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING")
op.execute("CREATE RULE audit_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING")
op.execute("CREATE RULE exec_events_no_update AS ON UPDATE TO execution_events DO INSTEAD NOTHING")
op.execute("CREATE RULE exec_events_no_delete AS ON DELETE TO execution_events DO INSTEAD NOTHING")
```

Reversed in `downgrade()`:
```python
op.execute("DROP RULE IF EXISTS audit_no_update ON audit_events")
# ... etc
op.drop_table("agent_namespaces")
op.drop_table("execution_events")
op.drop_table("audit_events")
op.drop_table("sessions")
op.drop_table("memberships")
op.drop_table("workspaces")
op.drop_table("users")
```

---

### Step 10 — Makefile Targets

**File**: `Makefile`

```makefile
ALEMBIC = cd apps/control-plane && alembic

.PHONY: migrate migrate-rollback migrate-create migrate-check

migrate:
	$(ALEMBIC) upgrade head

migrate-rollback:
	$(ALEMBIC) downgrade -1

migrate-create:
	$(ALEMBIC) revision --autogenerate -m "$(NAME)"

migrate-check:
	@echo "Checking migration chain for branch conflicts..."
	@$(ALEMBIC) branches --verbose
```

---

### Step 11 — Unit Tests for Mixins (≥95% coverage target)

**File**: `apps/control-plane/tests/unit/test_mixins.py`

| Test | Verifies |
|------|---------|
| `test_uuid_auto_generation` | UUID is non-null and valid v4 after flush |
| `test_created_at_set_on_insert` | `created_at` populated on first commit |
| `test_updated_at_changes_on_update` | `updated_at` changes; `created_at` stays constant |
| `test_soft_delete_is_deleted_false` | `is_deleted` returns `False` when `deleted_at` is None |
| `test_soft_delete_is_deleted_true` | `is_deleted` returns `True` after soft deletion |
| `test_soft_delete_filter_excludes_deleted` | Soft-deleted records excluded from `filter_deleted()` query |
| `test_soft_delete_filter_includes_active` | Active records included in `filter_deleted()` query |
| `test_optimistic_lock_version_increments` | `version` goes from 1 → 2 on update |
| `test_optimistic_lock_stale_error` | `StaleDataError` raised on concurrent version conflict |
| `test_workspace_scoped_query` | Records correctly filtered by `workspace_id` |
| `test_audit_mixin_fk_nullable_for_bootstrap` | `created_by` nullable for bootstrap scenario |

---

### Step 12 — Integration Tests for Migrations

**File**: `apps/control-plane/tests/integration/test_migrations.py`

Uses `testcontainers` (PostgreSQL 16) to validate migrations against a real database:

| Test | Verifies |
|------|---------|
| `test_upgrade_head_from_fresh_db` | All 7 tables created; `alembic_version` at latest |
| `test_downgrade_minus_one` | Last migration tables dropped; version rolled back |
| `test_append_only_audit_events` | UPDATE silently blocked; row unchanged |
| `test_append_only_execution_events` | DELETE silently blocked; row still present |
| `test_agent_namespace_unique_constraint` | Duplicate name raises `IntegrityError` |
| `test_migration_chain_linear` | `alembic branches` returns no branches |

---

### Step 13 — CI Validation

**File**: `.github/workflows/db-check.yml` (or equivalent)

```yaml
jobs:
  migration-check:
    steps:
      - run: make migrate-check
      
  helm-lint:
    steps:
      - run: helm lint deploy/helm/postgresql
      - run: helm template deploy/helm/postgresql | kubeconform -strict -kubernetes-version 1.29.0
```

---

## Complexity Tracking

No constitution violations. Standard infrastructure patterns throughout.

---

## Dependencies

None — this is the foundational feature. All other platform features depend on it.
