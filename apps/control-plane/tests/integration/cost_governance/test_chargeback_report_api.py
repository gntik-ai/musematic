from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from platform.cost_governance.services.chargeback_service import ChargebackService
from uuid import UUID, uuid4

import pytest


class Repo:
    def __init__(self, rows: dict[UUID, list[dict[str, object]]]) -> None:
        self.rows = rows

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, object]]:
        del group_by, since, until
        return self.rows.get(workspace_id, [])

    async def list_workspace_ids_with_costs(self) -> list[UUID]:
        return list(self.rows)


class Visible:
    def __init__(self, ids: list[UUID]) -> None:
        self.ids = ids

    async def get_user_workspace_ids(self, requester: UUID) -> list[UUID]:
        del requester
        return self.ids


@pytest.mark.asyncio
async def test_chargeback_report_export_excludes_hidden_workspace() -> None:
    visible_ids = [uuid4(), uuid4()]
    hidden_id = uuid4()
    rows = {
        workspace_id: [
            {
                "workspace_id": workspace_id,
                "cost_type": "model",
                "model_cost_cents": Decimal("10"),
                "compute_cost_cents": Decimal("1"),
                "storage_cost_cents": Decimal("2"),
                "overhead_cost_cents": Decimal("3"),
                "total_cost_cents": Decimal("16"),
            }
        ]
        for workspace_id in [*visible_ids, hidden_id]
    }
    service = ChargebackService(
        repository=Repo(rows),  # type: ignore[arg-type]
        clickhouse_repository=None,
        workspaces_service=Visible(visible_ids),
    )

    report = await service.generate_report(
        requester=uuid4(),
        dimensions=["workspace", "cost_type"],
        group_by=["workspace", "cost_type"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 30, tzinfo=UTC),
        workspace_filter=[*visible_ids, hidden_id],
    )
    export = service.export_report(report, "csv")
    parsed = list(csv.DictReader(io.StringIO(export.content)))

    assert report.totals["total_cost_cents"] == Decimal("32")
    assert len(parsed) == 2
    assert str(hidden_id) not in export.content
