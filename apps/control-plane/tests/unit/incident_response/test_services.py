from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.incident_response.events import (
    IncidentResolvedPayload,
    IncidentResponseEventType,
    IncidentTriggeredPayload,
    publish_incident_resolved,
    publish_incident_response_event,
    publish_incident_triggered,
    register_incident_response_event_types,
)
from platform.incident_response.exceptions import (
    ExternalAlertNotFoundError,
    IncidentNotFoundError,
    IntegrationNotFoundError,
    IntegrationProviderUnreachableError,
    IntegrationSecretValidationError,
    PostMortemNotFoundError,
    PostMortemOnOpenIncidentError,
    RunbookConcurrentEditError,
    RunbookNotFoundError,
)
from platform.incident_response.models import (
    Incident,
    IncidentExternalAlert,
    IncidentIntegration,
    PostMortem,
    Runbook,
)
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import (
    DiagnosticCommand,
    IncidentSignal,
    PostMortemStatus,
    RunbookCreateRequest,
    RunbookStatus,
    RunbookUpdateRequest,
    TimelineCoverageState,
    TimelineEntry,
    TimelineSource,
    TimelineSourceCoverage,
)
from platform.incident_response.seeds.runbooks_v1 import (
    RUNBOOK_SCENARIOS,
    RUNBOOKS_V1,
    _runbooks_table,
    seed_initial_runbooks,
)
from platform.incident_response.service import IncidentResponseService
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.services.integration_service import IntegrationService
from platform.incident_response.services.kafka_replay import (
    KafkaTimelineReplay,
    _decode,
    _event_type,
    _load_json,
    _payload_summary,
)
from platform.incident_response.services.post_mortem_service import PostMortemService
from platform.incident_response.services.providers.base import (
    BaseHttpPagingProvider,
    ProviderError,
    ProviderRef,
    _redact_headers,
)
from platform.incident_response.services.providers.opsgenie import (
    OpsGenieClient,
    _normalize_priority,
)
from platform.incident_response.services.providers.pagerduty import PagerDutyClient
from platform.incident_response.services.providers.victorops import (
    VictorOpsClient,
    _normalize_message_type,
    _split_secret,
    _to_unix,
)
from platform.incident_response.services.runbook_service import RunbookService
from platform.incident_response.services.timeline_assembler import TimelineAssembler
from platform.incident_response.trigger_interface import (
    NoopIncidentTrigger,
    ServiceIncidentTrigger,
    get_incident_trigger,
    register_incident_trigger,
    reset_incident_trigger,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql

NOW = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def _settings(**overrides: Any) -> PlatformSettings:
    settings = PlatformSettings()
    for key, value in overrides.items():
        setattr(settings.incident_response, key, value)
    return settings


def _integration(
    *,
    provider: str = "pagerduty",
    enabled: bool = True,
    mapping: dict[str, str] | None = None,
) -> IncidentIntegration:
    return IncidentIntegration(
        id=uuid4(),
        provider=provider,
        integration_key_ref="incident-response/integrations/key",
        enabled=enabled,
        alert_severity_mapping=mapping or {"high": "P2", "critical": "P1"},
        created_at=NOW,
        updated_at=NOW,
    )


def _incident(
    *,
    status: str = "open",
    severity: str = "high",
    scenario: str | None = "pod_failure",
    executions: list[UUID] | None = None,
) -> Incident:
    return Incident(
        id=uuid4(),
        condition_fingerprint="fingerprint",
        severity=severity,
        status=status,
        title="Incident title",
        description="Incident description",
        triggered_at=NOW,
        resolved_at=NOW + timedelta(minutes=5) if status in {"resolved", "auto_resolved"} else None,
        related_executions=executions or [uuid4()],
        related_event_ids=[uuid4()],
        runbook_scenario=scenario,
        alert_rule_class="error_rate_spike",
        post_mortem_id=None,
    )


def _alert(
    incident_id: UUID,
    integration_id: UUID,
    *,
    status: str = "pending",
    attempts: int = 0,
    provider_reference: str | None = None,
) -> IncidentExternalAlert:
    return IncidentExternalAlert(
        id=uuid4(),
        incident_id=incident_id,
        integration_id=integration_id,
        provider_reference=provider_reference,
        delivery_status=status,
        attempt_count=attempts,
        last_attempt_at=None,
        last_error=None,
        next_retry_at=NOW,
    )


def _runbook(*, scenario: str = "pod_failure", updated_at: datetime = NOW) -> Runbook:
    return Runbook(
        id=uuid4(),
        scenario=scenario,
        title="Pod failure",
        symptoms="Pods are failing",
        diagnostic_commands=[{"command": "kubectl get pods", "description": "List pods"}],
        remediation_steps="Restart or roll back the affected deployment",
        escalation_path="Escalate to platform runtime",
        status="active",
        version=1,
        created_at=NOW,
        updated_at=updated_at,
        updated_by=None,
    )


def _timeline_entry(*, source: TimelineSource = TimelineSource.audit_chain) -> TimelineEntry:
    return TimelineEntry(
        id=f"{source.value}:1",
        timestamp=NOW,
        source=source,
        event_type="test.event",
        summary="Timeline event",
        payload_summary={"ok": True},
    )


def _post_mortem(
    incident_id: UUID,
    *,
    timeline: list[dict[str, Any]] | None = None,
    blob_ref: str | None = None,
    status: str = "draft",
) -> PostMortem:
    return PostMortem(
        id=uuid4(),
        incident_id=incident_id,
        status=status,
        timeline=timeline,
        timeline_blob_ref=blob_ref,
        timeline_source_coverage=TimelineSourceCoverage().model_dump(mode="json"),
        impact_assessment=None,
        root_cause=None,
        action_items=None,
        distribution_list=None,
        linked_certification_ids=[],
        blameless=True,
        created_at=NOW,
        created_by=None,
        published_at=None,
        distributed_at=None,
    )


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *args: Any) -> None:
        self.events.append(args)


class SecretProvider:
    def __init__(self, *, fail: bool = False, value: str = "secret") -> None:
        self.fail = fail
        self.value = value
        self.paths: list[str] = []

    async def get_current(self, path: str) -> str:
        self.paths.append(path)
        if self.fail:
            raise RuntimeError("secret unavailable")
        return self.value


class ProducerRecorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class RedisRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.values: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> bytes | None:
        if self.fail:
            raise RuntimeError("redis get failed")
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ttl: int) -> None:
        del ttl
        if self.fail:
            raise RuntimeError("redis set failed")
        self.values[key] = value

    async def delete(self, key: str) -> None:
        if self.fail:
            raise RuntimeError("redis delete failed")
        self.deleted.append(key)
        self.values.pop(key, None)


class ProviderClient:
    def __init__(
        self, *, error: Exception | None = None, resolve_error: Exception | None = None
    ) -> None:
        self.error = error
        self.resolve_error = resolve_error
        self.created: list[tuple[UUID, str]] = []
        self.resolved: list[str] = []

    async def create_alert(
        self,
        *,
        integration: IncidentIntegration,
        incident: Incident,
        mapped_severity: str,
    ) -> ProviderRef:
        del integration
        if self.error is not None:
            raise self.error
        self.created.append((incident.id, mapped_severity))
        return ProviderRef(provider_reference=f"ref-{incident.id}")

    async def resolve_alert(
        self,
        *,
        integration: IncidentIntegration,
        provider_reference: str,
    ) -> None:
        del integration
        if self.resolve_error is not None:
            raise self.resolve_error
        self.resolved.append(provider_reference)


