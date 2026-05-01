"""Status page schemas for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OverallState(StrEnum):
    operational = "operational"
    degraded = "degraded"
    partial_outage = "partial_outage"
    full_outage = "full_outage"
    maintenance = "maintenance"


class SourceKind(StrEnum):
    kafka = "kafka"
    poll = "poll"
    fallback = "fallback"
    manual = "manual"


class IncidentSeverity(StrEnum):
    info = "info"
    warning = "warning"
    high = "high"
    critical = "critical"


class IncidentUpdate(BaseModel):
    at: datetime
    text: str


class ComponentStatus(BaseModel):
    id: str
    name: str
    state: OverallState = OverallState.operational
    last_check_at: datetime
    uptime_30d_pct: float | None = Field(default=None, ge=0, le=100)


class ComponentHistoryPoint(BaseModel):
    at: datetime
    state: OverallState


class ComponentDetail(ComponentStatus):
    history_30d: list[ComponentHistoryPoint] = Field(default_factory=list)


class PublicIncident(BaseModel):
    id: str
    title: str
    severity: IncidentSeverity = IncidentSeverity.info
    started_at: datetime
    resolved_at: datetime | None = None
    components_affected: list[str] = Field(default_factory=list)
    last_update_at: datetime
    last_update_summary: str = ""
    updates: list[IncidentUpdate] = Field(default_factory=list)


class MaintenanceWindowSummary(BaseModel):
    window_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    blocks_writes: bool = True
    components_affected: list[str] = Field(default_factory=list)


class UptimeSummary(BaseModel):
    pct: float = Field(ge=0, le=100)
    incidents: int = Field(ge=0)


class PlatformStatusSnapshotPayload(BaseModel):
    overall_state: OverallState = OverallState.operational
    components: list[ComponentStatus] = Field(default_factory=list)
    active_incidents: list[PublicIncident] = Field(default_factory=list)
    scheduled_maintenance: list[MaintenanceWindowSummary] = Field(default_factory=list)
    active_maintenance: MaintenanceWindowSummary | None = None
    recently_resolved_incidents: list[PublicIncident] = Field(default_factory=list)
    uptime_30d: dict[str, UptimeSummary] = Field(default_factory=dict)


class PlatformStatusSnapshotRead(PlatformStatusSnapshotPayload):
    generated_at: datetime
    source_kind: SourceKind = SourceKind.fallback
    snapshot_id: str | None = None


class PublicIncidentsResponse(BaseModel):
    incidents: list[PublicIncident]


class StatusSubscriptionScope(BaseModel):
    scope_components: list[str] = Field(default_factory=list)


class EmailSubscribeRequest(StatusSubscriptionScope):
    email: str


class WebhookSubscribeRequest(StatusSubscriptionScope):
    url: str
    contact_email: str | None = None


class SlackSubscribeRequest(StatusSubscriptionScope):
    webhook_url: str


class AntiEnumerationResponse(BaseModel):
    message: str = "If the address is valid, a confirmation link has been sent."


class WebhookSubscribeResponse(BaseModel):
    subscription_id: str
    signing_secret_hint: str | None = None
    verification_state: str = "pending"


class MyPlatformStatus(BaseModel):
    overall_state: OverallState
    active_maintenance: MaintenanceWindowSummary | None = None
    active_incidents: list[PublicIncident] = Field(default_factory=list)
    affects_my_features: dict[str, list[str]] = Field(default_factory=dict)


class MyStatusSubscription(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    target: str
    scope_components: list[str] = Field(default_factory=list)
    health: str
    confirmed_at: datetime | None = None
    created_at: datetime


class CreateMyStatusSubscriptionRequest(StatusSubscriptionScope):
    channel: str
    target: str


class UpdateMyStatusSubscriptionRequest(BaseModel):
    target: str | None = None
    scope_components: list[str] | None = None


def snapshot_read_from_payload(
    *,
    generated_at: datetime,
    payload: dict[str, Any],
    source_kind: str,
    snapshot_id: str | None = None,
) -> PlatformStatusSnapshotRead:
    parsed = PlatformStatusSnapshotPayload.model_validate(payload)
    return PlatformStatusSnapshotRead(
        **parsed.model_dump(),
        generated_at=generated_at,
        source_kind=SourceKind(source_kind),
        snapshot_id=snapshot_id,
    )
