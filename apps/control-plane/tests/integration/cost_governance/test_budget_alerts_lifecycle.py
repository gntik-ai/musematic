from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.budget_service import BudgetService, period_bounds
from uuid import uuid4

import pytest

from tests.integration.cost_governance.support import RecordingProducer
from tests.unit.cost_governance.test_budget_service import (
    BudgetRow,
    FakeBudgetRepository,
    RecordingAlertService,
)


@pytest.mark.asyncio
async def test_budget_alerts_reset_on_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="daily", budget_cents=100)
    repository = FakeBudgetRepository(budget)
    producer = RecordingProducer()
    alerts = RecordingAlertService()
    service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=None,
        settings=PlatformSettings(),
        kafka_producer=producer,  # type: ignore[arg-type]
        alert_service=alerts,
    )

    for spend in (Decimal("50"), Decimal("80"), Decimal("100")):
        repository.spend = spend
        await service.evaluate_thresholds(workspace_id)
    await service.evaluate_thresholds(workspace_id)

    assert [event["event_type"] for event in producer.events] == [
        "cost.budget.threshold.reached",
        "cost.budget.threshold.reached",
        "cost.budget.threshold.reached",
    ]
    assert len(alerts.calls) == 3

    monkeypatch.setattr(
        "platform.cost_governance.services.budget_service.period_bounds",
        lambda period_type: period_bounds(period_type, datetime(2026, 4, 27, 12, tzinfo=UTC)),
    )
    repository.spend = Decimal("50")
    assert len(await service.evaluate_thresholds(workspace_id)) == 1
