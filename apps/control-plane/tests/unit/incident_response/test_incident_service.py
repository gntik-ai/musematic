from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.unit.incident_response.support import (
    RecordingProducer,
    RecordingProviderClient,
    make_incident,
    make_integration,
)


class FakeIncidentRepository:
    def __init__(self, integrations: list[Any] | None = None) -> None:
        self.integrations = integrations or []
        self.incidents: dict[UUID, Any] = {}
        self.alerts: dict[UUID, Any] = {}
        self.appended_recurrences: list[tuple[UUID, UUID | None]] = []

    async def find_open_incident_by_fingerprint(self, fingerprint: str) -> Any | None:
        for incident in self.incidents.values():
            if incident.condition_fingerprint == fingerprint and incident.status in {
                "open",
                "acknowledged",
            }:
                return incident
        return None

    async def insert_incident(self, **fields: Any) -> Any:
        incident = make_incident(
            condition_fingerprint=fields["condition_fingerprint"],
            severity=fields["severity"],
            related_executions=list(fields["related_execution_ids"]),
            related_event_ids=list(fields["related_event_ids"]),
            runbook_scenario=fields["runbook_scenario"],
        )
        incident.title = fields["title"]
        incident.description = fields["description"]
        incident.alert_rule_class = fields["alert_rule_class"]
        self.incidents[incident.id] = incident
        return incident

    async def list_integrations(self, *, enabled_only: bool = False) -> list[Any]:
        if enabled_only:
            return [item for item in self.integrations if item.enabled]
        return list(self.integrations)

    async def insert_external_alert(self, *, incident_id: UUID, integration_id: UUID) -> Any:
        alert = _alert(incident_id=incident_id, integration_id=integration_id)
        self.alerts[alert.id] = alert
        return alert

    async def get_external_alert(self, external_alert_id: UUID) -> Any | None:
        return self.alerts.get(external_alert_id)

    async def get_integration(self, integration_id: UUID) -> Any | None:
        return next((item for item in self.integrations if item.id == integration_id), None)

    async def get_incident(self, incident_id: UUID) -> Any | None:
        return self.incidents.get(incident_id)

    async def list_external_alerts_for_incident(self, incident_id: UUID) -> list[Any]:
        return [item for item in self.alerts.values() if item.incident_id == incident_id]

    async def update_external_alert_status(self, external_alert_id: UUID, **fields: Any) -> Any:
        alert = self.alerts[external_alert_id]
        alert.delivery_status = fields["status"]
        if fields.get("provider_reference") is not None:
            alert.provider_reference = fields["provider_reference"]
        alert.last_error = fields.get("error")
        alert.next_retry_at = fields.get("next_retry_at")
        alert.last_attempt_at = datetime.now(UTC)
        if fields.get("increment_attempt"):
            alert.attempt_count += 1
        return alert

    async def append_recurrence(
        self,
        incident_id: UUID,
        related_event_id: UUID | None,
    ) -> Any | None:
        self.appended_recurrences.append((incident_id, related_event_id))
        incident = self.incidents.get(incident_id)
        if incident is not None and related_event_id is not None:
            incident.related_event_ids.append(related_event_id)
        return incident

    async def resolve_incident(
        self,
        incident_id: UUID,
        resolved_at: datetime,
        *,
        status: str = "resolved",
    ) -> Any | None:
        incident = self.incidents.get(incident_id)
        if incident is None:
            return None
        incident.status = status
        incident.resolved_at = resolved_at
        return incident


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        del ttl
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_create_from_signal_writes_incident_alerts_and_triggered_event() -> None:
    pagerduty = make_integration(provider="pagerduty")
    opsgenie = make_integration(provider="opsgenie", mapping={"critical": "P1"})
    repo = FakeIncidentRepository([pagerduty, opsgenie])
    producer = RecordingProducer()
    provider_clients = {
        "pagerduty": RecordingProviderClient(),
        "opsgenie": RecordingProviderClient(),
    }
    service = _service(repo, producer=producer, provider_clients=provider_clients)

    ref = await service.create_from_signal(_signal())
    await _drain_background(service)

    assert ref.external_pages_attempted == 2
    assert ref.no_external_page_attempted is False
    assert len(repo.incidents) == 1
    assert len(repo.alerts) == 2
    assert producer.messages[0]["event_type"] == "incident.triggered"
    assert provider_clients["pagerduty"].created[0]["mapped_severity"] == "critical"
    assert provider_clients["opsgenie"].created[0]["mapped_severity"] == "P1"


