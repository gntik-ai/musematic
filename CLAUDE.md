# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-09

## Active Technologies

- Python 3.11 (application), PostgreSQL 16 (database) + SQLAlchemy 2.x (async ORM), Alembic (migrations), asyncpg (async PostgreSQL driver), CloudNativePG operator (Kubernetes) (HEAD)

## Project Structure

```text
src/
tests/
```

## Commands

cd src && pytest && ruff check .

## Code Style

Python 3.11 (application), PostgreSQL 16 (database): Follow standard conventions

## Recent Changes

- HEAD: Added Python 3.11 (application), PostgreSQL 16 (database) + SQLAlchemy 2.x (async ORM), Alembic (migrations), asyncpg (async PostgreSQL driver), CloudNativePG operator (Kubernetes)

<!-- MANUAL ADDITIONS START -->
- Database session import path: `from platform.common.database import get_async_session`
- Local development imports: run tooling from `apps/control-plane/` with `PYTHONPATH=src`, or install the package with `pip install -e ./apps/control-plane`
- Mixin composition convention:
  `Base` first, then behavior mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`), then concrete columns
- Migration workflow:
  `make migrate`
  `make migrate-rollback`
  `make migrate-create NAME=add_feature`
  `make migrate-check`
- Connection routing rules:
  application traffic goes through `musematic-pooler:5432` in production
  migrations and admin operations go directly to `musematic-postgres-rw:5432`
<!-- MANUAL ADDITIONS END -->
