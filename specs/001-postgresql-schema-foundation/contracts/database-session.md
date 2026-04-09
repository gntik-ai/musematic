# Contract: Database Session Interface

**Feature**: 001-postgresql-schema-foundation  
**Date**: 2026-04-09  
**Type**: Internal — consumed by all application services

---

## Overview

All application code accesses PostgreSQL through the async session interface defined here. No component may open database connections or execute SQL outside this contract.

---

## Session Factory Contract

**Module**: `apps/control-plane/src/platform/common/database.py`

### `get_async_session() → AsyncContextManager[AsyncSession]`

Returns an async context manager that yields a configured `AsyncSession`. The session is automatically closed on context exit.

**Guarantees**:
- Session is not auto-committed — callers must `await session.commit()`
- Session is not auto-flushed — callers control when dirty state is sent to DB
- Connection is pre-pinged before use (`pool_pre_ping=True`)
- Session expires all instances on commit (`expire_on_commit=False` — objects remain accessible after commit)

**Usage**:
```python
from platform.common.database import get_async_session
from sqlalchemy import select
from platform.common.models import User

async with get_async_session() as session:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
```

**Error behavior**:
- If `DATABASE_URL` is not set, raises `RuntimeError` at startup (not at first use)
- If the database is unreachable, raises `sqlalchemy.exc.OperationalError`

---

## Migration Contract

**Tool**: Alembic  
**Config**: `apps/control-plane/migrations/alembic.ini`  
**Env variable**: `DATABASE_URL` (format: `postgresql+asyncpg://user:password@host:port/dbname`)

### `alembic upgrade head`

Applies all pending migrations in linear order. Idempotent if already at head.

**Guarantees**:
- Migrations are applied in revision order
- Each migration runs in a transaction; failure rolls back the migration
- Migration history is stored in `alembic_version` table

**Failure behavior**: If any migration fails, the revision is not recorded and the schema is left at the previous revision.

### `alembic downgrade -1`

Rolls back the most recently applied migration.

**Guarantees**:
- The `downgrade()` function of the latest revision is executed
- The schema returns to the state of the previous revision

---

## Model Mixin Contracts

### `UUIDMixin`

- **Pre-condition**: None
- **Post-condition**: `instance.id` is a valid UUIDv4 after `session.flush()` or `session.commit()`
- **Server behavior**: `gen_random_uuid()` is called by PostgreSQL on INSERT if not provided

### `TimestampMixin`

- **Post-condition**: `created_at` is set on first INSERT; `updated_at` is updated on every UPDATE
- **Invariant**: `created_at` never changes after first INSERT

### `SoftDeleteMixin`

- **Soft-delete**: Set `instance.deleted_at = datetime.utcnow()` and `instance.deleted_by = actor_id`
- **Query filter**: Always apply `where(~ModelClass.is_deleted)` in default queries
- **Invariant**: Soft-deleted records remain in the database and are retrievable by explicit query

### `EventSourcedMixin`

- **Invariant**: `version` is incremented by the ORM on every UPDATE automatically
- **Conflict**: If two sessions read the same `version` and both attempt UPDATE, the second raises `sqlalchemy.exc.StaleDataError`
- **Caller responsibility**: Catch `StaleDataError` and retry or surface to caller

### `WorkspaceScopedMixin`

- **Invariant**: `workspace_id` must be set on INSERT; cannot be NULL
- **Convention**: All queries on workspace-scoped models must include `where(Model.workspace_id == workspace_id)`

### `AuditMixin`

- **Invariant**: `created_by` and `updated_by` must reference a valid user UUID
- **Caller responsibility**: Resolve the current actor's UUID from the request context before persisting

---

## Append-Only Table Contract

Tables `audit_events` and `execution_events` are append-only:

- **Allowed**: `INSERT`
- **Blocked**: `UPDATE`, `DELETE` (silently blocked by PostgreSQL rules — no error raised)
- **Caller contract**: Never attempt to update or delete rows from these tables; use `INSERT` to record corrections or superseding events instead

---

## Connection Routing Contract

| Operation | Connection target | Notes |
|-----------|------------------|-------|
| Application reads/writes | PgBouncer Pooler service (`musematic-pooler:5432`) | Transaction-mode pooling |
| Alembic migrations | Direct PostgreSQL primary (`musematic-postgres-rw:5432`) | Bypasses pooler — required for DDL |
| Admin/debugging | Direct PostgreSQL primary | Requires cluster admin credentials |
