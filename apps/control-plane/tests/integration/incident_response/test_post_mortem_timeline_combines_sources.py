from __future__ import annotations

from datetime import timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import (
    TimelineCoverageState,
    TimelineEntry,
    TimelineSource,
    TimelineSourceCoverage,
)
from platform.incident_response.services.post_mortem_service import PostMortemService
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import MemoryIncidentRepository
from tests.unit.incident_response.support import make_incident


@pytest.mark.asyncio
async def test_post_mortem_timeline_combines_sources_and_marks_kafka_unavailable() -> None:
    resolved = make_incident(status="resolved")
    resolved.resolved_at = resolved.triggered_at + timedelta(minutes=30)
    degraded = make_incident(status="resolved")
    degraded.resolved_at = degraded.triggered_at + timedelta(minutes=30)
    repo = MemoryIncidentRepository()
    repo.incidents = {resolved.id: resolved, degraded.id: degraded}
    assembler = TimelineAssemblerStub()
    service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        timeline_assembler=assembler,  # type: ignore[arg-type]
    )

    first = await service.start(resolved.id, by_user_id=uuid4())
    assembler.kafka_available = False
    second = await service.start(degraded.id, by_user_id=uuid4())

    assert [entry.source for entry in first.timeline or []] == [
        TimelineSource.audit_chain,
        TimelineSource.execution_journal,
        TimelineSource.kafka,
    ]
    assert first.timeline_source_coverage.audit_chain == TimelineCoverageState.complete
    assert first.timeline_source_coverage.execution_journal == TimelineCoverageState.complete
    assert first.timeline_source_coverage.kafka == TimelineCoverageState.complete
    assert second.timeline_source_coverage.kafka == TimelineCoverageState.unavailable
    assert second.timeline_source_coverage.reasons["kafka"] == "consumer stopped"
    assert {entry.source for entry in second.timeline or []} == {
        TimelineSource.audit_chain,
        TimelineSource.execution_journal,
    }


class TimelineAssemblerStub:
    def __init__(self) -> None:
        self.kafka_available = True

    async def assemble(
        self,
        **kwargs: object,
    ) -> tuple[list[TimelineEntry], TimelineSourceCoverage]:
        start = kwargs["window_start"]
        entries = [
            TimelineEntry(
                id="audit:1",
                timestamp=start,
                source=TimelineSource.audit_chain,
                event_type="audit.changed",
                summary="Audit record",
            ),
            TimelineEntry(
                id="execution:1",
                timestamp=start + timedelta(seconds=1),  # type: ignore[operator]
                source=TimelineSource.execution_journal,
                event_type="execution.failed",
                summary="Execution failed",
            ),
        ]
        coverage = TimelineSourceCoverage()
        if self.kafka_available:
            entries.append(
                TimelineEntry(
                    id="kafka:1",
                    timestamp=start + timedelta(seconds=2),  # type: ignore[operator]
                    source=TimelineSource.kafka,
                    event_type="runtime.failed",
                    summary="Runtime event",
                )
            )
        else:
            coverage.kafka = TimelineCoverageState.unavailable
            coverage.reasons["kafka"] = "consumer stopped"
        return entries, coverage
