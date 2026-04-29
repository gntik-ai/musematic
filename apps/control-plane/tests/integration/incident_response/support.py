from __future__ import annotations

from datetime import UTC, datetime
from platform.incident_response.models import PostMortem
from platform.incident_response.schemas import TimelineSourceCoverage
from platform.incident_response.services.providers.base import ProviderRef
from typing import Any
from uuid import UUID, uuid4

from tests.unit.incident_response.support import make_incident, make_integration


class MemoryIncidentRepository:
    def __init__(self, integrations: list[Any] | None = None) -> None:
        self.integrations = integrations or []
        self.incidents: dict[UUID, Any] = {}
        self.alerts: dict[UUID, Any] = {}
        self.post_mortems: dict[UUID, PostMortem] = {}
        self.appended_recurrences: list[tuple[UUID, UUID | None]] = []

    async def find_open_incident_by_fingerprint(self, fingerprint: str) -> Any | None:
        return next(
            (
                incident
                for incident in self.incidents.values()
                if incident.condition_fingerprint == fingerprint
                and incident.status in {"open", "acknowledged"}
            ),
            None,
        )

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

    async def get_incident(self, incident_id: UUID) -> Any | None:
        return self.incidents.get(incident_id)

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

    async def list_integrations(self, *, enabled_only: bool = False) -> list[Any]:
        if enabled_only:
            return [item for item in self.integrations if item.enabled]
        return list(self.integrations)

    async def insert_integration(self, **fields: Any) -> Any:
        integration = make_integration(
            provider=fields["provider"],
            enabled=fields["enabled"],
            mapping=fields["alert_severity_mapping"],
            key_ref=fields["integration_key_ref"],
        )
        self.integrations.append(integration)
        return integration

    async def get_integration(self, integration_id: UUID) -> Any | None:
        return next((item for item in self.integrations if item.id == integration_id), None)

    async def update_integration(self, integration_id: UUID, **fields: Any) -> Any | None:
        integration = await self.get_integration(integration_id)
        if integration is None:
            return None
        if fields.get("enabled") is not None:
            integration.enabled = fields["enabled"]
        if fields.get("alert_severity_mapping") is not None:
            integration.alert_severity_mapping = fields["alert_severity_mapping"]
        return integration

    async def delete_integration(self, integration_id: UUID) -> bool:
        before = len(self.integrations)
        self.integrations = [item for item in self.integrations if item.id != integration_id]
        return len(self.integrations) != before

    async def insert_external_alert(
        self,
        *,
        incident_id: UUID,
        integration_id: UUID,
    ) -> Any:
        alert = Alert(incident_id=incident_id, integration_id=integration_id)
        self.alerts[alert.id] = alert
        return alert

    async def get_external_alert(self, external_alert_id: UUID) -> Any | None:
        return self.alerts.get(external_alert_id)

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

    async def list_pending_retries(self, now: datetime) -> list[Any]:
        return [
            item
            for item in self.alerts.values()
            if item.delivery_status == "pending"
            and item.next_retry_at is not None
            and item.next_retry_at <= now
        ]

    async def insert_post_mortem(self, **fields: Any) -> PostMortem:
        post_mortem = PostMortem(
            id=fields.get("post_mortem_id") or uuid4(),
            incident_id=fields["incident_id"],
            status="draft",
            timeline=fields["timeline"],
            timeline_blob_ref=fields["timeline_blob_ref"],
            timeline_source_coverage=fields[
                "timeline_source_coverage"
            ] or TimelineSourceCoverage().model_dump(mode="json"),
            impact_assessment=None,
            root_cause=None,
            action_items=None,
            distribution_list=None,
            linked_certification_ids=[],
            blameless=True,
            created_at=datetime.now(UTC),
            created_by=fields["created_by"],
            published_at=None,
            distributed_at=None,
        )
        self.post_mortems[post_mortem.id] = post_mortem
        return post_mortem

    async def get_post_mortem(self, post_mortem_id: UUID) -> PostMortem | None:
        return self.post_mortems.get(post_mortem_id)

    async def get_post_mortem_by_incident(self, incident_id: UUID) -> PostMortem | None:
        return next(
            (item for item in self.post_mortems.values() if item.incident_id == incident_id),
            None,
        )

    async def update_incident_post_mortem(
        self,
        incident_id: UUID,
        post_mortem_id: UUID,
    ) -> None:
        self.incidents[incident_id].post_mortem_id = post_mortem_id

    async def update_post_mortem_section(
        self,
        post_mortem_id: UUID,
        **fields: Any,
    ) -> PostMortem | None:
        post_mortem = self.post_mortems.get(post_mortem_id)
        if post_mortem is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(post_mortem, key, value)
        return post_mortem

    async def append_incident_execution(self, incident_id: UUID, execution_id: UUID) -> Any | None:
        incident = self.incidents.get(incident_id)
        if incident is not None and execution_id not in incident.related_executions:
            incident.related_executions.append(execution_id)
        return incident

    async def append_linked_certification(
        self,
        post_mortem_id: UUID,
        certification_id: UUID,
    ) -> PostMortem | None:
        post_mortem = self.post_mortems.get(post_mortem_id)
        if post_mortem is not None and certification_id not in post_mortem.linked_certification_ids:
            post_mortem.linked_certification_ids.append(certification_id)
        return post_mortem

    async def mark_published(
        self,
        post_mortem_id: UUID,
        published_at: datetime,
    ) -> PostMortem | None:
        post_mortem = self.post_mortems.get(post_mortem_id)
        if post_mortem is None:
            return None
        post_mortem.status = "published"
        post_mortem.published_at = published_at
        return post_mortem

    async def mark_distributed(
        self,
        post_mortem_id: UUID,
        recipients_outcomes: list[dict[str, Any]],
        distributed_at: datetime,
    ) -> PostMortem | None:
        post_mortem = self.post_mortems.get(post_mortem_id)
        if post_mortem is None:
            return None
        post_mortem.status = "distributed"
        post_mortem.distribution_list = recipients_outcomes
        post_mortem.distributed_at = distributed_at
        return post_mortem

    async def list_post_mortems_by_execution(self, execution_id: UUID) -> list[PostMortem]:
        incident_ids = {
            item.id for item in self.incidents.values() if execution_id in item.related_executions
        }
        return [
            item for item in self.post_mortems.values() if item.incident_id in incident_ids
        ]

    async def list_post_mortems_by_certification(self, certification_id: UUID) -> list[PostMortem]:
        return [
            item
            for item in self.post_mortems.values()
            if certification_id in item.linked_certification_ids
        ]


