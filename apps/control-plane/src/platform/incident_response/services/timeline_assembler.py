from __future__ import annotations

from datetime import datetime
from platform.incident_response.exceptions import IncidentNotFoundError
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import (
    TimelineCoverageState,
    TimelineEntry,
    TimelineSource,
    TimelineSourceCoverage,
)
from platform.incident_response.services.kafka_replay import KafkaTimelineReplay
from typing import Any
from uuid import UUID


class TimelineAssembler:
    def __init__(
        self,
        *,
        repository: IncidentResponseRepository,
        audit_chain_service: Any | None,
        execution_service: Any | None,
        kafka_replay: KafkaTimelineReplay | None,
        kafka_topics: list[str],
    ) -> None:
        self.repository = repository
        self.audit_chain_service = audit_chain_service
        self.execution_service = execution_service
        self.kafka_replay = kafka_replay
        self.kafka_topics = kafka_topics

    async def assemble(
        self,
        *,
        incident_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[list[TimelineEntry], TimelineSourceCoverage]:
        incident = await self.repository.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        coverage = TimelineSourceCoverage()
        entries: list[TimelineEntry] = []

        try:
            if self.audit_chain_service is None:
                raise RuntimeError("audit chain service unavailable")
            audit_rows = await self.audit_chain_service.list_audit_sources_in_window(
                window_start,
                window_end,
            )
            entries.extend(
                TimelineEntry(
                    id=f"audit_chain:{row.id}",
                    timestamp=row.created_at,
                    source=TimelineSource.audit_chain,
                    event_type=row.audit_event_source,
                    summary=f"Audit chain entry {row.sequence_number}",
                    payload_summary={
                        "sequence_number": row.sequence_number,
                        "audit_event_id": None
                        if row.audit_event_id is None
                        else str(row.audit_event_id),
                    },
                )
                for row in audit_rows
            )
        except Exception as exc:
            coverage.audit_chain = TimelineCoverageState.unavailable
            coverage.reasons["audit_chain"] = str(exc)

        try:
            if self.execution_service is None:
                raise RuntimeError("execution service unavailable")
            execution_rows = await self.execution_service.get_journal_in_window(
                incident.related_executions,
                window_start,
                window_end,
            )
            entries.extend(
                TimelineEntry(
                    id=f"execution_journal:{row.id}",
                    timestamp=row.created_at,
                    source=TimelineSource.execution_journal,
                    event_type=str(row.event_type),
                    summary=f"Execution {row.execution_id} event {row.sequence}",
                    payload_summary={
                        "execution_id": str(row.execution_id),
                        "sequence": row.sequence,
                        "step_id": row.step_id,
                    },
                )
                for row in execution_rows
            )
        except Exception as exc:
            coverage.execution_journal = TimelineCoverageState.unavailable
            coverage.reasons["execution_journal"] = str(exc)

        try:
            if self.kafka_replay is None:
                raise RuntimeError("Kafka replay unavailable")
            entries.extend(
                await self.kafka_replay.read_window(self.kafka_topics, window_start, window_end)
            )
            if self.kafka_replay.last_window_partial:
                coverage.kafka = TimelineCoverageState.partial
        except Exception as exc:
            coverage.kafka = TimelineCoverageState.unavailable
            coverage.reasons["kafka"] = str(exc)

        entries.sort(key=lambda item: (item.timestamp, item.source.value, item.id))
        return entries, coverage
