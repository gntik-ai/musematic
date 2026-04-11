# Data Model: Connector Plugin Framework

**Branch**: `025-connector-plugin-framework` | **Date**: 2026-04-11 | **Phase**: 1

## SQLAlchemy Models

### Enums

```python
# apps/control-plane/src/platform/connectors/models.py

import enum

class ConnectorTypeSlug(str, enum.Enum):
    SLACK = "slack"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    EMAIL = "email"

class ConnectorInstanceStatus(str, enum.Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"

class ConnectorHealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"

class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"

class DeadLetterResolution(str, enum.Enum):
    PENDING = "pending"
    REDELIVERED = "redelivered"
    DISCARDED = "discarded"
```

### ConnectorType

```python
class ConnectorType(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "connector_types"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    config_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSON Schema for config validation
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecation_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    instances: Mapped[list["ConnectorInstance"]] = relationship(back_populates="connector_type")
```

### ConnectorInstance

```python
class ConnectorInstance(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    __tablename__ = "connector_instances"

    connector_type_id: Mapped[UUID] = mapped_column(ForeignKey("connector_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Credential values replaced with {"$ref": "<key>"}
    status: Mapped[ConnectorInstanceStatus] = mapped_column(
        SQLEnum(ConnectorInstanceStatus), default=ConnectorInstanceStatus.ENABLED, nullable=False
    )
    health_status: Mapped[ConnectorHealthStatus] = mapped_column(
        SQLEnum(ConnectorHealthStatus), default=ConnectorHealthStatus.UNKNOWN, nullable=False
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Delivery metrics
    messages_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_retried: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_dead_lettered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_connector_instances_workspace_id", "workspace_id"),
        Index("ix_connector_instances_workspace_type", "workspace_id", "connector_type_id"),
        UniqueConstraint("workspace_id", "name", name="uq_connector_instance_workspace_name"),
    )

    # Relationships
    connector_type: Mapped["ConnectorType"] = relationship(back_populates="instances")
    credential_refs: Mapped[list["ConnectorCredentialRef"]] = relationship(back_populates="connector_instance", cascade="all, delete-orphan")
    routes: Mapped[list["ConnectorRoute"]] = relationship(back_populates="connector_instance", cascade="all, delete-orphan")
    deliveries: Mapped[list["OutboundDelivery"]] = relationship(back_populates="connector_instance")
```

### ConnectorCredentialRef

```python
class ConnectorCredentialRef(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "connector_credential_refs"

    connector_instance_id: Mapped[UUID] = mapped_column(ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False)
    credential_key: Mapped[str] = mapped_column(String(255), nullable=False)  # Logical name: "bot_token", "signing_secret"
    vault_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # e.g., "workspaces/{ws_id}/connectors/{inst_id}/{key}"
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)  # Workspace isolation

    __table_args__ = (
        UniqueConstraint("connector_instance_id", "credential_key", name="uq_credential_ref_instance_key"),
        Index("ix_credential_refs_workspace_id", "workspace_id"),
    )

    connector_instance: Mapped["ConnectorInstance"] = relationship(back_populates="credential_refs")
```

### ConnectorRoute

```python
class ConnectorRoute(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    __tablename__ = "connector_routes"

    connector_instance_id: Mapped[UUID] = mapped_column(ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Matching conditions (all are optional — empty = match all)
    channel_pattern: Mapped[str | None] = mapped_column(String(512), nullable=True)   # Glob pattern
    sender_pattern: Mapped[str | None] = mapped_column(String(512), nullable=True)    # Glob pattern
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)     # Additional conditions
    # Target
    target_agent_fqn: Mapped[str | None] = mapped_column(String(512), nullable=True)  # e.g., "support-ops:triage-agent"
    target_workflow_id: Mapped[UUID | None] = mapped_column(UUID, nullable=True)       # Alternative: workflow target
    # Ordering
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_connector_routes_workspace_id", "workspace_id"),
        Index("ix_connector_routes_instance_priority", "connector_instance_id", "priority"),
        CheckConstraint(
            "(target_agent_fqn IS NOT NULL) OR (target_workflow_id IS NOT NULL)",
            name="ck_route_has_target"
        ),
    )

    connector_instance: Mapped["ConnectorInstance"] = relationship(back_populates="routes")
```

### OutboundDelivery

