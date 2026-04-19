# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-19

## Active Technologies

- Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane` + gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3 (056-ibor-integration-and)

## Project Structure

```text
src/
tests/
```

## Commands

cd src && pytest && ruff check .

## Code Style

Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane`: Follow standard conventions

## Recent Changes

- 056-ibor-integration-and: Added Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane` + gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