class MemoryRepository:
    def __init__(self) -> None:
        self.integrations: dict[UUID, IncidentIntegration] = {}
        self.incidents: dict[UUID, Incident] = {}
        self.alerts: dict[UUID, IncidentExternalAlert] = {}
        self.runbooks: dict[UUID, Runbook] = {}
        self.post_mortems: dict[UUID, PostMortem] = {}
        self.appended_recurrences: list[tuple[UUID, UUID | None]] = []

    async def insert_integration(self, **kwargs: Any) -> IncidentIntegration:
        integration = IncidentIntegration(
            id=uuid4(),
            provider=kwargs["provider"],
            integration_key_ref=kwargs["integration_key_ref"],
            alert_severity_mapping=dict(kwargs["alert_severity_mapping"]),
            enabled=kwargs["enabled"],
            created_at=NOW,
            updated_at=NOW,
        )
        self.integrations[integration.id] = integration
        return integration

    async def get_integration(self, integration_id: UUID) -> IncidentIntegration | None:
        return self.integrations.get(integration_id)

    async def list_integrations(self, *, enabled_only: bool = False) -> list[IncidentIntegration]:
        rows = list(self.integrations.values())
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    async def update_integration(
        self, integration_id: UUID, **fields: Any
    ) -> IncidentIntegration | None:
        integration = self.integrations.get(integration_id)
        if integration is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(integration, key, value)
        integration.updated_at = NOW + timedelta(minutes=1)
        return integration

    async def delete_integration(self, integration_id: UUID) -> bool:
        return self.integrations.pop(integration_id, None) is not None

    async def insert_runbook(self, **kwargs: Any) -> Runbook:
        runbook = Runbook(
            id=uuid4(),
            scenario=kwargs["scenario"],
            title=kwargs["title"],
            symptoms=kwargs["symptoms"],
            diagnostic_commands=list(kwargs["diagnostic_commands"]),
            remediation_steps=kwargs["remediation_steps"],
            escalation_path=kwargs["escalation_path"],
            status=kwargs["status"],
            version=1,
            created_at=NOW,
            updated_at=NOW,
            updated_by=kwargs["updated_by"],
        )
        self.runbooks[runbook.id] = runbook
        return runbook

    async def get_runbook(self, runbook_id: UUID) -> Runbook | None:
        return self.runbooks.get(runbook_id)

    async def get_runbook_by_scenario(self, scenario: str) -> Runbook | None:
        for runbook in self.runbooks.values():
            if runbook.scenario == scenario and runbook.status == "active":
                return runbook
        return None

    async def list_runbooks(
        self,
        *,
        status: str | None,
        scenario_query: str | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[Runbook]:
        rows = list(self.runbooks.values())
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if scenario_query:
            rows = [row for row in rows if scenario_query in row.scenario]
        if cursor is not None:
            rows = [row for row in rows if row.updated_at < cursor]
        return rows[:limit]

    async def update_runbook(
        self,
        runbook_id: UUID,
        *,
        expected_version: int,
        updated_by: UUID | None,
        fields: dict[str, Any],
    ) -> Runbook:
        runbook = self.runbooks[runbook_id]
        if runbook.version != expected_version:
            raise RunbookConcurrentEditError(runbook_id, runbook.version)
        for key, value in fields.items():
            setattr(runbook, key, value)
        runbook.version += 1
        runbook.updated_by = updated_by
        runbook.updated_at = NOW + timedelta(minutes=1)
        return runbook

    async def mark_runbooks_stale(self, threshold_ts: datetime) -> list[Runbook]:
        return [
            runbook
            for runbook in self.runbooks.values()
            if runbook.status == "active" and runbook.updated_at < threshold_ts
        ]

    async def find_open_incident_by_fingerprint(
        self, condition_fingerprint: str
    ) -> Incident | None:
        for incident in self.incidents.values():
            if incident.condition_fingerprint == condition_fingerprint and incident.status in {
                "open",
                "acknowledged",
            }:
                return incident
        return None

    async def append_recurrence(
        self,
        incident_id: UUID,
        related_event_id: UUID | None,
    ) -> Incident | None:
        self.appended_recurrences.append((incident_id, related_event_id))
        incident = self.incidents.get(incident_id)
        if incident is not None and related_event_id is not None:
            incident.related_event_ids.append(related_event_id)
        return incident

    async def insert_incident(self, **kwargs: Any) -> Incident:
        incident = Incident(
            id=uuid4(),
            condition_fingerprint=kwargs["condition_fingerprint"],
            severity=kwargs["severity"],
            status="open",
            title=kwargs["title"],
            description=kwargs["description"],
            triggered_at=NOW,
            resolved_at=None,
            related_executions=list(kwargs["related_execution_ids"]),
            related_event_ids=list(kwargs["related_event_ids"]),
            runbook_scenario=kwargs["runbook_scenario"],
            alert_rule_class=kwargs["alert_rule_class"],
            post_mortem_id=None,
        )
        self.incidents[incident.id] = incident
        return incident

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        return self.incidents.get(incident_id)

    async def list_incidents(self, **kwargs: Any) -> list[Incident]:
        rows = list(self.incidents.values())
        status = kwargs.get("status")
        severity = kwargs.get("severity")
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if severity is not None:
            rows = [row for row in rows if row.severity == severity]
        return rows[: kwargs["limit"]]

    async def resolve_incident(
        self,
        incident_id: UUID,
        resolved_at: datetime,
        *,
        status: str = "resolved",
    ) -> Incident | None:
        incident = self.incidents.get(incident_id)
        if incident is None:
            return None
        incident.status = status
        incident.resolved_at = resolved_at
        return incident

    async def update_incident_post_mortem(self, incident_id: UUID, post_mortem_id: UUID) -> None:
        self.incidents[incident_id].post_mortem_id = post_mortem_id

    async def append_incident_execution(
        self, incident_id: UUID, execution_id: UUID
    ) -> Incident | None:
        incident = self.incidents.get(incident_id)
        if incident is not None and execution_id not in incident.related_executions:
            incident.related_executions.append(execution_id)
        return incident

    async def insert_external_alert(
        self, *, incident_id: UUID, integration_id: UUID
    ) -> IncidentExternalAlert:
        alert = _alert(incident_id, integration_id)
        self.alerts[alert.id] = alert
        return alert

    async def get_external_alert(self, external_alert_id: UUID) -> IncidentExternalAlert | None:
        return self.alerts.get(external_alert_id)

    async def list_external_alerts_for_incident(
        self, incident_id: UUID
    ) -> list[IncidentExternalAlert]:
        return [alert for alert in self.alerts.values() if alert.incident_id == incident_id]

    async def update_external_alert_status(
        self,
        external_alert_id: UUID,
        *,
        status: str,
        provider_reference: str | None = None,
        error: str | None = None,
        next_retry_at: datetime | None = None,
        increment_attempt: bool = False,
    ) -> IncidentExternalAlert | None:
        alert = self.alerts.get(external_alert_id)
        if alert is None:
            return None
        alert.delivery_status = status
        if provider_reference is not None:
            alert.provider_reference = provider_reference
        alert.last_error = error
        alert.next_retry_at = next_retry_at
        alert.last_attempt_at = NOW
        if increment_attempt:
            alert.attempt_count += 1
        return alert

    async def list_pending_retries(self, now: datetime) -> list[IncidentExternalAlert]:
        return [
            alert
            for alert in self.alerts.values()
            if alert.delivery_status == "pending"
            and alert.next_retry_at is not None
            and alert.next_retry_at <= now
        ]

    async def insert_post_mortem(self, **kwargs: Any) -> PostMortem:
        post_mortem = PostMortem(
            id=kwargs.get("post_mortem_id") or uuid4(),
            incident_id=kwargs["incident_id"],
            status="draft",
            timeline=kwargs["timeline"],
            timeline_blob_ref=kwargs["timeline_blob_ref"],
            timeline_source_coverage=kwargs["timeline_source_coverage"],
            impact_assessment=None,
            root_cause=None,
            action_items=None,
            distribution_list=None,
            linked_certification_ids=[],
            blameless=True,
            created_at=NOW,
            created_by=kwargs["created_by"],
            published_at=None,
            distributed_at=None,
        )
        self.post_mortems[post_mortem.id] = post_mortem
        return post_mortem

    async def get_post_mortem(self, post_mortem_id: UUID) -> PostMortem | None:
        return self.post_mortems.get(post_mortem_id)

    async def get_post_mortem_by_incident(self, incident_id: UUID) -> PostMortem | None:
        for post_mortem in self.post_mortems.values():
            if post_mortem.incident_id == incident_id:
                return post_mortem
        return None

    async def update_post_mortem_section(
        self, post_mortem_id: UUID, **fields: Any
    ) -> PostMortem | None:
        post_mortem = self.post_mortems.get(post_mortem_id)
        if post_mortem is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(post_mortem, key, value)
        return post_mortem

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
        self, post_mortem_id: UUID, published_at: datetime
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
            incident.id
            for incident in self.incidents.values()
            if execution_id in incident.related_executions
        }
        return [
            post_mortem
            for post_mortem in self.post_mortems.values()
            if post_mortem.incident_id in incident_ids
        ]

    async def list_post_mortems_by_certification(self, certification_id: UUID) -> list[PostMortem]:
        return [
            post_mortem
            for post_mortem in self.post_mortems.values()
            if certification_id in post_mortem.linked_certification_ids
        ]


