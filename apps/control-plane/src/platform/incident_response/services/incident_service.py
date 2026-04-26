from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.incident_response.events import (
    IncidentResolvedPayload,
    IncidentTriggeredPayload,
    publish_incident_resolved,
    publish_incident_triggered,
)
from platform.incident_response.exceptions import (
    ExternalAlertNotFoundError,
    IncidentNotFoundError,
    IntegrationNotFoundError,
)
from platform.incident_response.models import Incident, IncidentExternalAlert, IncidentIntegration
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import (
    ExternalAlertResponse,
    IncidentDetailResponse,
    IncidentListItem,
    IncidentRef,
    IncidentResponse,
    IncidentSignal,
)
from platform.incident_response.services.providers.base import (
    PagingProviderClient,
    ProviderError,
)
from platform.incident_response.services.runbook_service import RunbookService
from typing import Any
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)


class IncidentService:
    def __init__(
        self,
        *,
        repository: IncidentResponseRepository,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None,
        producer: EventProducer | None,
        provider_clients: dict[str, PagingProviderClient],
        runbook_service: RunbookService | None = None,
        audit_chain_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer
        self.provider_clients = provider_clients
        self.runbook_service = runbook_service
        self.audit_chain_service = audit_chain_service
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _schedule_background(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_task_done)

    def _background_task_done(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("incident_response_background_task_failed")

    async def create_from_signal(self, signal: IncidentSignal) -> IncidentRef:
        correlation_ctx = signal.correlation_context or CorrelationContext(correlation_id=uuid4())
        dedup_key = self._dedup_key(signal.condition_fingerprint)
        existing_hint = await self._redis_get(dedup_key)
        if existing_hint is not None:
            existing = await self.repository.find_open_incident_by_fingerprint(
                signal.condition_fingerprint
            )
            if existing is not None:
                for event_id in signal.related_event_ids:
                    await self.repository.append_recurrence(existing.id, event_id)
                return IncidentRef(
                    incident_id=existing.id,
                    deduplicated=True,
                    no_external_page_attempted=True,
                )

        existing = await self.repository.find_open_incident_by_fingerprint(
            signal.condition_fingerprint
        )
        if existing is not None:
            for event_id in signal.related_event_ids:
                await self.repository.append_recurrence(existing.id, event_id)
            await self._redis_set(
                dedup_key,
                str(existing.id).encode(),
                self.settings.incident_response.dedup_fingerprint_ttl_seconds,
            )
            return IncidentRef(
                incident_id=existing.id,
                deduplicated=True,
                no_external_page_attempted=True,
            )

        scenario = signal.runbook_scenario
        if scenario is None and self.runbook_service is not None:
            scenario = self.runbook_service.lookup_by_alert_rule_class(signal.alert_rule_class)
        incident = await self.repository.insert_incident(
            condition_fingerprint=signal.condition_fingerprint,
            severity=signal.severity.value,
            title=signal.title,
            description=signal.description,
            related_execution_ids=signal.related_execution_ids,
            related_event_ids=signal.related_event_ids,
            runbook_scenario=scenario,
            alert_rule_class=signal.alert_rule_class,
        )
        integrations = await self.repository.list_integrations(enabled_only=True)
        alerts: list[IncidentExternalAlert] = []
        for integration in integrations:
            alert = await self.repository.insert_external_alert(
                incident_id=incident.id,
                integration_id=integration.id,
            )
            alerts.append(alert)
        await self._redis_set(
            dedup_key,
            str(incident.id).encode(),
            self.settings.incident_response.dedup_fingerprint_ttl_seconds,
        )
        await publish_incident_triggered(
            self.producer,
            IncidentTriggeredPayload(
                incident_id=incident.id,
                condition_fingerprint=incident.condition_fingerprint,
                severity=incident.severity,
                alert_rule_class=incident.alert_rule_class,
                related_execution_ids=incident.related_executions,
                runbook_scenario=incident.runbook_scenario,
                triggered_at=incident.triggered_at,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
        )
        for alert in alerts:
            self._schedule_background(self._dispatch_external_alert(alert.id))
        return IncidentRef(
            incident_id=incident.id,
            external_pages_attempted=len(alerts),
            no_external_page_attempted=not alerts,
        )

    async def _dispatch_external_alert(self, external_alert_id: UUID) -> None:
        alert = await self.repository.get_external_alert(external_alert_id)
        if alert is None:
            raise ExternalAlertNotFoundError(external_alert_id)
        integration = await self.repository.get_integration(alert.integration_id)
        if integration is None:
            raise IntegrationNotFoundError(alert.integration_id)
        incident = await self.repository.get_incident(alert.incident_id)
        if incident is None:
            raise IncidentNotFoundError(alert.incident_id)
        provider = self.provider_clients.get(integration.provider)
        if provider is None:
            await self._record_delivery_failure(
                alert,
                error=f"No provider client for {integration.provider}",
                retryable=False,
            )
            return
        mapped_severity = self._mapped_severity(integration, incident.severity)
        try:
            ref = await provider.create_alert(
                integration=integration,
                incident=incident,
                mapped_severity=mapped_severity,
            )
        except ProviderError as exc:
            await self._record_delivery_failure(alert, error=str(exc), retryable=exc.retryable)
            return
        except Exception as exc:
            await self._record_delivery_failure(alert, error=str(exc), retryable=True)
            return
        await self.repository.update_external_alert_status(
            alert.id,
            status="delivered",
            provider_reference=ref.provider_reference,
            error=None,
            next_retry_at=None,
            increment_attempt=True,
        )

    async def resolve(
        self,
        incident_id: UUID,
        *,
        resolved_at: datetime | None = None,
        auto_resolved: bool = False,
    ) -> IncidentResponse:
        resolved = resolved_at or datetime.now(UTC)
        status = "auto_resolved" if auto_resolved else "resolved"
        incident = await self.repository.resolve_incident(incident_id, resolved, status=status)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        correlation_ctx = CorrelationContext(correlation_id=uuid4())
        await publish_incident_resolved(
            self.producer,
            IncidentResolvedPayload(
                incident_id=incident.id,
                condition_fingerprint=incident.condition_fingerprint,
                severity=incident.severity,
                status=incident.status,
                resolved_at=resolved,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
        )
        alerts = await self.repository.list_external_alerts_for_incident(incident.id)
        for alert in alerts:
            if alert.delivery_status == "delivered" and alert.provider_reference:
                self._schedule_background(self._resolve_external_alert(alert.id))
        await self._redis_delete(self._dedup_key(incident.condition_fingerprint))
        return IncidentResponse.model_validate(incident)

    async def auto_resolve_if_provider_resolved(self, incident_id: UUID) -> IncidentResponse:
        return await self.resolve(incident_id, auto_resolved=True)

    async def _resolve_external_alert(self, external_alert_id: UUID) -> None:
        alert = await self.repository.get_external_alert(external_alert_id)
        if alert is None or not alert.provider_reference:
            return
        integration = await self.repository.get_integration(alert.integration_id)
        if integration is None:
            return
        provider = self.provider_clients.get(integration.provider)
        if provider is None:
            return
        try:
            await provider.resolve_alert(
                integration=integration,
                provider_reference=alert.provider_reference,
            )
        except Exception as exc:
            await self.repository.update_external_alert_status(
                alert.id,
                status=alert.delivery_status,
                error=str(exc),
                next_retry_at=None,
                increment_attempt=True,
            )
            return
        await self.repository.update_external_alert_status(
            alert.id,
            status="resolved",
            provider_reference=alert.provider_reference,
            error=None,
            next_retry_at=None,
            increment_attempt=True,
        )

    async def get(self, incident_id: UUID) -> IncidentDetailResponse:
        incident = await self.repository.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        alerts = await self.repository.list_external_alerts_for_incident(incident.id)
        base = IncidentDetailResponse.model_validate(
            {
                **self._incident_dict(incident),
                "external_alerts": [
                    ExternalAlertResponse.model_validate(alert) for alert in alerts
                ],
            }
        )
        if self.runbook_service is None:
            return base
        if incident.runbook_scenario:
            base.runbook = await self.runbook_service.get_by_scenario(incident.runbook_scenario)
            if base.runbook is None:
                base.runbook_authoring_link = self._runbook_authoring_link(
                    incident.runbook_scenario
                )
        else:
            base.runbook_scenario_unmapped = True
            base.runbook_authoring_link = self._runbook_authoring_link("new")
        return base

    async def list(
        self,
        *,
        status: str | None,
        severity: str | None,
        since: datetime | None,
        until: datetime | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[IncidentListItem]:
        rows = await self.repository.list_incidents(
            status=status,
            severity=severity,
            since=since,
            until=until,
            cursor=cursor,
            limit=limit,
        )
        return [IncidentListItem.model_validate(row) for row in rows]

    async def retry_due_alerts(self, now: datetime) -> int:
        pending = await self.repository.list_pending_retries(now)
        count = 0
        for alert in pending:
            if alert.attempt_count >= self.settings.incident_response.delivery_retry_max_attempts:
                await self.repository.update_external_alert_status(
                    alert.id,
                    status="failed",
                    error=alert.last_error or "retry attempts exhausted",
                    next_retry_at=None,
                )
                continue
            await self._dispatch_external_alert(alert.id)
            count += 1
        return count

    async def _record_delivery_failure(
        self,
        alert: IncidentExternalAlert,
        *,
        error: str,
        retryable: bool,
    ) -> None:
        attempt_count = alert.attempt_count + 1
        max_attempts = self.settings.incident_response.delivery_retry_max_attempts
        if not retryable or attempt_count >= max_attempts:
            await self.repository.update_external_alert_status(
                alert.id,
                status="failed",
                error=error,
                next_retry_at=None,
                increment_attempt=True,
            )
            LOGGER.error(
                "incident_response_provider_delivery_failed",
                extra={"external_alert_id": str(alert.id), "retryable": retryable},
            )
            return
        await self.repository.update_external_alert_status(
            alert.id,
            status="pending",
            error=error,
            next_retry_at=self._next_retry_at(attempt_count),
            increment_attempt=True,
        )

    def _next_retry_at(self, attempt_count: int) -> datetime:
        initial = self.settings.incident_response.delivery_retry_initial_seconds
        max_window = self.settings.incident_response.delivery_retry_max_window_seconds
        delay = min(initial * (2 ** max(attempt_count - 1, 0)), max_window)
        return datetime.now(UTC) + timedelta(seconds=delay)

    def _mapped_severity(self, integration: IncidentIntegration, severity: str) -> str:
        mapping = integration.alert_severity_mapping or {}
        mapped = mapping.get(severity)
        if mapped:
            return str(mapped)
        LOGGER.warning(
            "incident_response_missing_severity_mapping",
            extra={"provider": integration.provider, "severity": severity},
        )
        defaults = {
            "critical": "critical",
            "high": "high",
            "warning": "warning",
            "info": "info",
        }
        return defaults.get(severity, "warning")

    def _incident_dict(self, incident: Incident) -> dict[str, Any]:
        return {
            "id": incident.id,
            "condition_fingerprint": incident.condition_fingerprint,
            "severity": incident.severity,
            "status": incident.status,
            "title": incident.title,
            "description": incident.description,
            "triggered_at": incident.triggered_at,
            "resolved_at": incident.resolved_at,
            "related_executions": incident.related_executions,
            "related_event_ids": incident.related_event_ids,
            "runbook_scenario": incident.runbook_scenario,
            "alert_rule_class": incident.alert_rule_class,
            "post_mortem_id": incident.post_mortem_id,
        }

    def _runbook_authoring_link(self, scenario: str) -> str:
        return f"/operator/runbooks/new?scenario={scenario}"

    def _dedup_key(self, fingerprint: str) -> str:
        return f"incident:dedup:{fingerprint}"

    async def _redis_get(self, key: str) -> bytes | None:
        if self.redis_client is None:
            return None
        try:
            return await self.redis_client.get(key)
        except Exception:
            return None

    async def _redis_set(self, key: str, value: bytes, ttl: int) -> None:
        if self.redis_client is None:
            return
        try:
            await self.redis_client.set(key, value, ttl=ttl)
        except Exception:
            return

    async def _redis_delete(self, key: str) -> None:
        if self.redis_client is None:
            return
        try:
            await self.redis_client.delete(key)
        except Exception:
            return