```python
class OutboundDelivery(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "outbound_deliveries"

    connector_instance_id: Mapped[UUID] = mapped_column(ForeignKey("connector_instances.id"), nullable=False)
    destination: Mapped[str] = mapped_column(String(1024), nullable=False)  # Channel ID, email address, URL
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)             # Structured message content
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        SQLEnum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)  # [{attempt, error, timestamp}]
    # Correlation
    source_interaction_id: Mapped[UUID | None] = mapped_column(UUID, nullable=True)
    source_execution_id: Mapped[UUID | None] = mapped_column(UUID, nullable=True)

    __table_args__ = (
        Index("ix_outbound_deliveries_workspace_id", "workspace_id"),
        Index("ix_outbound_deliveries_status_retry", "status", "next_retry_at"),
        Index("ix_outbound_deliveries_connector_status", "connector_instance_id", "status"),
    )

    connector_instance: Mapped["ConnectorInstance"] = relationship(back_populates="deliveries")
    dead_letter_entry: Mapped["DeadLetterEntry | None"] = relationship(back_populates="outbound_delivery", uselist=False)
```

### DeadLetterEntry

```python
class DeadLetterEntry(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "dead_letter_entries"

    outbound_delivery_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbound_deliveries.id"), unique=True, nullable=False
    )
    connector_instance_id: Mapped[UUID] = mapped_column(ForeignKey("connector_instances.id"), nullable=False)
    resolution_status: Mapped[DeadLetterResolution] = mapped_column(
        SQLEnum(DeadLetterResolution), default=DeadLetterResolution.PENDING, nullable=False
    )
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # MinIO path if discarded

    __table_args__ = (
        Index("ix_dead_letter_entries_workspace_id", "workspace_id"),
        Index("ix_dead_letter_entries_connector_resolution", "connector_instance_id", "resolution_status"),
    )

    outbound_delivery: Mapped["OutboundDelivery"] = relationship(back_populates="dead_letter_entry")
    connector_instance: Mapped["ConnectorInstance"] = relationship()
```

---

## Plugin Contract (Protocol)

```python
# apps/control-plane/src/platform/connectors/plugin.py

from typing import Protocol, runtime_checkable, Any
from dataclasses import dataclass

@dataclass
class InboundMessage:
    """Normalized inbound message produced by any connector."""
    connector_instance_id: str
    workspace_id: str
    sender_identity: str       # Channel-specific sender ID
    sender_display: str        # Human-readable name
    channel: str               # Channel ID or address
    content_text: str | None
    content_structured: dict | None
    timestamp: datetime
    original_payload: dict     # Raw payload for traceability
    message_id: str | None     # Channel-native message ID for dedup

@dataclass
class DeliveryRequest:
    """Structured outbound delivery request."""
    connector_instance_id: str
    workspace_id: str
    destination: str           # Channel ID, email address, URL
    content_text: str | None
    content_structured: dict | None
    metadata: dict

@dataclass
class HealthCheckResult:
    status: ConnectorHealthStatus
    latency_ms: float | None
    error: str | None

@runtime_checkable
class BaseConnector(Protocol):
    """Plugin contract all connector types must implement."""

    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],  # key → vault_path
    ) -> None:
        """Validate configuration against the connector type's schema. Raises ConnectorConfigError."""
        ...

    async def normalize_inbound(
        self,
        raw_payload: dict[str, Any],
        connector_instance_id: str,
        workspace_id: str,
    ) -> InboundMessage:
        """Normalize raw inbound payload to InboundMessage. Raises NormalizationError."""
        ...

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
        credentials: dict[str, str],  # key → resolved_secret_value (injected at call time)
    ) -> None:
        """Deliver outbound message. Raises DeliveryError on transient failure, DeliveryPermanentError on permanent failure."""
        ...

    async def health_check(
        self,
        config: dict[str, Any],
        credentials: dict[str, str],
    ) -> HealthCheckResult:
        """Check external service reachability."""
        ...
```

---

## Pydantic Schemas

