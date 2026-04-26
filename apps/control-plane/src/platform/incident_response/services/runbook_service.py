from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.exceptions import RunbookNotFoundError
from platform.incident_response.models import Runbook
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import (
    RunbookCreateRequest,
    RunbookListItem,
    RunbookResponse,
    RunbookUpdateRequest,
)
from typing import Any
from uuid import UUID, uuid4


class RunbookService:
    def __init__(
        self,
        *,
        repository: IncidentResponseRepository,
        settings: PlatformSettings,
        audit_chain_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.audit_chain_service = audit_chain_service

    async def create(
        self,
        payload: RunbookCreateRequest,
        *,
        updated_by: UUID | None,
    ) -> RunbookResponse:
        runbook = await self.repository.insert_runbook(
            scenario=payload.scenario,
            title=payload.title,
            symptoms=payload.symptoms,
            diagnostic_commands=[
                command.model_dump(mode="json") for command in payload.diagnostic_commands
            ],
            remediation_steps=payload.remediation_steps,
            escalation_path=payload.escalation_path,
            status=payload.status.value,
            updated_by=updated_by,
        )
        await self._audit("runbook.created", runbook, updated_by=updated_by)
        return self._response(runbook)

    async def get(self, runbook_id: UUID) -> RunbookResponse:
        runbook = await self.repository.get_runbook(runbook_id)
        if runbook is None:
            raise RunbookNotFoundError(runbook_id)
        return self._response(runbook)

    async def get_by_scenario(self, scenario: str) -> RunbookResponse | None:
        runbook = await self.repository.get_runbook_by_scenario(scenario)
        return None if runbook is None else self._response(runbook)

    async def list(
        self,
        *,
        status: str | None,
        scenario_query: str | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[RunbookListItem]:
        rows = await self.repository.list_runbooks(
            status=status,
            scenario_query=scenario_query,
            cursor=cursor,
            limit=limit,
        )
        return [
            RunbookListItem.model_validate(
                {
                    "id": row.id,
                    "scenario": row.scenario,
                    "title": row.title,
                    "status": row.status,
                    "version": row.version,
                    "updated_at": row.updated_at,
                    "is_stale": self._is_stale(row),
                }
            )
            for row in rows
        ]

    async def update(
        self,
        runbook_id: UUID,
        payload: RunbookUpdateRequest,
        *,
        updated_by: UUID | None,
    ) -> RunbookResponse:
        fields = payload.model_dump(exclude_none=True, exclude={"expected_version"}, mode="json")
        runbook = await self.repository.update_runbook(
            runbook_id,
            expected_version=payload.expected_version,
            updated_by=updated_by,
            fields=fields,
        )
        await self._audit("runbook.updated", runbook, updated_by=updated_by)
        return self._response(runbook)

    async def retire(self, runbook_id: UUID, *, updated_by: UUID | None) -> RunbookResponse:
        runbook = await self.repository.get_runbook(runbook_id)
        if runbook is None:
            raise RunbookNotFoundError(runbook_id)
        updated = await self.repository.update_runbook(
            runbook_id,
            expected_version=runbook.version,
            updated_by=updated_by,
            fields={"status": "retired"},
        )
        await self._audit("runbook.retired", updated, updated_by=updated_by)
        return self._response(updated)

    def lookup_by_alert_rule_class(self, alert_rule_class: str) -> str | None:
        return self.settings.incident_response.alert_rule_class_to_scenario.get(alert_rule_class)

    def _response(self, runbook: Runbook) -> RunbookResponse:
        return RunbookResponse.model_validate(
            {
                "id": runbook.id,
                "scenario": runbook.scenario,
                "title": runbook.title,
                "symptoms": runbook.symptoms,
                "diagnostic_commands": runbook.diagnostic_commands,
                "remediation_steps": runbook.remediation_steps,
                "escalation_path": runbook.escalation_path,
                "status": runbook.status,
                "version": runbook.version,
                "created_at": runbook.created_at,
                "updated_at": runbook.updated_at,
                "updated_by": runbook.updated_by,
                "is_stale": self._is_stale(runbook),
            }
        )

    def _is_stale(self, runbook: Runbook) -> bool:
        threshold = datetime.now(UTC) - timedelta(
            days=self.settings.incident_response.runbook_freshness_window_days
        )
        return runbook.updated_at < threshold

    async def _audit(
        self,
        action: str,
        runbook: Runbook,
        *,
        updated_by: UUID | None,
    ) -> None:
        append = getattr(self.audit_chain_service, "append", None)
        if append is None:
            return
        payload = {
            "action": action,
            "runbook_id": str(runbook.id),
            "scenario": runbook.scenario,
            "version": runbook.version,
            "updated_by": None if updated_by is None else str(updated_by),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        await append(uuid4(), "incident_response.runbooks", canonical)