@pytest.mark.asyncio
async def test_runbook_and_integration_services_cover_success_and_error_paths() -> None:
    repo = MemoryRepository()
    audit = AuditRecorder()
    runbooks = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=_settings(runbook_freshness_window_days=1),
        audit_chain_service=audit,
    )
    actor = uuid4()

    created = await runbooks.create(
        RunbookCreateRequest(
            scenario="pod_failure",
            title="Pod failure",
            symptoms="Pods fail",
            diagnostic_commands=[
                DiagnosticCommand(command="kubectl get pods", description="List pods")
            ],
            remediation_steps="Restart the pod",
            escalation_path="Escalate to runtime",
            status=RunbookStatus.active,
        ),
        updated_by=actor,
    )
    assert created.scenario == "pod_failure"
    assert await runbooks.get_by_scenario("pod_failure") is not None
    repo.runbooks[created.id].updated_at = NOW - timedelta(days=5)
    assert (await runbooks.list(status="active", scenario_query="pod", cursor=None, limit=10))[
        0
    ].is_stale

    updated = await runbooks.update(
        created.id,
        RunbookUpdateRequest(expected_version=1, title="Updated pod failure"),
        updated_by=actor,
    )
    assert updated.version == 2
    retired = await runbooks.retire(created.id, updated_by=actor)
    assert retired.status == RunbookStatus.retired
    assert runbooks.lookup_by_alert_rule_class("error_rate_spike") == "pod_failure"
    with pytest.raises(RunbookNotFoundError):
        await runbooks.get(uuid4())
    with pytest.raises(RunbookConcurrentEditError):
        await runbooks.update(
            created.id,
            RunbookUpdateRequest(expected_version=1, title="stale"),
            updated_by=actor,
        )

    secrets = SecretProvider()
    integrations = IntegrationService(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=secrets,  # type: ignore[arg-type]
        audit_chain_service=audit,
    )
    integration = await integrations.create(
        provider="pagerduty",
        integration_key_ref="incident-response/integrations/key",
        alert_severity_mapping={"high": "P2"},
    )
    assert integration.enabled is True
    assert len(await integrations.list(enabled_only=True)) == 1
    assert (await integrations.get(integration.id)).provider == "pagerduty"
    assert (await integrations.disable(integration.id)).enabled is False
    assert (await integrations.enable(integration.id)).enabled is True
    assert (
        await integrations.update_severity_mapping(integration.id, {"critical": "P1"})
    ).alert_severity_mapping == {"critical": "P1"}
    assert (await integrations.update(integration.id, enabled=False)).enabled is False
    assert await integrations.resolve_credential(repo.integrations[integration.id]) == "secret"
    await integrations.delete(integration.id)
    with pytest.raises(IntegrationNotFoundError):
        await integrations.get(integration.id)
    with pytest.raises(IntegrationSecretValidationError):
        await IntegrationService(
            repository=repo,  # type: ignore[arg-type]
            secret_provider=SecretProvider(fail=True),  # type: ignore[arg-type]
        ).create(
            provider="opsgenie",
            integration_key_ref="incident-response/integrations/bad",
            alert_severity_mapping={},
        )


@pytest.mark.asyncio
async def test_incident_service_dedup_dispatch_resolution_and_retry_paths() -> None:
    repo = MemoryRepository()
    settings = _settings(delivery_retry_initial_seconds=1, delivery_retry_max_attempts=2)
    redis = RedisRecorder()
    producer = ProducerRecorder()
    provider = ProviderClient()
    runbooks = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
    )
    repo.runbooks[uuid4()] = _runbook()
    integration = _integration()
    repo.integrations[integration.id] = integration
    service = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        redis_client=redis,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
        provider_clients={"pagerduty": provider},
        runbook_service=runbooks,
    )
    scheduled: list[Any] = []
    service._schedule_background = scheduled.append  # type: ignore[method-assign]

    signal = IncidentSignal(
        alert_rule_class="error_rate_spike",
        severity="high",
        title="Title",
        description="Description",
        condition_fingerprint="fingerprint",
        related_event_ids=[uuid4()],
        correlation_context=CorrelationContext(correlation_id=uuid4()),
    )
    created = await service.create_from_signal(signal)
    assert created.external_pages_attempted == 1
    assert producer.events[0]["event_type"] == IncidentResponseEventType.incident_triggered.value
    await scheduled.pop()
    incident = repo.incidents[created.incident_id]
    alert = next(iter(repo.alerts.values()))
    assert alert.delivery_status == "delivered"
    assert provider.created == [(incident.id, "P2")]

    detail = await service.get(incident.id)
    assert detail.runbook is not None
    assert (
        await service.list(
            status="open", severity="high", since=None, until=None, cursor=None, limit=10
        )
    )[0].id == incident.id

    redis.values[service._dedup_key("fingerprint")] = str(incident.id).encode()
    deduped = await service.create_from_signal(signal)
    assert deduped.deduplicated is True
    assert repo.appended_recurrences

    redis.values.clear()
    deduped_without_hint = await service.create_from_signal(signal)
    assert deduped_without_hint.deduplicated is True
    assert redis.values[service._dedup_key("fingerprint")] == str(incident.id).encode()

    unresolved = await service.resolve(incident.id)
    assert unresolved.status == "resolved"
    await scheduled.pop()
    assert alert.delivery_status == "resolved"
    assert redis.deleted == [service._dedup_key("fingerprint")]
    with pytest.raises(IncidentNotFoundError):
        await service.resolve(uuid4())

    missing_alert_id = uuid4()
    with pytest.raises(ExternalAlertNotFoundError):
        await service._dispatch_external_alert(missing_alert_id)

    missing_integration_alert = _alert(incident.id, uuid4())
    repo.alerts[missing_integration_alert.id] = missing_integration_alert
    with pytest.raises(IntegrationNotFoundError):
        await service._dispatch_external_alert(missing_integration_alert.id)
    missing_integration_alert.delivery_status = "failed"

    unknown = _integration(provider="unknown")
    repo.integrations[unknown.id] = unknown
    unknown_alert = _alert(incident.id, unknown.id)
    repo.alerts[unknown_alert.id] = unknown_alert
    await service._dispatch_external_alert(unknown_alert.id)
    assert unknown_alert.delivery_status == "failed"

    retry_provider = ProviderClient(
        error=ProviderError("temporary", provider="pagerduty", retryable=True)
    )
    service.provider_clients["pagerduty"] = retry_provider
    retry_alert = _alert(incident.id, integration.id)
    repo.alerts[retry_alert.id] = retry_alert
    await service._dispatch_external_alert(retry_alert.id)
    assert retry_alert.delivery_status == "pending"
    assert retry_alert.next_retry_at is not None

    service.provider_clients["pagerduty"] = ProviderClient(
        error=ProviderError("bad request", provider="pagerduty", retryable=False)
    )
    fail_alert = _alert(incident.id, integration.id)
    repo.alerts[fail_alert.id] = fail_alert
    await service._dispatch_external_alert(fail_alert.id)
    assert fail_alert.delivery_status == "failed"

    retry_alert.next_retry_at = NOW
    exhausted = _alert(incident.id, integration.id, attempts=2)
    repo.alerts[exhausted.id] = exhausted
    assert await service.retry_due_alerts(NOW + timedelta(seconds=1)) >= 1
    assert exhausted.delivery_status == "failed"

    no_scenario = _incident(scenario=None)
    repo.incidents[no_scenario.id] = no_scenario
    unmapped = await service.get(no_scenario.id)
    assert unmapped.runbook_scenario_unmapped is True
    assert unmapped.runbook_authoring_link.endswith("scenario=new")

    broken_redis = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        redis_client=RedisRecorder(fail=True),  # type: ignore[arg-type]
        producer=None,
        provider_clients={},
    )
    assert await broken_redis._redis_get("key") is None
    await broken_redis._redis_set("key", b"value", 1)
    await broken_redis._redis_delete("key")