```python
# apps/control-plane/src/platform/connectors/schemas.py

# --- ConnectorType ---
class ConnectorTypeResponse(BaseModel):
    id: UUID
    slug: str
    display_name: str
    description: str | None
    config_schema: dict
    is_deprecated: bool
    created_at: datetime

# --- ConnectorInstance ---
class ConnectorInstanceCreate(BaseModel):
    connector_type_slug: str
    name: str = Field(..., min_length=1, max_length=255)
    config: dict                             # With {"$ref": "key"} for credential fields
    credential_refs: dict[str, str]          # key → vault_path (e.g., {"bot_token": "workspaces/…/bot_token"})

class ConnectorInstanceUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    credential_refs: dict[str, str] | None = None
    status: ConnectorInstanceStatus | None = None

class ConnectorInstanceResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_type: ConnectorTypeResponse
    name: str
    config: dict                             # Credential values masked: {"$ref": "key"} preserved
    status: ConnectorInstanceStatus
    health_status: ConnectorHealthStatus
    last_health_check_at: datetime | None
    health_check_error: str | None
    messages_sent: int
    messages_failed: int
    messages_retried: int
    messages_dead_lettered: int
    created_at: datetime
    updated_at: datetime

# --- ConnectorRoute ---
class ConnectorRouteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connector_instance_id: UUID
    channel_pattern: str | None = None
    sender_pattern: str | None = None
    conditions: dict = Field(default_factory=dict)
    target_agent_fqn: str | None = None
    target_workflow_id: UUID | None = None
    priority: int = Field(default=100, ge=1, le=9999)
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_target(self) -> "ConnectorRouteCreate":
        if not self.target_agent_fqn and not self.target_workflow_id:
            raise ValueError("Either target_agent_fqn or target_workflow_id must be specified")
        return self

class ConnectorRouteUpdate(BaseModel):
    name: str | None = None
    channel_pattern: str | None = None
    sender_pattern: str | None = None
    conditions: dict | None = None
    target_agent_fqn: str | None = None
    target_workflow_id: UUID | None = None
    priority: int | None = Field(None, ge=1, le=9999)
    is_enabled: bool | None = None

class ConnectorRouteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_instance_id: UUID
    name: str
    channel_pattern: str | None
    sender_pattern: str | None
    conditions: dict
    target_agent_fqn: str | None
    target_workflow_id: UUID | None
    priority: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

# --- OutboundDelivery ---
class OutboundDeliveryCreate(BaseModel):
    connector_instance_id: UUID
    destination: str
    content_text: str | None = None
    content_structured: dict | None = None
    priority: int = Field(default=100, ge=1, le=9999)
    source_interaction_id: UUID | None = None
    source_execution_id: UUID | None = None

class OutboundDeliveryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_instance_id: UUID
    destination: str
    status: DeliveryStatus
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    delivered_at: datetime | None
    error_history: list[dict]
    created_at: datetime

# --- DeadLetterEntry ---
class DeadLetterEntryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    outbound_delivery_id: UUID
    connector_instance_id: UUID
    resolution_status: DeadLetterResolution
    dead_lettered_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None
    original_delivery: OutboundDeliveryResponse

class DeadLetterRedeliverRequest(BaseModel):
    note: str | None = None

class DeadLetterDiscardRequest(BaseModel):
    note: str | None = None

# --- Health Check ---
class HealthCheckResponse(BaseModel):
    connector_instance_id: UUID
    status: ConnectorHealthStatus
    latency_ms: float | None
    error: str | None
    checked_at: datetime
```

---

## Service Signatures

```python
# apps/control-plane/src/platform/connectors/service.py

class ConnectorsService:
    # --- Connector Types ---
    async def list_connector_types(self) -> list[ConnectorType]: ...
    async def get_connector_type(self, slug: str) -> ConnectorType: ...

    # --- Connector Instances ---
    async def create_connector_instance(
        self, workspace_id: UUID, data: ConnectorInstanceCreate
    ) -> ConnectorInstance: ...
    async def get_connector_instance(
        self, workspace_id: UUID, instance_id: UUID
    ) -> ConnectorInstance: ...
    async def list_connector_instances(
        self, workspace_id: UUID, type_slug: str | None = None, status: ConnectorInstanceStatus | None = None
    ) -> list[ConnectorInstance]: ...
    async def update_connector_instance(
        self, workspace_id: UUID, instance_id: UUID, data: ConnectorInstanceUpdate
    ) -> ConnectorInstance: ...
    async def delete_connector_instance(
        self, workspace_id: UUID, instance_id: UUID
    ) -> None: ...
    async def run_health_check(
        self, workspace_id: UUID, instance_id: UUID
    ) -> HealthCheckResult: ...

    # --- Connector Routes ---
    async def create_route(
        self, workspace_id: UUID, data: ConnectorRouteCreate
    ) -> ConnectorRoute: ...
    async def get_route(
        self, workspace_id: UUID, route_id: UUID
    ) -> ConnectorRoute: ...
    async def list_routes(
        self, workspace_id: UUID, connector_instance_id: UUID | None = None
    ) -> list[ConnectorRoute]: ...
    async def update_route(
        self, workspace_id: UUID, route_id: UUID, data: ConnectorRouteUpdate
    ) -> ConnectorRoute: ...
    async def delete_route(
        self, workspace_id: UUID, route_id: UUID
    ) -> None: ...
    async def match_route(
        self, connector_instance_id: UUID, workspace_id: UUID, channel: str, sender: str
    ) -> ConnectorRoute | None: ...  # Internal use by inbound handler

    # --- Inbound Processing ---
    async def process_inbound(
        self, connector_instance_id: UUID, raw_payload: dict, request_headers: dict
    ) -> InboundMessage: ...  # Verifies signature (webhook), normalizes, publishes to connector.ingress

    # --- Outbound Delivery ---
    async def create_delivery(
        self, workspace_id: UUID, data: OutboundDeliveryCreate
    ) -> OutboundDelivery: ...
    async def get_delivery(
        self, workspace_id: UUID, delivery_id: UUID
    ) -> OutboundDelivery: ...
    async def list_deliveries(
        self, workspace_id: UUID, connector_instance_id: UUID | None = None,
        status: DeliveryStatus | None = None
    ) -> list[OutboundDelivery]: ...
    async def execute_delivery(
        self, delivery_id: UUID
    ) -> None: ...  # Called by worker; resolves credentials, calls connector, updates retry state

    # --- Dead Letter Queue ---
    async def list_dead_letter_entries(
        self, workspace_id: UUID, connector_instance_id: UUID | None = None,
        resolution: DeadLetterResolution | None = None
    ) -> list[DeadLetterEntry]: ...
    async def get_dead_letter_entry(
        self, workspace_id: UUID, entry_id: UUID
    ) -> DeadLetterEntry: ...
    async def redeliver_dead_letter(
        self, workspace_id: UUID, entry_id: UUID, request: DeadLetterRedeliverRequest
    ) -> OutboundDelivery: ...  # Creates new OutboundDelivery; marks entry as redelivered
    async def discard_dead_letter(
        self, workspace_id: UUID, entry_id: UUID, request: DeadLetterDiscardRequest
    ) -> None: ...  # Archives to MinIO, marks entry as discarded
```

