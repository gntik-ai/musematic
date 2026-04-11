# Data Model: FastAPI Application Scaffold

**Feature**: 013-fastapi-app-scaffold  
**Date**: 2026-04-10  
**Phase**: 1 — Design

---

## SQLAlchemy Base and Mixins

### Declarative Base

```python
# src/platform/common/models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### Mixins

```python
# src/platform/common/models/mixins.py
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, UUID, Boolean, Integer, String, func
from sqlalchemy.ext.hybrid import hybrid_property

class UUIDMixin:
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

class AuditMixin:
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

class WorkspaceScopedMixin:
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)

class EventSourcedMixin:
    version = Column(Integer, nullable=False, default=1)
    # pending_events is transient — not persisted, used for unit-of-work pattern
```

### Usage Pattern

```python
# Any bounded context model follows this mixin order:
class AgentProfile(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, WorkspaceScopedMixin):
    __tablename__ = "agent_profiles"
    name = Column(String, nullable=False)
    # ...concrete columns after mixins
```

---

## Pydantic Settings Model

```python
# src/platform/common/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")
    dsn: str = "postgresql+asyncpg://musematic:musematic@localhost:5432/musematic"
    pool_size: int = 20
    max_overflow: int = 10

class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    url: str = "redis://localhost:6379"
    nodes: list[str] = []
    test_mode: str = "standalone"  # "standalone" or "cluster"

class KafkaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KAFKA_")
    brokers: str = "localhost:9092"
    consumer_group: str = "platform"

class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_")
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334

class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEO4J_")
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "neo4j"

class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")
    host: str = "localhost"
    port: int = 8123

class OpenSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_")
    hosts: str = "http://localhost:9200"

class MinIOSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_")
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    default_bucket: str = "platform-artifacts"

class GRPCSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRPC_")
    runtime_controller: str = "localhost:50051"
    reasoning_engine: str = "localhost:50052"
    sandbox_manager: str = "localhost:50053"
    simulation_controller: str = "localhost:50055"

class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    jwt_secret_key: str = ""  # RS256 public key
    jwt_algorithm: str = "RS256"
    session_ttl_seconds: int = 86400

class OTelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTEL_")
    exporter_endpoint: str = ""
    service_name: str = "musematic-control-plane"

class PlatformSettings(BaseSettings):
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    kafka: KafkaSettings = KafkaSettings()
    qdrant: QdrantSettings = QdrantSettings()
    neo4j: Neo4jSettings = Neo4jSettings()
    clickhouse: ClickHouseSettings = ClickHouseSettings()
    opensearch: OpenSearchSettings = OpenSearchSettings()
    minio: MinIOSettings = MinIOSettings()
    grpc: GRPCSettings = GRPCSettings()
    auth: AuthSettings = AuthSettings()
    otel: OTelSettings = OTelSettings()
    profile: str = "api"  # runtime profile
```

---

## Event Envelope Schema

```python
# src/platform/common/events/envelope.py
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Any

class CorrelationContext(BaseModel):
    workspace_id: UUID | None = None
    conversation_id: UUID | None = None
    interaction_id: UUID | None = None
    execution_id: UUID | None = None
    fleet_id: UUID | None = None
    goal_id: UUID | None = None
    correlation_id: UUID

class EventEnvelope(BaseModel):
    event_type: str
    version: str = "1.0"
    source: str
    correlation_context: CorrelationContext
    trace_context: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any]
```

---

## Exception Hierarchy

```python
# src/platform/common/exceptions.py

class PlatformError(Exception):
    status_code: int = 500
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}

class NotFoundError(PlatformError):
    status_code = 404

class AuthorizationError(PlatformError):
    status_code = 403

class ValidationError(PlatformError):
    status_code = 422

class PolicyViolationError(PlatformError):
    status_code = 403

class BudgetExceededError(PlatformError):
    status_code = 429

class ConvergenceFailedError(PlatformError):
    status_code = 500
```

---

## Pagination Models

```python
# src/platform/common/pagination.py
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False

class OffsetPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
```

---

## Dependency Injection Functions

```python
# src/platform/common/dependencies.py

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield async SQLAlchemy session; commit on success, rollback on exception."""

async def get_current_user(request: Request) -> User:
    """Extract and validate JWT from Authorization header; return User model."""

async def get_workspace(request: Request, db: AsyncSession) -> Workspace:
    """Resolve workspace from X-Workspace-ID header; verify user membership."""
```

---

## Configuration Variables (Environment)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DSN` | required | SQLAlchemy async DSN |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `REDIS_NODES` | empty | Redis cluster nodes (comma-separated) |
| `REDIS_TEST_MODE` | `standalone` | Redis mode: standalone or cluster |
| `KAFKA_BROKERS` | `localhost:9092` | Kafka bootstrap servers |
| `QDRANT_HOST` | `localhost` | Qdrant server host |
| `QDRANT_GRPC_PORT` | `6334` | Qdrant gRPC port |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` | Neo4j credentials |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse HTTP host |
| `CLICKHOUSE_PORT` | `8123` | ClickHouse HTTP port |
| `OPENSEARCH_HOSTS` | `http://localhost:9200` | OpenSearch hosts |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO S3 endpoint |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `minioadmin` | MinIO credentials |
| `GRPC_RUNTIME_CONTROLLER` | `localhost:50051` | RuntimeController address |
| `GRPC_REASONING_ENGINE` | `localhost:50052` | ReasoningEngine address |
| `GRPC_SANDBOX_MANAGER` | `localhost:50053` | SandboxManager address |
| `GRPC_SIMULATION_CONTROLLER` | `localhost:50055` | SimulationController address |
| `AUTH_JWT_SECRET_KEY` | required | RS256 public key for JWT |
| `AUTH_JWT_ALGORITHM` | `RS256` | JWT signing algorithm |
| `OTEL_EXPORTER_ENDPOINT` | optional | OTLP exporter endpoint |
| `PLATFORM_PROFILE` | `api` | Runtime profile |