@pytest.mark.asyncio
async def test_post_mortem_service_handles_blob_links_distribution_and_errors() -> None:
    repo = MemoryRepository()
    incident = _incident(status="resolved")
    repo.incidents[incident.id] = incident
    entry = _timeline_entry()

    class Assembler:
        async def assemble(
            self, **kwargs: Any
        ) -> tuple[list[TimelineEntry], TimelineSourceCoverage]:
            assert kwargs["incident_id"] == incident.id
            return [entry], TimelineSourceCoverage()

    class ObjectStorage:
        def __init__(self) -> None:
            self.objects: dict[tuple[str, str], bytes] = {}

        async def create_bucket_if_not_exists(self, bucket: str) -> None:
            self.bucket = bucket

        async def put_object(
            self,
            bucket: str,
            key: str,
            payload: bytes,
            *,
            content_type: str,
        ) -> None:
            assert content_type == "application/json"
            self.objects[(bucket, key)] = payload

        async def get_object(self, bucket: str, key: str) -> bytes:
            return self.objects[(bucket, key)]

    class Alerts:
        async def send_post_mortem(self, *, recipient: str) -> None:
            if recipient == "bad@example.com":
                raise RuntimeError("bounce")

    audit = AuditRecorder()
    storage = ObjectStorage()
    service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=_settings(postmortem_blob_threshold_bytes=1),
        timeline_assembler=Assembler(),  # type: ignore[arg-type]
        object_storage=storage,  # type: ignore[arg-type]
        alert_service=Alerts(),
        audit_chain_service=audit,
    )

    started = await service.start(incident.id, by_user_id=uuid4())
    assert started.timeline_blob_ref is not None
    assert started.timeline == [entry]
    assert await service.start(incident.id, by_user_id=None) == started
    assert (await service.get(started.id)).id == started.id
    assert (await service.get_by_incident(incident.id)).id == started.id
    saved = await service.save_section(
        started.id,
        impact_assessment="impact",
        root_cause="root",
        action_items=[{"owner": "ops"}],
    )
    assert saved.impact_assessment == "impact"
    execution_id = incident.related_executions[0]
    certification_id = uuid4()
    assert (await service.link_execution(started.id, execution_id)).id == started.id
    assert (
        await service.link_certification(started.id, certification_id)
    ).linked_certification_ids == [certification_id]
    assert (await service.mark_blameless(started.id)).blameless is True
    assert (await service.publish(started.id)).status == PostMortemStatus.published
    distributed = await service.distribute(
        started.id,
        ["ok@example.com", "bad@example.com"],
    )
    assert distributed.status == PostMortemStatus.distributed
    assert distributed.distribution_list is not None
    assert distributed.distribution_list[1]["outcome"].startswith("failed:")
    assert (await service.find_for_execution(execution_id))[0].id == started.id
    assert (await service.find_for_certification(certification_id))[0].id == started.id

    open_incident = _incident(status="open")
    repo.incidents[open_incident.id] = open_incident
    with pytest.raises(PostMortemOnOpenIncidentError):
        await service.start(open_incident.id, by_user_id=None)
    with pytest.raises(IncidentNotFoundError):
        await service.start(uuid4(), by_user_id=None)
    with pytest.raises(PostMortemNotFoundError):
        await service.get(uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.get_by_incident(uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.save_section(uuid4(), impact_assessment="missing")
    with pytest.raises(PostMortemNotFoundError):
        await service.link_execution(uuid4(), uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.link_certification(uuid4(), uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.mark_blameless(uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.publish(uuid4())
    with pytest.raises(PostMortemNotFoundError):
        await service.distribute(uuid4(), ["ops@example.com"])

    inline, blob_ref = await service._maybe_spill_timeline(uuid4(), [{"small": True}])
    assert inline is not None or blob_ref is not None
    no_storage_service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=_settings(postmortem_blob_threshold_bytes=1),
        timeline_assembler=Assembler(),  # type: ignore[arg-type]
        object_storage=None,
    )
    assert (await no_storage_service._maybe_spill_timeline(uuid4(), [{"large": "x" * 100}]))[
        0
    ] is not None


@pytest.mark.asyncio
async def test_timeline_assembler_and_kafka_replay_cover_success_partial_and_failure_paths() -> (
    None
):
    repo = MemoryRepository()
    execution_id = uuid4()
    incident = _incident(status="resolved", executions=[execution_id])
    repo.incidents[incident.id] = incident

    class Audit:
        async def list_audit_sources_in_window(self, start: datetime, end: datetime) -> list[Any]:
            del start, end
            return [
                SimpleNamespace(
                    id=uuid4(),
                    created_at=NOW + timedelta(seconds=2),
                    audit_event_source="audit.event",
                    sequence_number=5,
                    audit_event_id=None,
                )
            ]

    class Execution:
        async def get_journal_in_window(
            self,
            executions: list[UUID],
            start: datetime,
            end: datetime,
        ) -> list[Any]:
            del start, end
            assert executions == [execution_id]
            return [
                SimpleNamespace(
                    id=uuid4(),
                    created_at=NOW + timedelta(seconds=1),
                    event_type="runtime.completed",
                    execution_id=execution_id,
                    sequence=7,
                    step_id="step",
                )
            ]

    class Replay:
        last_window_partial = True

        async def read_window(
            self,
            topics: list[str],
            start: datetime,
            end: datetime,
        ) -> list[TimelineEntry]:
            del topics, start, end
            return [_timeline_entry(source=TimelineSource.kafka)]

    assembler = TimelineAssembler(
        repository=repo,  # type: ignore[arg-type]
        audit_chain_service=Audit(),
        execution_service=Execution(),
        kafka_replay=Replay(),  # type: ignore[arg-type]
        kafka_topics=["topic"],
    )
    entries, coverage = await assembler.assemble(
        incident_id=incident.id,
        window_start=NOW,
        window_end=NOW + timedelta(minutes=1),
    )
    assert [entry.source for entry in entries] == [
        TimelineSource.kafka,
        TimelineSource.execution_journal,
        TimelineSource.audit_chain,
    ]
    assert coverage.kafka == TimelineCoverageState.partial

    failing = TimelineAssembler(
        repository=repo,  # type: ignore[arg-type]
        audit_chain_service=None,
        execution_service=None,
        kafka_replay=None,
        kafka_topics=[],
    )
    _, failed_coverage = await failing.assemble(
        incident_id=incident.id,
        window_start=NOW,
        window_end=NOW,
    )
    assert failed_coverage.audit_chain == TimelineCoverageState.unavailable
    assert failed_coverage.execution_journal == TimelineCoverageState.unavailable
    assert failed_coverage.kafka == TimelineCoverageState.unavailable
    with pytest.raises(IncidentNotFoundError):
        await failing.assemble(incident_id=uuid4(), window_start=NOW, window_end=NOW)

    assert _decode(b"text") == "text"
    assert _decode(b"\xff") is None
    assert _load_json(json.dumps({"event_type": "a"}).encode()) == {"event_type": "a"}
    assert _load_json(b"not json") == {}
    assert _event_type(json.dumps({"type": "legacy"}).encode()) == "legacy"
    assert _payload_summary(json.dumps({"event_type": "a", "id": "1"}).encode()) == "a 1"
    assert _payload_summary(None).startswith("Kafka event ")

    class FakeConsumer:
        def __init__(self, *topics: str, **kwargs: Any) -> None:
            del kwargs
            self.topics = topics
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

        def partitions_for_topic(self, topic: str) -> set[int]:
            return {0} if topic == "topic" else set()

        async def offsets_for_times(self, mapping: dict[Any, int]) -> dict[Any, Any]:
            return {next(iter(mapping)): SimpleNamespace(offset=0)}

        async def end_offsets(self, partitions: list[Any]) -> dict[Any, int]:
            return {partitions[0]: 10}

        async def beginning_offsets(self, partitions: list[Any]) -> dict[Any, int]:
            return {partitions[0]: 0}

        async def seek(self, partition: Any, offset: int) -> None:
            self.seeked = (partition, offset)

        async def getmany(self, *, timeout_ms: int, max_records: int) -> dict[Any, list[Any]]:
            del timeout_ms, max_records
            if getattr(self, "sent", False):
                return {}
            self.sent = True
            record = SimpleNamespace(
                topic="topic",
                partition=0,
                offset=3,
                timestamp=int(NOW.timestamp() * 1000),
                value=json.dumps({"event_type": "evt", "subject": "sub"}).encode(),
                key=b"key",
            )
            return {object(): [record]}

    replay = KafkaTimelineReplay(settings=_settings(), consumer_factory=FakeConsumer)  # type: ignore[arg-type]
    kafka_entries = await replay.read_window(["topic"], NOW, NOW + timedelta(minutes=1))
    assert kafka_entries[0].summary == "evt sub"
    with pytest.raises(ValueError, match="timeline Kafka replay window exceeds configured cap"):
        await replay.read_window(["topic"], NOW, NOW + timedelta(days=2))


@pytest.mark.asyncio
async def test_provider_clients_events_trigger_and_facade_paths() -> None:
    assert _redact_headers({"Authorization": "secret", "Other": "ok"}) == {
        "Authorization": "<redacted>",
        "Other": "ok",
    }
    assert _normalize_priority("critical") == "P1"
    assert _normalize_priority("p5") == "P5"
    assert _normalize_priority("unknown") == "P3"
    assert _split_secret("routing:name") == ("routing", "name")
    assert _split_secret("routing") == ("routing", "musematic")
    assert _normalize_message_type("P2") == "CRITICAL"
    assert _normalize_message_type("P4") == "WARNING"
    assert _normalize_message_type("other") == "INFO"
    assert _to_unix(NOW) == int(NOW.timestamp())

    class Response:
        def __init__(self, status_code: int, payload: Any) -> None:
            self.status_code = status_code
            self.payload = payload

        def json(self) -> Any:
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload

    class Client:
        def __init__(self, response: Response | Exception) -> None:
            self.response = response
            self.posts: list[dict[str, Any]] = []

        async def post(self, url: str, **kwargs: Any) -> Response:
            self.posts.append({"url": url, **kwargs})
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    class TestProvider(BaseHttpPagingProvider):
        provider = "test"
        base_url = "https://example.test"

    provider = TestProvider(
        secret_provider=SecretProvider(),  # type: ignore[arg-type]
        timeout_seconds=1,
        client=Client(Response(200, {"ok": True})),  # type: ignore[arg-type]
    )
    assert await provider._post("https://example.test", json={}) == {"ok": True}
    with pytest.raises(ProviderError, match="Plain-text"):
        await provider._post("http://example.test", json={})
    assert (
        await TestProvider(
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
            timeout_seconds=1,
            client=Client(Response(200, ValueError("bad json"))),  # type: ignore[arg-type]
        )._post("https://example.test", json={})
        == {}
    )
    assert (
        await TestProvider(
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
            timeout_seconds=1,
            client=Client(Response(200, [])),  # type: ignore[arg-type]
        )._post("https://example.test", json={})
        == {}
    )
    with pytest.raises(ProviderError) as status_error:
        await TestProvider(
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
            timeout_seconds=1,
            client=Client(Response(500, {})),  # type: ignore[arg-type]
        )._post("https://example.test", json={})
    assert status_error.value.retryable is True
    with pytest.raises(ProviderError) as timeout_error:
        await TestProvider(
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
            timeout_seconds=1,
            client=Client(httpx.TimeoutException("timeout")),  # type: ignore[arg-type]
        )._post("https://example.test", json={})
    assert timeout_error.value.retryable is True
    with pytest.raises(ProviderError):
        await TestProvider(
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
            timeout_seconds=1,
            client=Client(httpx.HTTPError("http")),  # type: ignore[arg-type]
        )._post("https://example.test", json={})

    integration = _integration()
    incident = _incident(status="open")
    pagerduty = PagerDutyClient(
        secret_provider=SecretProvider(value="routing"),  # type: ignore[arg-type]
        timeout_seconds=1,
        client=Client(Response(200, {"dedup_key": "dedup"})),  # type: ignore[arg-type]
    )
    assert (
        await pagerduty.create_alert(
            integration=integration,
            incident=incident,
            mapped_severity="critical",
        )
    ).provider_reference == "dedup"
    await pagerduty.resolve_alert(integration=integration, provider_reference="dedup")

    opsgenie = OpsGenieClient(
        secret_provider=SecretProvider(value="genie"),  # type: ignore[arg-type]
        timeout_seconds=1,
        client=Client(Response(200, {"requestId": "req"})),  # type: ignore[arg-type]
    )
    assert (
        await opsgenie.create_alert(
            integration=integration,
            incident=incident,
            mapped_severity="high",
        )
    ).provider_reference == "req"
    await opsgenie.resolve_alert(integration=integration, provider_reference="alias/1")

    victorops = VictorOpsClient(
        secret_provider=SecretProvider(value="route:name"),  # type: ignore[arg-type]
        timeout_seconds=1,
        client=Client(Response(200, {"entity_id": "entity"})),  # type: ignore[arg-type]
    )
    assert (
        await victorops.create_alert(
            integration=integration,
            incident=incident,
            mapped_severity="P1",
        )
    ).provider_reference == "entity"
    await victorops.resolve_alert(integration=integration, provider_reference="entity")

    producer = ProducerRecorder()
    ctx = CorrelationContext(correlation_id=uuid4())
    payload = IncidentTriggeredPayload(
        incident_id=incident.id,
        condition_fingerprint=incident.condition_fingerprint,
        severity=incident.severity,
        alert_rule_class=incident.alert_rule_class,
        related_execution_ids=incident.related_executions,
        runbook_scenario=incident.runbook_scenario,
        triggered_at=incident.triggered_at,
        correlation_context=ctx,
    )
    await publish_incident_response_event(
        producer,  # type: ignore[arg-type]
        "custom.event",
        payload,
        ctx,
    )
    await publish_incident_triggered(producer, payload, ctx)  # type: ignore[arg-type]
    await publish_incident_resolved(
        producer,  # type: ignore[arg-type]
        IncidentResolvedPayload(
            incident_id=incident.id,
            condition_fingerprint=incident.condition_fingerprint,
            severity=incident.severity,
            status="resolved",
            resolved_at=NOW,
            correlation_context=ctx,
        ),
        ctx,
    )
    await publish_incident_response_event(
        None, IncidentResponseEventType.incident_triggered, payload, ctx
    )
    register_incident_response_event_types()
    assert producer.events[0]["key"] == str(incident.id)

    noop = NoopIncidentTrigger()
    assert (
        await noop.fire(
            IncidentSignal(
                alert_rule_class="rule",
                severity="info",
                title="t",
                description="d",
                condition_fingerprint="f",
            )
        )
    ).no_external_page_attempted is True

    class SignalService:
        async def create_from_signal(self, signal: IncidentSignal) -> Any:
            del signal
            return SimpleNamespace(incident_id=incident.id)

    assert (
        await ServiceIncidentTrigger(SignalService()).fire(
            IncidentSignal(
                alert_rule_class="rule",
                severity="info",
                title="t",
                description="d",
                condition_fingerprint="f",
            )
        )
    ).incident_id == incident.id
    register_incident_trigger(noop)
    assert get_incident_trigger() is noop
    reset_incident_trigger()

    post_mortems = SimpleNamespace(
        find_for_execution=lambda execution_id: _async([SimpleNamespace(id=execution_id)]),
        find_for_certification=lambda certification_id: _async(
            [SimpleNamespace(id=certification_id)]
        ),
    )
    facade = IncidentResponseService(
        incident_service=SimpleNamespace(),  # type: ignore[arg-type]
        integration_service=SimpleNamespace(),  # type: ignore[arg-type]
        runbook_service=SimpleNamespace(),  # type: ignore[arg-type]
        post_mortem_service=post_mortems,  # type: ignore[arg-type]
        timeline_assembler=SimpleNamespace(),  # type: ignore[arg-type]
    )
    await facade.handle_workspace_archived(uuid4())
    assert (await facade.find_post_mortems_for_execution(uuid4()))[0].id
    assert (await facade.find_post_mortems_for_certification(uuid4()))[0].id
    assert IntegrationProviderUnreachableError("pagerduty", "down").status_code == 503


@pytest.mark.asyncio
async def test_dependency_factories_jobs_runtime_and_background_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from platform.incident_response import dependencies, runtime
    from platform.incident_response.jobs import delivery_retry_scanner, runbook_freshness_scanner

    settings = _settings(delivery_retry_scan_interval_seconds=7)
    redis = RedisRecorder()
    kafka = ProducerRecorder()
    object_storage = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "redis": redis,
                    "kafka": kafka,
                    "object_storage": object_storage,
                },
            )
        )
    )
    session = object()
    audit = AuditRecorder()
    secret_provider = dependencies.get_secret_provider(request)

    assert dependencies._get_settings(request) is settings
    assert dependencies._get_producer(request) is kafka
    assert dependencies._get_redis(request) is redis
    assert dependencies._get_object_storage(request) is object_storage
    assert dependencies.get_secret_provider(request) is secret_provider
    assert set(dependencies.get_paging_provider_clients(request, secret_provider)) == {
        "pagerduty",
        "opsgenie",
        "victorops",
    }
    assert (
        dependencies.build_runbook_service(
            session=session,  # type: ignore[arg-type]
            settings=settings,
            audit_chain_service=audit,
        ).settings
        is settings
    )
    assert (
        dependencies.build_integration_service(
            session=session,  # type: ignore[arg-type]
            secret_provider=secret_provider,
            audit_chain_service=audit,
        ).secret_provider
        is secret_provider
    )
    runbook_service = dependencies.build_runbook_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
    )
    incident_service = dependencies.build_incident_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        redis_client=redis,  # type: ignore[arg-type]
        producer=kafka,  # type: ignore[arg-type]
        provider_clients={},
        runbook_service=runbook_service,
        audit_chain_service=audit,
    )
    assert incident_service.settings is settings
    timeline = dependencies.build_timeline_assembler(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        audit_chain_service=audit,
        execution_service=object(),
    )
    assert timeline.kafka_topics == settings.incident_response.timeline_kafka_topics
    post_mortems = dependencies.build_post_mortem_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        timeline_assembler=timeline,
        object_storage=object_storage,  # type: ignore[arg-type]
        alert_service=object(),
        audit_chain_service=audit,
    )
    assert post_mortems.settings is settings
    assert await dependencies.get_runbook_service(
        request,
        session=session,  # type: ignore[arg-type]
        audit_chain_service=audit,  # type: ignore[arg-type]
    )
    assert await dependencies.get_integration_service(
        request,
        session=session,  # type: ignore[arg-type]
        secret_provider=secret_provider,
        audit_chain_service=audit,  # type: ignore[arg-type]
    )
    assert await dependencies.get_incident_service(
        request,
        session=session,  # type: ignore[arg-type]
        provider_clients={},
        runbook_service=runbook_service,
        audit_chain_service=audit,  # type: ignore[arg-type]
    )
    assert await dependencies.get_timeline_assembler(
        request,
        session=session,  # type: ignore[arg-type]
        audit_chain_service=audit,  # type: ignore[arg-type]
        execution_service=object(),  # type: ignore[arg-type]
    )
    assert await dependencies.get_post_mortem_service(
        request,
        session=session,  # type: ignore[arg-type]
        timeline_assembler=timeline,
        audit_chain_service=audit,  # type: ignore[arg-type]
        alert_service=object(),  # type: ignore[arg-type]
    )
    assert await dependencies.get_incident_response_service(
        incident_service=incident_service,
        integration_service=SimpleNamespace(),  # type: ignore[arg-type]
        runbook_service=runbook_service,
        post_mortem_service=post_mortems,
        timeline_assembler=timeline,
    )

    service = IncidentService(
        repository=MemoryRepository(),  # type: ignore[arg-type]
        settings=settings,
        redis_client=None,
        producer=None,
        provider_clients={},
    )

    async def ok() -> None:
        return None

    async def boom() -> None:
        raise RuntimeError("background failed")

    service._schedule_background(ok())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not service._background_tasks
    service._schedule_background(boom())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not service._background_tasks
    task = asyncio.create_task(asyncio.sleep(1))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    service._background_task_done(task)  # type: ignore[arg-type]
    assert await service._redis_get("x") is None
    await service._redis_set("x", b"y", 1)
    await service._redis_delete("x")

    class SessionContext:
        def __init__(self) -> None:
            self.session = SimpleNamespace(committed=False)

        async def __aenter__(self) -> Any:
            async def commit() -> None:
                self.session.committed = True

            self.session.commit = commit
            return self.session

        async def __aexit__(self, *args: Any) -> None:
            return None

    class RetryRepository:
        def __init__(self, session_arg: Any) -> None:
            self.session = session_arg
            self.alerts = [
                SimpleNamespace(id=uuid4(), attempt_count=99, last_error=None),
                SimpleNamespace(id=uuid4(), attempt_count=0, last_error="retry"),
            ]
            retry_repositories.append(self)

        async def list_pending_retries(self, now: datetime) -> list[Any]:
            assert now.tzinfo is not None
            return self.alerts

        async def update_external_alert_status(self, *args: Any, **kwargs: Any) -> None:
            retry_updates.append((args, kwargs))

    retry_repositories: list[RetryRepository] = []
    retry_updates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    dispatched: list[UUID] = []

    monkeypatch.setattr(delivery_retry_scanner.database, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(
        delivery_retry_scanner,
        "build_audit_chain_service",
        lambda **kwargs: audit,
    )
    monkeypatch.setattr(
        delivery_retry_scanner,
        "build_runbook_service",
        lambda **kwargs: runbook_service,
    )

    class RetryService:
        async def _dispatch_external_alert(self, alert_id: UUID) -> None:
            dispatched.append(alert_id)

    monkeypatch.setattr(
        delivery_retry_scanner,
        "build_incident_service",
        lambda **kwargs: RetryService(),
    )
    monkeypatch.setattr(delivery_retry_scanner, "IncidentResponseRepository", RetryRepository)

    app = SimpleNamespace(
        state=SimpleNamespace(settings=settings, clients={"redis": redis, "kafka": kafka})
    )
    assert await delivery_retry_scanner.run_delivery_retry_scan(app) == 2
    assert retry_updates[0][1]["status"] == "failed"
    assert dispatched == [retry_repositories[0].alerts[1].id]

    class Scheduler:
        def __init__(self, *, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

        def add_job(self, func: Any, *args: Any, **kwargs: Any) -> None:
            self.jobs.append((func, args, kwargs))

    original_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            return SimpleNamespace(AsyncIOScheduler=Scheduler)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    retry_scheduler = delivery_retry_scanner.build_delivery_retry_scheduler(app)
    assert retry_scheduler.jobs[0][2]["seconds"] == 7
    freshness_scheduler = runbook_freshness_scanner.build_runbook_freshness_scheduler(app)
    assert freshness_scheduler.jobs[0][2]["days"] == 1

    def failing_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", failing_import)
    assert delivery_retry_scanner.build_delivery_retry_scheduler(app) is None
    assert runbook_freshness_scanner.build_runbook_freshness_scheduler(app) is None

    class FreshnessRepository:
        def __init__(self, session_arg: Any) -> None:
            self.session = session_arg

        async def mark_runbooks_stale(self, threshold: datetime) -> list[Runbook]:
            assert threshold.tzinfo is not None
            return [_runbook(updated_at=threshold - timedelta(days=1))]

    monkeypatch.setattr(runbook_freshness_scanner.database, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(
        runbook_freshness_scanner, "IncidentResponseRepository", FreshnessRepository
    )
    assert await runbook_freshness_scanner.run_runbook_freshness_scan(app) == 1

    class RuntimeIncidentService:
        async def create_from_signal(self, signal: IncidentSignal) -> Any:
            return SimpleNamespace(
                incident_id=uuid4(),
                deduplicated=False,
                external_pages_attempted=len(signal.related_event_ids),
                no_external_page_attempted=False,
            )

    monkeypatch.setattr(runtime.database, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(runtime, "build_audit_chain_service", lambda **kwargs: audit)
    monkeypatch.setattr(runtime, "build_runbook_service", lambda **kwargs: runbook_service)
    monkeypatch.setattr(
        runtime,
        "build_incident_service",
        lambda **kwargs: RuntimeIncidentService(),
    )
    runtime_app = SimpleNamespace(
        state=SimpleNamespace(settings=settings, clients={"redis": redis, "kafka": kafka})
    )
    runtime_ref = await runtime.AppIncidentTrigger(runtime_app).fire(
        IncidentSignal(
            alert_rule_class="rule",
            severity="info",
            title="Runtime",
            description="Runtime signal",
            condition_fingerprint="runtime",
            related_event_ids=[uuid4()],
        )
    )
    assert runtime_ref.external_pages_attempted == 1


@pytest.mark.asyncio
async def test_remaining_incident_response_edge_branches() -> None:
    from platform.incident_response.schemas import IntegrationCreateRequest

    repo = MemoryRepository()
    settings = _settings(delivery_retry_initial_seconds=1, delivery_retry_max_attempts=3)
    integration = _integration(mapping={})
    repo.integrations[integration.id] = integration
    incident = _incident(status="open", scenario="missing_scenario")
    repo.incidents[incident.id] = incident
    service = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        redis_client=None,
        producer=None,
        provider_clients={
            "pagerduty": ProviderClient(resolve_error=RuntimeError("resolve failed"))
        },
    )

    alert_missing_incident = _alert(uuid4(), integration.id)
    repo.alerts[alert_missing_incident.id] = alert_missing_incident
    with pytest.raises(IncidentNotFoundError):
        await service._dispatch_external_alert(alert_missing_incident.id)

    service.provider_clients["pagerduty"] = ProviderClient(error=RuntimeError("provider boom"))
    alert = _alert(incident.id, integration.id)
    repo.alerts[alert.id] = alert
    await service._dispatch_external_alert(alert.id)
    assert alert.delivery_status == "pending"
    assert alert.last_error == "provider boom"
    assert service._mapped_severity(integration, "unknown") == "warning"

    delivered = _alert(
        incident.id,
        integration.id,
        status="delivered",
        provider_reference="ref",
    )
    repo.alerts[delivered.id] = delivered
    await service._resolve_external_alert(uuid4())
    no_ref = _alert(incident.id, integration.id, status="delivered", provider_reference=None)
    repo.alerts[no_ref.id] = no_ref
    await service._resolve_external_alert(no_ref.id)
    no_integration = _alert(incident.id, uuid4(), status="delivered", provider_reference="ref")
    repo.alerts[no_integration.id] = no_integration
    await service._resolve_external_alert(no_integration.id)
    service.provider_clients.clear()
    await service._resolve_external_alert(delivered.id)
    service.provider_clients["pagerduty"] = ProviderClient(resolve_error=RuntimeError("down"))
    await service._resolve_external_alert(delivered.id)
    assert delivered.last_error == "down"

    incident.status = "resolved"
    assert (await service.auto_resolve_if_provider_resolved(incident.id)).status == "auto_resolved"
    with pytest.raises(IncidentNotFoundError):
        await service.get(uuid4())
    assert (await service.get(incident.id)).runbook is None

    runbook_service = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
    )
    service.runbook_service = runbook_service
    missing_runbook = await service.get(incident.id)
    assert (
        missing_runbook.runbook_authoring_link == "/operator/runbooks/new?scenario=missing_scenario"
    )

    with pytest.raises(ValueError, match="incident-response Vault path"):
        IntegrationCreateRequest(
            provider="pagerduty",
            integration_key_ref="wrong/path",
        )

    integrations = IntegrationService(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=SecretProvider(),  # type: ignore[arg-type]
    )
    missing_id = uuid4()
    for call in (
        integrations.enable,
        integrations.disable,
    ):
        with pytest.raises(IntegrationNotFoundError):
            await call(missing_id)
    with pytest.raises(IntegrationNotFoundError):
        await integrations.update_severity_mapping(missing_id, {})
    with pytest.raises(IntegrationNotFoundError):
        await integrations.update(missing_id, enabled=True)
    await integrations._audit("noop", integration=integration)

    class NoAppendAudit:
        pass

    await IntegrationService(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=SecretProvider(),  # type: ignore[arg-type]
        audit_chain_service=NoAppendAudit(),
    )._audit("noop", integration=integration)

    class DeleteFalseRepository(MemoryRepository):
        async def delete_integration(self, integration_id: UUID) -> bool:
            del integration_id
            return False

    delete_repo = DeleteFalseRepository()
    delete_repo.integrations[integration.id] = integration
    with pytest.raises(IntegrationNotFoundError):
        await IntegrationService(
            repository=delete_repo,  # type: ignore[arg-type]
            secret_provider=SecretProvider(),  # type: ignore[arg-type]
        ).delete(integration.id)

    class NoPartitionConsumer:
        def __init__(self, *topics: str, **kwargs: Any) -> None:
            del topics, kwargs

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def partitions_for_topic(self, topic: str) -> set[int]:
            del topic
            return set()

    assert (
        await KafkaTimelineReplay(
            settings=settings,
            consumer_factory=NoPartitionConsumer,  # type: ignore[arg-type]
        ).read_window(["empty"], NOW, NOW + timedelta(minutes=1))
        == []
    )

    class OffsetConsumer(NoPartitionConsumer):
        def __init__(self, *topics: str, **kwargs: Any) -> None:
            super().__init__(*topics, **kwargs)
            self.calls = 0

        def partitions_for_topic(self, topic: str) -> set[int]:
            del topic
            return {0}

        async def offsets_for_times(self, mapping: dict[Any, int]) -> dict[Any, Any]:
            partition = next(iter(mapping))
            return {partition: None}

        async def end_offsets(self, partitions: list[Any]) -> dict[Any, int]:
            return {partitions[0]: 5}

        async def seek(self, partition: Any, offset: int) -> None:
            self.seeked = (partition, offset)

        async def getmany(self, *, timeout_ms: int, max_records: int) -> dict[Any, list[Any]]:
            del timeout_ms, max_records
            return {}

    replay = KafkaTimelineReplay(
        settings=settings,
        consumer_factory=OffsetConsumer,  # type: ignore[arg-type]
    )
    assert await replay.read_window(["topic"], NOW, NOW + timedelta(minutes=1)) == []
    assert replay.last_window_partial is True

    class LateRecordConsumer(OffsetConsumer):
        async def offsets_for_times(self, mapping: dict[Any, int]) -> dict[Any, Any]:
            return {next(iter(mapping)): SimpleNamespace(offset=1)}

        async def beginning_offsets(self, partitions: list[Any]) -> dict[Any, int]:
            return {partitions[0]: 1}

        async def getmany(self, *, timeout_ms: int, max_records: int) -> dict[Any, list[Any]]:
            del timeout_ms, max_records
            if self.calls:
                return {}
            self.calls += 1
            return {
                object(): [
                    SimpleNamespace(
                        topic="topic",
                        partition=0,
                        offset=1,
                        timestamp=int((NOW + timedelta(hours=1)).timestamp() * 1000),
                        value=b"{}",
                        key=None,
                    )
                ]
            }

    late_replay = KafkaTimelineReplay(
        settings=settings,
        consumer_factory=LateRecordConsumer,  # type: ignore[arg-type]
    )
    assert await late_replay.read_window(["topic"], NOW, NOW + timedelta(minutes=1)) == []
    assert late_replay.last_window_partial is True

    class FailingStorage:
        async def create_bucket_if_not_exists(self, bucket: str) -> None:
            del bucket
            raise RuntimeError("storage down")

    post_mortem = _post_mortem(incident.id, timeline=None)
    repo.post_mortems[post_mortem.id] = post_mortem
    post_service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=_settings(postmortem_blob_threshold_bytes=10_000),
        timeline_assembler=SimpleNamespace(),  # type: ignore[arg-type]
        object_storage=None,
        audit_chain_service=None,
    )
    assert (await post_service._maybe_spill_timeline(uuid4(), [{"small": True}]))[1] is None
    assert await post_service._load_timeline(post_mortem) is None
    await post_service._notify_recipient(post_mortem, "none@example.com")
    await post_service._audit("noop", post_mortem)

    failing_spill = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=_settings(postmortem_blob_threshold_bytes=1),
        timeline_assembler=SimpleNamespace(),  # type: ignore[arg-type]
        object_storage=FailingStorage(),  # type: ignore[arg-type]
    )
    inline, blob = await failing_spill._maybe_spill_timeline(uuid4(), [{"large": "x" * 100}])
    assert inline is not None
    assert blob is None