class Alert:
    def __init__(self, *, incident_id: UUID, integration_id: UUID) -> None:
        self.id = uuid4()
        self.incident_id = incident_id
        self.integration_id = integration_id
        self.provider_reference: str | None = None
        self.delivery_status = "pending"
        self.attempt_count = 0
        self.last_attempt_at: datetime | None = None
        self.last_error: str | None = None
        self.next_retry_at: datetime | None = None


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        del ttl
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **payload: Any) -> None:
        self.events.append(payload)


class RecordingProvider:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.resolved: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def create_alert(self, **kwargs: Any) -> ProviderRef:
        self.created.append(kwargs)
        if self.error is not None:
            raise self.error
        return ProviderRef(provider_reference=f"external-{kwargs['incident'].id}")

    async def resolve_alert(self, **kwargs: Any) -> None:
        self.resolved.append(kwargs)


class RecordingAudit:
    def __init__(self) -> None:
        self.entries: list[tuple[Any, str, bytes]] = []

    async def append(self, event_id: Any, source: str, canonical_payload: bytes) -> None:
        self.entries.append((event_id, source, canonical_payload))


class FailingAudit:
    async def append(self, event_id: Any, source: str, canonical_payload: bytes) -> None:
        del event_id, source, canonical_payload
        raise RuntimeError("audit unavailable")


class SecretProvider:
    def __init__(self, value: str = "routing-key") -> None:
        self.value = value

    async def get_current(self, path: str) -> str:
        del path
        return self.value


def enabled_pagerduty(mapping: dict[str, str] | None = None) -> Any:
    return make_integration(provider="pagerduty", mapping=mapping or {"warning": "P3"})
