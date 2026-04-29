from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.exceptions import RunbookConcurrentEditError
from platform.incident_response.models import Runbook
from platform.incident_response.schemas import (
    DiagnosticCommand,
    RunbookCreateRequest,
    RunbookStatus,
    RunbookUpdateRequest,
)
from platform.incident_response.services.runbook_service import RunbookService
from typing import Any
from uuid import UUID, uuid4

import pytest


class RunbookRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Runbook] = {}

    async def insert_runbook(self, **fields: Any) -> Runbook:
        now = datetime.now(UTC)
        row = Runbook(
            id=uuid4(),
            scenario=fields["scenario"],
            title=fields["title"],
            symptoms=fields["symptoms"],
            diagnostic_commands=list(fields["diagnostic_commands"]),
            remediation_steps=fields["remediation_steps"],
            escalation_path=fields["escalation_path"],
            status=fields["status"],
            version=1,
            created_at=now,
            updated_at=now,
            updated_by=fields["updated_by"],
        )
        self.rows[row.id] = row
        return row

    async def get_runbook(self, runbook_id: UUID) -> Runbook | None:
        return self.rows.get(runbook_id)

    async def get_runbook_by_scenario(self, scenario: str) -> Runbook | None:
        return next(
            (
                row
                for row in self.rows.values()
                if row.scenario == scenario and row.status == "active"
            ),
            None,
        )

    async def list_runbooks(
        self,
        *,
        status: str | None,
        scenario_query: str | None,
        cursor: datetime | None,
        limit: int,
    ) -> list[Runbook]:
        del cursor
        rows = list(self.rows.values())
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if scenario_query is not None:
            rows = [row for row in rows if scenario_query in row.scenario]
        return rows[:limit]

    async def update_runbook(
        self,
        runbook_id: UUID,
        *,
        expected_version: int,
        updated_by: UUID | None,
        fields: dict[str, Any],
    ) -> Runbook:
        row = self.rows[runbook_id]
        if row.version != expected_version:
            raise RunbookConcurrentEditError(runbook_id, row.version)
        for key, value in fields.items():
            setattr(row, key, value)
        row.version += 1
        row.updated_by = updated_by
        row.updated_at = datetime.now(UTC)
        return row


@pytest.mark.asyncio
async def test_runbook_crud_lookup_staleness_concurrency_and_retire() -> None:
    repo = RunbookRepository()
    service = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    actor = uuid4()
    created = await service.create(_create_payload(), updated_by=actor)

    assert created.scenario == "kafka_lag"
    assert created.diagnostic_commands[0].command == "kafka-consumer-groups.sh --describe"
    assert (await service.get_by_scenario("kafka_lag")) == created

    repo.rows[created.id].updated_at = datetime.now(UTC) - timedelta(days=120)
    stale = await service.get(created.id)
    listed = await service.list(status="active", scenario_query="kafka", cursor=None, limit=10)
    assert stale.is_stale is True
    assert listed[0].is_stale is True

    updated = await service.update(
        created.id,
        RunbookUpdateRequest(expected_version=1, title="Updated Kafka lag"),
        updated_by=actor,
    )
    assert updated.version == 2
    assert updated.title == "Updated Kafka lag"

    with pytest.raises(RunbookConcurrentEditError) as exc_info:
        await service.update(
            created.id,
            RunbookUpdateRequest(expected_version=1, title="Stale write"),
            updated_by=actor,
        )
    assert exc_info.value.current_version == 2

    retired = await service.retire(created.id, updated_by=actor)
    assert retired.status == RunbookStatus.retired
    assert repo.rows[created.id].status == "retired"


def test_diagnostic_commands_require_command_and_description() -> None:
    with pytest.raises(ValueError, match="String should have at least 1 character"):
        _create_payload(diagnostic_commands=[{"command": "", "description": "missing"}])


def _create_payload(
    *,
    diagnostic_commands: list[dict[str, str]] | None = None,
) -> RunbookCreateRequest:
    return RunbookCreateRequest(
        scenario="kafka_lag",
        title="Kafka lag",
        symptoms="Consumers are behind the latest offset.",
        diagnostic_commands=[
            DiagnosticCommand.model_validate(item)
            for item in (
                diagnostic_commands
                or [
                    {
                        "command": "kafka-consumer-groups.sh --describe",
                        "description": "Inspect consumer lag by group.",
                    }
                ]
            )
        ],
        remediation_steps="Scale consumers or pause high-volume producers.",
        escalation_path="Escalate to platform streaming on-call.",
        status=RunbookStatus.active,
    )