@pytest.mark.asyncio
async def test_repository_methods_cover_crud_and_query_branches() -> None:
    class Scalars:
        def __init__(self, rows: list[Any]) -> None:
            self.rows = rows

        def all(self) -> list[Any]:
            return self.rows

    class Result:
        def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
            self.rows = [] if rows is None else rows
            self.scalar = scalar

        def scalars(self) -> Scalars:
            return Scalars(self.rows)

        def scalar_one_or_none(self) -> Any:
            return self.scalar

    class Session:
        def __init__(self) -> None:
            self.objects: dict[tuple[type[Any], UUID], Any] = {}
            self.results: list[Result] = []
            self.added: list[Any] = []
            self.deleted: list[Any] = []
            self.flushes = 0

        def add(self, item: Any) -> None:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if isinstance(item, IncidentExternalAlert) and item.attempt_count is None:
                item.attempt_count = 0
            self.added.append(item)
            self.objects[(type(item), item.id)] = item

        async def flush(self) -> None:
            self.flushes += 1

        async def get(self, model: type[Any], object_id: UUID) -> Any:
            return self.objects.get((model, object_id))

        async def delete(self, item: Any) -> None:
            self.deleted.append(item)
            self.objects.pop((type(item), item.id), None)

        async def execute(self, statement: Any) -> Result:
            del statement
            return self.results.pop(0) if self.results else Result()

    session = Session()
    repository = IncidentResponseRepository(session)  # type: ignore[arg-type]
    integration = await repository.insert_integration(
        provider="pagerduty",
        integration_key_ref="incident-response/integrations/key",
        alert_severity_mapping={"high": "P2"},
    )
    assert await repository.get_integration(integration.id) is integration
    session.results.append(Result(rows=[integration]))
    assert await repository.list_integrations(enabled_only=True) == [integration]
    assert (await repository.update_integration(integration.id, enabled=False)).enabled is False
    assert await repository.update_integration(uuid4(), enabled=True) is None
    assert await repository.delete_integration(integration.id) is True
    assert await repository.delete_integration(uuid4()) is False

    incident = await repository.insert_incident(
        condition_fingerprint="fingerprint",
        severity="high",
        title="title",
        description="description",
        related_execution_ids=[uuid4()],
        related_event_ids=[uuid4()],
        runbook_scenario="pod_failure",
        alert_rule_class="error_rate_spike",
    )
    assert await repository.get_incident(incident.id) is incident
    session.results.append(Result(scalar=incident))
    assert await repository.find_open_incident_by_fingerprint("fingerprint") is incident
    session.results.append(Result(scalar=incident))
    assert await repository.append_recurrence(incident.id, uuid4()) is incident
    assert await repository.append_recurrence(incident.id, None) is incident
    session.results.append(Result(scalar=None))
    assert await repository.append_incident_execution(incident.id, uuid4()) is incident
    session.results.append(Result(rows=[incident]))
    assert await repository.list_incidents(
        status="open",
        severity="high",
        since=NOW - timedelta(days=1),
        until=NOW + timedelta(days=1),
        cursor=NOW + timedelta(days=1),
        limit=10,
    ) == [incident]
    assert await repository.resolve_incident(uuid4(), NOW) is None
    assert (await repository.resolve_incident(incident.id, NOW)).status == "resolved"
    await repository.update_incident_post_mortem(incident.id, uuid4())

    integration = _integration()
    session.objects[(IncidentIntegration, integration.id)] = integration
    alert = await repository.insert_external_alert(
        incident_id=incident.id, integration_id=integration.id
    )
    assert await repository.get_external_alert(alert.id) is alert
    session.results.append(Result(rows=[alert]))
    assert await repository.list_external_alerts_for_incident(incident.id) == [alert]
    assert await repository.update_external_alert_status(uuid4(), status="failed") is None
    assert (
        await repository.update_external_alert_status(
            alert.id,
            status="delivered",
            provider_reference="ref",
            error=None,
            next_retry_at=None,
            increment_attempt=True,
        )
    ).attempt_count == 1
    session.results.append(Result(rows=[alert]))
    assert await repository.list_pending_retries(NOW) == [alert]

    runbook = await repository.insert_runbook(
        scenario="pod_failure",
        title="Pod failure",
        symptoms="symptoms",
        diagnostic_commands=[{"command": "cmd", "description": "desc"}],
        remediation_steps="steps",
        escalation_path="path",
        status="active",
        updated_by=None,
    )
    assert await repository.get_runbook(runbook.id) is runbook
    session.results.append(Result(scalar=runbook))
    assert await repository.get_runbook_by_scenario("pod_failure") is runbook
    session.results.append(Result(scalar=runbook))
    assert await repository.get_runbook_by_scenario("pod_failure", active_only=False) is runbook
    session.results.append(Result(rows=[runbook]))
    assert await repository.list_runbooks(
        status="active",
        scenario_query="pod",
        cursor=NOW + timedelta(days=1),
        limit=10,
    ) == [runbook]
    session.results.append(Result(scalar=runbook))
    assert (
        await repository.update_runbook(
            runbook.id,
            expected_version=1,
            updated_by=uuid4(),
            fields={"title": "Updated"},
        )
        is runbook
    )
    session.results.append(Result(scalar=None))
    with pytest.raises(RunbookConcurrentEditError):
        await repository.update_runbook(
            uuid4(),
            expected_version=1,
            updated_by=None,
            fields={},
        )
    session.results.append(Result(rows=[runbook]))
    assert await repository.mark_runbooks_stale(NOW) == [runbook]

    post_mortem = await repository.insert_post_mortem(
        incident_id=incident.id,
        timeline=[],
        timeline_blob_ref=None,
        timeline_source_coverage=TimelineSourceCoverage().model_dump(mode="json"),
        created_by=None,
    )
    assert await repository.get_post_mortem(post_mortem.id) is post_mortem
    session.results.append(Result(scalar=post_mortem))
    assert await repository.get_post_mortem_by_incident(incident.id) is post_mortem
    assert await repository.update_post_mortem_section(uuid4(), root_cause="missing") is None
    assert (
        await repository.update_post_mortem_section(
            post_mortem.id,
            root_cause="root",
            impact_assessment=None,
        )
    ).root_cause == "root"
    session.results.append(Result(rows=[post_mortem]))
    assert await repository.list_post_mortems_by_execution(uuid4()) == [post_mortem]
    session.results.append(Result(rows=[post_mortem]))
    assert await repository.list_post_mortems_by_certification(uuid4()) == [post_mortem]
    session.results.append(Result(scalar=post_mortem))
    assert await repository.append_linked_certification(post_mortem.id, uuid4()) is post_mortem
    session.results.append(Result(scalar=None))
    assert await repository.append_linked_certification(post_mortem.id, uuid4()) is post_mortem
    assert await repository.mark_published(uuid4(), NOW) is None
    assert (await repository.mark_published(post_mortem.id, NOW)).status == "published"
    assert await repository.mark_distributed(uuid4(), [], NOW) is None
    assert (
        await repository.mark_distributed(post_mortem.id, [{"recipient": "a"}], NOW)
    ).status == "distributed"


def test_runbook_seed_statement_uses_jsonb_and_idempotent_insert() -> None:
    table = _runbooks_table()
    assert table.c.diagnostic_commands.type.__class__.__name__ == "JSONB"
    assert "pod_failure" in RUNBOOK_SCENARIOS
    assert RUNBOOKS_V1[0]["diagnostic_commands"]

    class Connection:
        def __init__(self) -> None:
            self.statement: Any | None = None

        def execute(self, statement: Any) -> None:
            self.statement = statement

    connection = Connection()
    seed_initial_runbooks(connection)
    assert connection.statement is not None
    assert "ON CONFLICT" in str(connection.statement.compile(dialect=postgresql.dialect()))


async def _async(value: Any) -> Any:
    return value