---

## Kafka Event Payloads

```python
# apps/control-plane/src/platform/connectors/events.py

# connector.ingress topic (keyed by connector_instance_id)
class ConnectorIngressPayload(BaseModel):
    """Published when an inbound message is received and normalized."""
    connector_instance_id: str
    workspace_id: str
    sender_identity: str
    sender_display: str
    channel: str
    content_text: str | None
    content_structured: dict | None
    timestamp: str          # ISO 8601
    original_payload: dict
    message_id: str | None
    route_target_agent_fqn: str | None
    route_target_workflow_id: str | None
    route_id: str | None

# connector.delivery topic (keyed by connector_instance_id)
class ConnectorDeliveryRequestPayload(BaseModel):
    """Published by execution BC to request outbound delivery."""
    delivery_id: str
    connector_instance_id: str
    workspace_id: str
    destination: str
    content_text: str | None
    content_structured: dict | None
    priority: int
    source_interaction_id: str | None
    source_execution_id: str | None

# Additional events on connector.ingress topic
class ConnectorDeliverySucceededPayload(BaseModel):
    delivery_id: str
    connector_instance_id: str
    workspace_id: str
    delivered_at: str

class ConnectorDeliveryFailedPayload(BaseModel):
    delivery_id: str
    connector_instance_id: str
    workspace_id: str
    attempt_count: int
    error: str
    next_retry_at: str | None

class ConnectorDeadLetteredPayload(BaseModel):
    delivery_id: str
    dead_letter_entry_id: str
    connector_instance_id: str
    workspace_id: str
    error_history: list[dict]
```

---

## Retry Backoff Calculation

```python
# apps/control-plane/src/platform/connectors/retry.py

BACKOFF_BASE = 4  # seconds
BACKOFF_EXPONENT = 2

def compute_next_retry_at(attempt_count: int) -> datetime:
    """Compute next retry timestamp using exponential backoff.
    attempt_count=1 → 1s, attempt_count=2 → 4s, attempt_count=3 → 16s
    """
    delay_seconds = BACKOFF_BASE ** (attempt_count - 1)  # 4^0=1, 4^1=4, 4^2=16
    return datetime.now(tz=UTC) + timedelta(seconds=delay_seconds)
```

---

## Webhook Signature Verification

```python
# apps/control-plane/src/platform/connectors/security.py

async def verify_webhook_signature(
    request: Request,
    connector_instance_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> None:
    """FastAPI dependency — verifies HMAC-SHA256 signature before route handler."""
    body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Signature")
    if not signature_header:
        raise WebhookSignatureError("Missing signature header")

    # Load signing secret from vault (never cached — always fresh for rotation support)
    instance = await repo.get_connector_instance(connector_instance_id)
    signing_ref = await repo.get_credential_ref(instance.id, "signing_secret")
    signing_secret = await vault.get_secret(signing_ref.vault_path)

    expected = hmac.new(signing_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise WebhookSignatureError("Signature verification failed")
```
