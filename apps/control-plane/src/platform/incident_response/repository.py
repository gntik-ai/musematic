from __future__ import annotations

from datetime import UTC, datetime
from platform.incident_response.exceptions import RunbookConcurrentEditError
from platform.incident_response.models import (
    Incident,
    IncidentExternalAlert,
    IncidentIntegration,
    PostMortem,
    Runbook,
)
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class IncidentResponseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_integration(
        self,
        *,
        provider: str,
        integration_key_ref: str,
        alert_severity_mapping: dict[str, str],
        enabled: bool = True,
    ) -> IncidentIntegration:
        integration = IncidentIntegration(
            provider=provider,
            integration_key_ref=integration_key_ref,
            alert_severity_mapping=dict(alert_severity_mapping),
            enabled=enabled,
        )
        self.session.add(integration)
        await self.session.flush()
        return integration

    async def get_integration(self, integration_id: UUID) -> IncidentIntegration | None:
        return await self.session.get(IncidentIntegration, integration_id)

    async def list_integrations(self, *, enabled_only: bool = False) -> list[IncidentIntegration]:
        statement = select(IncidentIntegration)
        if enabled_only:
            statement = statement.where(IncidentIntegration.enabled.is_(True))
        result = await self.session.execute(
            statement.order_by(IncidentIntegration.provider.asc(), IncidentIntegration.id.asc())
        )
        return list(result.scalars().all())

    async def update_integration(
        self,
        integration_id: UUID,
        *,
        enabled: bool | None = None,
        alert_severity_mapping: dict[str, str] | None = None,
    ) -> IncidentIntegration | None:
        integration = await self.get_integration(integration_id)
        if integration is None:
            return None
        if enabled is not None:
            integration.enabled = enabled
        if alert_severity_mapping is not None:
            integration.alert_severity_mapping = dict(alert_severity_mapping)
        integration.updated_at = datetime.now(UTC)
        await self.session.flush()
        return integration

    async def delete_integration(self, integration_id: UUID) -> bool:
        integration = await self.get_integration(integration_id)
        if integration is None:
            return False
        await self.session.delete(integration)
        await self.session.flush()
        return True

    async def find_open_incident_by_fingerprint(
        self,
        condition_fingerprint: str,
    ) -> Incident | None:
        result = await self.session.execute(
            select(Incident)
            .where(
                Incident.condition_fingerprint == condition_fingerprint,
                Incident.status.in_(("open", "acknowledged")),
            )
            .order_by(Incident.triggered_at.desc(), Incident.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def insert_incident(
        self,
        *,
        condition_fingerprint: str,
        severity: str,
        title: str,
        description: str,
        related_execution_ids: list[UUID],
        related_event_ids: list[UUID],
        runbook_scenario: str | None,
        alert_rule_class: str,
    ) -> Incident:
        incident = Incident(
            condition_fingerprint=condition_fingerprint,
            severity=severity,
            status="open",
            title=title,
            description=description,
            related_executions=list(related_execution_ids),
            related_event_ids=list(related_event_ids),
            runbook_scenario=runbook_scenario,
            alert_rule_class=alert_rule_class,
        )
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def append_recurrence(
        self,
        incident_id: UUID,
        related_event_id: UUID | None,
    ) -> Incident | None:
        values: dict[str, Any] = {}
        if related_event_id is not None:
            values["related_event_ids"] = func.array_append(
                Incident.related_event_ids,
                related_event_id,
            )
        if not values:
            return await self.get_incident(incident_id)
        result = await self.session.execute(
            update(Incident).where(Incident.id == incident_id).values(**values).returning(Incident)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def append_incident_execution(
        self,
        incident_id: UUID,
        execution_id: UUID,
    ) -> Incident | None:
        result = await self.session.execute(
            update(Incident)
            .where(
                ~Incident.related_executions.contains([execution_id]), Incident.id == incident_id
            )
            .values(related_executions=func.array_append(Incident.related_executions, execution_id))
            .returning(Incident)
        )
        row = result.scalar_one_or_none()
        await self.session.flush()
        return row or await self.get_incident(incident_id)

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        return await self.session.get(Incident, incident_id)

    async def list_incidents(
        self,
        *,
        status: str | None,
        severity: str | None,
        since: datetime | None,
        until: datetime | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[Incident]:
        statement = select(Incident)
        if status is not None:
            statement = statement.where(Incident.status == status)
        if severity is not None:
            statement = statement.where(Incident.severity == severity)
        if since is not None:
            statement = statement.where(Incident.triggered_at >= since)
        if until is not None:
            statement = statement.where(Incident.triggered_at <= until)
        if cursor is not None:
            statement = statement.where(Incident.triggered_at < cursor)
        result = await self.session.execute(
            statement.order_by(desc(Incident.triggered_at), desc(Incident.id)).limit(limit)
        )
        return list(result.scalars().all())

    async def resolve_incident(
        self,
        incident_id: UUID,
        resolved_at: datetime,
        *,
        status: str = "resolved",
    ) -> Incident | None:
        incident = await self.get_incident(incident_id)
        if incident is None:
            return None
        incident.status = status
        incident.resolved_at = resolved_at
        await self.session.flush()
        return incident

    async def update_incident_post_mortem(
        self,
        incident_id: UUID,
        post_mortem_id: UUID,
    ) -> None:
        await self.session.execute(
            update(Incident).where(Incident.id == incident_id).values(post_mortem_id=post_mortem_id)
        )
        await self.session.flush()

    async def insert_external_alert(
        self,
        *,
        incident_id: UUID,
        integration_id: UUID,
        next_retry_at: datetime | None = None,
    ) -> IncidentExternalAlert:
        alert = IncidentExternalAlert(
            incident_id=incident_id,
            integration_id=integration_id,
            delivery_status="pending",
            next_retry_at=next_retry_at,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_external_alert(
        self,
        external_alert_id: UUID,
    ) -> IncidentExternalAlert | None:
        return await self.session.get(IncidentExternalAlert, external_alert_id)

    async def list_external_alerts_for_incident(
        self,
        incident_id: UUID,
    ) -> list[IncidentExternalAlert]:
        result = await self.session.execute(
            select(IncidentExternalAlert)
            .where(IncidentExternalAlert.incident_id == incident_id)
            .order_by(IncidentExternalAlert.id.asc())
        )
        return list(result.scalars().all())

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
        alert = await self.get_external_alert(external_alert_id)
        if alert is None:
            return None
        alert.delivery_status = status
        if provider_reference is not None:
            alert.provider_reference = provider_reference
        alert.last_error = error
        alert.next_retry_at = next_retry_at
        alert.last_attempt_at = datetime.now(UTC)
        if increment_attempt:
            alert.attempt_count += 1
        await self.session.flush()
        return alert

    async def list_pending_retries(
        self, now: datetime, *, limit: int = 500
    ) -> list[IncidentExternalAlert]:
        result = await self.session.execute(
            select(IncidentExternalAlert)
            .where(
                IncidentExternalAlert.delivery_status == "pending",
                IncidentExternalAlert.next_retry_at.is_not(None),
                IncidentExternalAlert.next_retry_at <= now,
            )
            .order_by(IncidentExternalAlert.next_retry_at.asc(), IncidentExternalAlert.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def insert_runbook(
        self,
        *,
        scenario: str,
        title: str,
        symptoms: str,
        diagnostic_commands: list[dict[str, str]],
        remediation_steps: str,
        escalation_path: str,
        status: str,
        updated_by: UUID | None,
    ) -> Runbook:
        runbook = Runbook(
            scenario=scenario,
            title=title,
            symptoms=symptoms,
            diagnostic_commands=list(diagnostic_commands),
            remediation_steps=remediation_steps,
            escalation_path=escalation_path,
            status=status,
            updated_by=updated_by,
        )
        self.session.add(runbook)
        await self.session.flush()
        return runbook

    async def get_runbook(self, runbook_id: UUID) -> Runbook | None:
        return await self.session.get(Runbook, runbook_id)

    async def get_runbook_by_scenario(
        self,
        scenario: str,
        *,
        active_only: bool = True,
    ) -> Runbook | None:
        statement = select(Runbook).where(Runbook.scenario == scenario)
        if active_only:
            statement = statement.where(Runbook.status == "active")
        result = await self.session.execute(statement.limit(1))
        return result.scalar_one_or_none()

    async def list_runbooks(
        self,
        *,
        status: str | None,
        scenario_query: str | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[Runbook]:
        statement = select(Runbook)
        if status is not None:
            statement = statement.where(Runbook.status == status)
        if scenario_query:
            statement = statement.where(Runbook.scenario.ilike(f"%{scenario_query}%"))
        if cursor is not None:
            statement = statement.where(Runbook.updated_at < cursor)
        result = await self.session.execute(statement.order_by(Runbook.scenario.asc()).limit(limit))
        return list(result.scalars().all())

    async def update_runbook(
        self,
        runbook_id: UUID,
        *,
        expected_version: int,
        updated_by: UUID | None,
        fields: dict[str, Any],
    ) -> Runbook:
        values = dict(fields)
        values["version"] = Runbook.version + 1
        values["updated_by"] = updated_by
        values["updated_at"] = func.now()
        result = await self.session.execute(
            update(Runbook)
            .where(and_(Runbook.id == runbook_id, Runbook.version == expected_version))
            .values(**values)
            .returning(Runbook)
        )
        runbook = result.scalar_one_or_none()
        await self.session.flush()
        if runbook is not None:
            return runbook
        current = await self.get_runbook(runbook_id)
        raise RunbookConcurrentEditError(
            runbook_id,
            None if current is None else current.version,
        )

    async def mark_runbooks_stale(self, threshold_ts: datetime) -> list[Runbook]:
        result = await self.session.execute(
            select(Runbook)
            .where(Runbook.status == "active", Runbook.updated_at < threshold_ts)
            .order_by(Runbook.updated_at.asc(), Runbook.id.asc())
        )
        return list(result.scalars().all())

    async def insert_post_mortem(
        self,
        *,
        post_mortem_id: UUID | None = None,
        incident_id: UUID,
        timeline: list[dict[str, Any]] | None,
        timeline_blob_ref: str | None,
        timeline_source_coverage: dict[str, Any],
        created_by: UUID | None,
    ) -> PostMortem:
        values: dict[str, Any] = {}
        if post_mortem_id is not None:
            values["id"] = post_mortem_id
        post_mortem = PostMortem(
            **values,
            incident_id=incident_id,
            status="draft",
            timeline=timeline,
            timeline_blob_ref=timeline_blob_ref,
            timeline_source_coverage=timeline_source_coverage,
            created_by=created_by,
        )
        self.session.add(post_mortem)
        await self.session.flush()
        return post_mortem

    async def get_post_mortem(self, post_mortem_id: UUID) -> PostMortem | None:
        return await self.session.get(PostMortem, post_mortem_id)

    async def get_post_mortem_by_incident(self, incident_id: UUID) -> PostMortem | None:
        result = await self.session.execute(
            select(PostMortem).where(PostMortem.incident_id == incident_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def update_post_mortem_section(
        self,
        post_mortem_id: UUID,
        **fields: Any,
    ) -> PostMortem | None:
        post_mortem = await self.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(post_mortem, key, value)
        await self.session.flush()
        return post_mortem

    async def list_post_mortems_by_execution(self, execution_id: UUID) -> list[PostMortem]:
        result = await self.session.execute(
            select(PostMortem)
            .join(Incident, Incident.id == PostMortem.incident_id)
            .where(Incident.related_executions.contains([execution_id]))
            .order_by(PostMortem.created_at.desc(), PostMortem.id.desc())
        )
        return list(result.scalars().all())

    async def list_post_mortems_by_certification(self, certification_id: UUID) -> list[PostMortem]:
        result = await self.session.execute(
            select(PostMortem)
            .where(PostMortem.linked_certification_ids.contains([certification_id]))
            .order_by(PostMortem.created_at.desc(), PostMortem.id.desc())
        )
        return list(result.scalars().all())

    async def append_linked_certification(
        self,
        post_mortem_id: UUID,
        certification_id: UUID,
    ) -> PostMortem | None:
        result = await self.session.execute(
            update(PostMortem)
            .where(
                PostMortem.id == post_mortem_id,
                ~PostMortem.linked_certification_ids.contains([certification_id]),
            )
            .values(
                linked_certification_ids=func.array_append(
                    PostMortem.linked_certification_ids,
                    certification_id,
                )
            )
            .returning(PostMortem)
        )
        row = result.scalar_one_or_none()
        await self.session.flush()
        return row or await self.get_post_mortem(post_mortem_id)

    async def mark_published(
        self, post_mortem_id: UUID, published_at: datetime
    ) -> PostMortem | None:
        post_mortem = await self.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            return None
        post_mortem.status = "published"
        post_mortem.published_at = published_at
        await self.session.flush()
        return post_mortem

    async def mark_distributed(
        self,
        post_mortem_id: UUID,
        recipients_outcomes: list[dict[str, Any]],
        distributed_at: datetime,
    ) -> PostMortem | None:
        post_mortem = await self.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            return None
        post_mortem.status = "distributed"
        post_mortem.distribution_list = recipients_outcomes
        post_mortem.distributed_at = distributed_at
        await self.session.flush()
        return post_mortem