@pytest.mark.asyncio
async def test_disabled_integration_keeps_internal_incident_without_external_alert() -> None:
    repo = FakeIncidentRepository([make_integration(enabled=False)])
    service = _service(repo)

    ref = await service.create_from_signal(_signal())
    await _drain_background(service)

    assert ref.no_external_page_attempted is True
    assert ref.external_pages_attempted == 0
    assert len(repo.incidents) == 1
    assert repo.alerts == {}


@pytest.mark.asyncio
async def test_duplicate_open_fingerprint_appends_recurrence_without_new_page() -> None:
    event_id = uuid4()
    existing = make_incident(condition_fingerprint="same-condition")
    repo = FakeIncidentRepository([make_integration()])
    repo.incidents[existing.id] = existing
    redis = FakeRedis()
    redis.values["incident:dedup:same-condition"] = str(existing.id).encode()
    service = _service(repo, redis_client=redis)

    ref = await service.create_from_signal(_signal(fingerprint="same-condition", event_id=event_id))
    await _drain_background(service)

    assert ref.incident_id == existing.id
    assert ref.deduplicated is True
    assert ref.no_external_page_attempted is True
    assert list(repo.incidents) == [existing.id]
    assert repo.alerts == {}
    assert repo.appended_recurrences == [(existing.id, event_id)]


@pytest.mark.asyncio
async def test_missing_severity_mapping_falls_back_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProviderClient()
    repo = FakeIncidentRepository(
        [make_integration(provider="pagerduty", mapping={"warning": "warning"})]
    )
    service = _service(repo, provider_clients={"pagerduty": provider})

    await service.create_from_signal(_signal(severity=IncidentSeverity.critical))
    await _drain_background(service)

    assert provider.created[0]["mapped_severity"] == "critical"
    assert "incident_response_missing_severity_mapping" in caplog.text


@pytest.mark.asyncio
async def test_resolve_sets_resolved_at_emits_event_and_resolves_provider_alert() -> None:
    provider = RecordingProviderClient()
    repo = FakeIncidentRepository([make_integration(provider="pagerduty")])
    producer = RecordingProducer()
    service = _service(repo, producer=producer, provider_clients={"pagerduty": provider})
    ref = await service.create_from_signal(_signal())
    await _drain_background(service)

    resolved_at = datetime.now(UTC)
    response = await service.resolve(ref.incident_id, resolved_at=resolved_at)
    await _drain_background(service)

    alert = next(iter(repo.alerts.values()))
    assert response.status == "resolved"
    assert response.resolved_at == resolved_at
    assert alert.delivery_status == "resolved"
    assert provider.resolved == [
        {
            "integration": repo.integrations[0],
            "provider_reference": f"provider-{ref.incident_id}",
        }
    ]
    assert [message["event_type"] for message in producer.messages] == [
        "incident.triggered",
        "incident.resolved",
    ]


def _signal(
    *,
    fingerprint: str = "rule:workspace",
    event_id: UUID | None = None,
    severity: IncidentSeverity = IncidentSeverity.critical,
) -> IncidentSignal:
    return IncidentSignal(
        alert_rule_class="kafka_lag",
        severity=severity,
        title="Kafka lag above threshold",
        description="Consumer group lag has exceeded the on-call threshold.",
        related_event_ids=[event_id or uuid4()],
        condition_fingerprint=fingerprint,
        runbook_scenario="kafka_lag",
    )


def _service(
    repo: FakeIncidentRepository,
    *,
    producer: RecordingProducer | None = None,
    provider_clients: dict[str, RecordingProviderClient] | None = None,
    redis_client: FakeRedis | None = None,
) -> IncidentService:
    return IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=redis_client,  # type: ignore[arg-type]
        producer=producer or RecordingProducer(),  # type: ignore[arg-type]
        provider_clients=provider_clients or {"pagerduty": RecordingProviderClient()},
    )


def _alert(*, incident_id: UUID, integration_id: UUID) -> Any:
    return type(
        "Alert",
        (),
        {
            "id": uuid4(),
            "incident_id": incident_id,
            "integration_id": integration_id,
            "provider_reference": None,
            "delivery_status": "pending",
            "attempt_count": 0,
            "last_attempt_at": None,
            "last_error": None,
            "next_retry_at": None,
        },
    )()


async def _drain_background(service: IncidentService) -> None:
    while service._background_tasks:
        await asyncio.gather(*list(service._background_tasks))
