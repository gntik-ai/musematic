from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.attribution_service import AttributionService
from platform.cost_governance.services.chargeback_service import ChargebackService
from uuid import uuid4

import pytest

from tests.integration.cost_governance.support import AttributionRepository, ClickHouseSink


@pytest.mark.asyncio
async def test_late_arriving_correction_preserves_original_and_reconciles_report() -> None:
    workspace_id = uuid4()
    repository = AttributionRepository()
    service = AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        clickhouse_repository=ClickHouseSink(),  # type: ignore[arg-type]
        fail_open=False,
    )
    original = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="initial",
        workspace_id=workspace_id,
        agent_id=None,
        user_id=uuid4(),
        payload={"model_cost_cents": "10"},
    )
    assert original is not None

    correction = await service.record_correction(
        original.id,
        deltas={"compute_cost_cents": "2.5"},
        reason="late compute invoice",
    )
    result = await service.get_execution_cost(original.execution_id)
    report = await ChargebackService(
        repository=repository,  # type: ignore[arg-type]
        clickhouse_repository=None,
        workspaces_service=None,
    ).generate_report(
        requester=uuid4(),
        dimensions=["workspace"],
        group_by=["workspace"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 30, tzinfo=UTC),
    )

    assert correction.correction_of == original.id
    assert original.compute_cost_cents == Decimal("0.0000")
    assert result is not None
    assert result["totals"]["total_cost_cents"] == Decimal("12.5000")
    assert report.totals["total_cost_cents"] == Decimal("12.5000")
