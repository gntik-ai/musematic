from __future__ import annotations

from datetime import datetime
from platform.connectors.models import (
    ConnectorHealthStatus,
    ConnectorInstanceStatus,
    ConnectorTypeSlug,
    DeadLetterResolution,
    DeliveryStatus,
)
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

SENSITIVE_HINTS = ("token", "secret", "password", "api_key")


def _sanitize_config(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            return {"$ref": value["$ref"]}
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "vault_path":
                continue
            cleaned[key] = _sanitize_config(item, key)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_config(item, parent_key) for item in value]
    if (
        isinstance(value, str)
        and parent_key is not None
        and any(hint in parent_key.lower() for hint in SENSITIVE_HINTS)
    ):
        return "[masked]"
    return value


def _validate_ref_shape(value: Any) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value.keys()) != {"$ref"}:
                raise ValueError("Credential references must only contain a '$ref' field")
            ref_value = value["$ref"]
            if not isinstance(ref_value, str) or not ref_value.strip():
                raise ValueError("Credential reference keys must be non-empty strings")
            return {"$ref": ref_value.strip()}
        return {key: _validate_ref_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_validate_ref_shape(item) for item in value]
    return value


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ConnectorTypeResponse(BaseModel):
    id: UUID
    slug: str
    display_name: str
    description: str | None
    config_schema: dict[str, Any]
    is_deprecated: bool
    deprecated_at: datetime | None
    deprecation_note: str | None


class ConnectorTypeListResponse(BaseModel):
    items: list[ConnectorTypeResponse]
    total: int


class ConnectorInstanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_type_slug: ConnectorTypeSlug
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any]
    credential_refs: dict[str, str] = Field(default_factory=dict)
    status: ConnectorInstanceStatus = ConnectorInstanceStatus.enabled

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("credential_refs")
    @classmethod
    def validate_credential_refs(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, path in value.items():
            if not key.strip() or not path.strip():
                raise ValueError("Credential reference keys and vault paths must be non-empty")
            normalized[key.strip()] = path.strip()
        return normalized

    @field_validator("config")
    @classmethod
    def validate_config_refs(cls, value: dict[str, Any]) -> dict[str, Any]:
        validated = _validate_ref_shape(value)
        if not isinstance(validated, dict):
            raise TypeError("Connector config must be an object.")
        return validated


class ConnectorInstanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    credential_refs: dict[str, str] | None = None
    status: ConnectorInstanceStatus | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("credential_refs")
    @classmethod
    def validate_credential_refs(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        normalized: dict[str, str] = {}
        for key, path in value.items():
            if not key.strip() or not path.strip():
                raise ValueError("Credential reference keys and vault paths must be non-empty")
            normalized[key.strip()] = path.strip()
        return normalized

    @field_validator("config")
    @classmethod
    def validate_config_refs(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        validated = _validate_ref_shape(value)
        if not isinstance(validated, dict):
            raise TypeError("Connector config must be an object.")
        return validated


class ConnectorInstanceResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_type_id: UUID
    connector_type_slug: str
    name: str
    config: dict[str, Any]
    status: ConnectorInstanceStatus
    health_status: ConnectorHealthStatus
    last_health_check_at: datetime | None
    health_check_error: str | None
    messages_sent: int
    messages_failed: int
    messages_retried: int
    messages_dead_lettered: int
    credential_keys: list[str]
    created_at: datetime
    updated_at: datetime

    @field_serializer("config")
    def serialize_config(self, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = _sanitize_config(value)
        if not isinstance(sanitized, dict):
            raise TypeError("Serialized connector config must be an object.")
        return sanitized


class ConnectorInstanceListResponse(BaseModel):
    items: list[ConnectorInstanceResponse]
    total: int


class HealthCheckResponse(BaseModel):
    status: ConnectorHealthStatus
    latency_ms: float | None
    error: str | None = None


class TestConnectivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any] | None = None
    credential_refs: dict[str, str] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_config_refs(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        validated = _validate_ref_shape(value)
        if not isinstance(validated, dict):
            raise TypeError("Connector config must be an object.")
        return validated


class TestResult(BaseModel):
    success: bool
    diagnostic: str
    latency_ms: float


class TestConnectivityResponse(BaseModel):
    connector_instance_id: UUID
    connector_type_slug: str
    result: TestResult


class ConnectorRouteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    channel_pattern: str | None = None
    sender_pattern: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    target_agent_fqn: str | None = None
    target_workflow_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=10_000)
    is_enabled: bool = True

    @field_validator("name", "channel_pattern", "sender_pattern", "target_agent_fqn")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_target(self) -> ConnectorRouteCreate:
        if self.target_agent_fqn is None and self.target_workflow_id is None:
            raise ValueError("At least one route target must be provided")
        return self


class ConnectorRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    channel_pattern: str | None = None
    sender_pattern: str | None = None
    conditions: dict[str, Any] | None = None
    target_agent_fqn: str | None = None
    target_workflow_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    is_enabled: bool | None = None

    @field_validator("name", "channel_pattern", "sender_pattern", "target_agent_fqn")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ConnectorRouteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_instance_id: UUID
    name: str
    channel_pattern: str | None
    sender_pattern: str | None
    conditions: dict[str, Any]
    target_agent_fqn: str | None
    target_workflow_id: UUID | None
    priority: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class ConnectorRouteListResponse(BaseModel):
    items: list[ConnectorRouteResponse]
    total: int


class OutboundDeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_instance_id: UUID
    destination: str = Field(min_length=1, max_length=1024)
    content_text: str | None = None
    content_structured: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10_000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    source_interaction_id: UUID | None = None
    source_execution_id: UUID | None = None

    @field_validator("destination", "content_text")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class OutboundDeliveryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    connector_instance_id: UUID
    destination: str
    content_text: str | None
    content_structured: dict[str, Any] | None
    metadata: dict[str, Any]
    priority: int
    status: DeliveryStatus
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    delivered_at: datetime | None
    error_history: list[dict[str, Any]]
    source_interaction_id: UUID | None
    source_execution_id: UUID | None
    created_at: datetime
    updated_at: datetime


class OutboundDeliveryListResponse(BaseModel):
    items: list[OutboundDeliveryResponse]
    total: int


class DeadLetterEntryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    outbound_delivery_id: UUID
    connector_instance_id: UUID
    resolution_status: DeadLetterResolution
    dead_lettered_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None
    archive_path: str | None
    error_history: list[dict[str, Any]]
    delivery: OutboundDeliveryResponse


class DeadLetterEntryListResponse(BaseModel):
    items: list[DeadLetterEntryResponse]
    total: int


class DeadLetterRedeliverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str | None = None

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class DeadLetterDiscardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str | None = None

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)
