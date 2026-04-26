from __future__ import annotations

from decimal import Decimal
from platform.cost_governance.services.anomaly_service import AnomalyService
from uuid import uuid4

import pytest

from tests.integration.cost_governance.support import RecordingProducer
from tests.unit.cost_governance.test_anomaly_service import AlertRecorder, History, Repo


@pytest.mark.asyncio
async def test_anomaly_detect_ack_resolve_and_refire_lifecycle() -> None:
    workspace_id = uuid4()
    repo = Repo()
    alerts = AlertRecorder()
    producer = RecordingProducer()
    service = AnomalyService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10"), Decimal("10"), Decimal("10"), Decimal("80")]),  # type: ignore[arg-type]
        kafka_producer=producer,  # type: ignore[arg-type]
        alert_service=alerts,
    )

    first = await service.detect(workspace_id)
    duplicate = await service.detect(workspace_id)
    assert first is not None
    assert duplicate is not None
    assert first.id == duplicate.id
    assert len(repo.rows) == 1
    assert len(alerts.calls) == 1
    assert producer.events[0]["event_type"] == "cost.anomaly.detected"

    acknowledged = await service.acknowledge(first.id, uuid4())
    resolved = await service.resolve(first.id)
    refired = await service.detect(workspace_id)

    assert acknowledged is not None
    assert acknowledged.state == "acknowledged"
    assert resolved is not None
    assert resolved.state == "resolved"
    assert refired is not None
    assert refired.id != first.id
