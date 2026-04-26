from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.cost_governance.services.chargeback_service import ChargebackService
from typing import Any
from uuid import UUID, uuid4

import pytest


class FakeRepository:
    def __init__(self, rows_by_workspace: dict[UUID, list[dict[str, object]]]) -> None:
        self.rows_by_workspace = rows_by_workspace
        self.queries: list[UUID] = []

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, object]]:
        del group_by, since, until
        self.queries.append(workspace_id)
        return self.rows_by_workspace.get(workspace_id, [])

    async def list_workspace_ids_with_costs(self) -> list[UUID]:
        return list(self.rows_by_workspace)


class VisibleWorkspaces:
    def __init__(self, ids: list[UUID]) -> None:
        self.ids = ids

    async def get_user_workspace_ids(self, requester: UUID) -> list[UUID]:
        del requester
        return self.ids


class ClickHouseRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def query_cost_rollups(
        self,
        workspace_ids: list[UUID],
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, object]]:
        del workspace_ids, group_by, since, until
        return self.rows


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *payload: Any) -> None:
        self.events.append(payload)


@pytest.mark.asyncio
async def test_report_reconciles_and_filters_rbac_at_query_layer() -> None:
    visible = uuid4()
    hidden = uuid4()
    repo = FakeRepository(
        {
            visible: [
                {
                    "workspace_id": visible,
                    "cost_type": "model",
                    "model_cost_cents": Decimal("10"),
                    "compute_cost_cents": Decimal("2"),
                    "storage_cost_cents": Decimal("1"),
                    "overhead_cost_cents": Decimal("0.5"),
                    "total_cost_cents": Decimal("13.5"),
                }
            ],
            hidden: [
                {
                    "workspace_id": hidden,
                    "model_cost_cents": Decimal("999"),
                    "compute_cost_cents": Decimal("0"),
                    "storage_cost_cents": Decimal("0"),
                    "overhead_cost_cents": Decimal("0"),
                    "total_cost_cents": Decimal("999"),
                }
            ],
        }
    )
    service = ChargebackService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=None,
        workspaces_service=VisibleWorkspaces([visible]),
    )

    report = await service.generate_report(
        requester=uuid4(),
        dimensions=["workspace", "cost_type"],
        group_by=["workspace", "cost_type"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 30, tzinfo=UTC),
        workspace_filter=[visible, hidden],
    )

    assert repo.queries == [visible]
    assert report.totals["total_cost_cents"] == Decimal("13.5")
    assert report.rows[0].dimensions["workspace_id"] == visible


@pytest.mark.asyncio
async def test_export_includes_dimensions_time_range_and_totals() -> None:
    workspace_id = uuid4()
    repo = FakeRepository(
        {
            workspace_id: [
                {
                    "workspace_id": workspace_id,
                    "agent_id": uuid4(),
                    "model_cost_cents": Decimal("3"),
                    "compute_cost_cents": Decimal("4"),
                    "storage_cost_cents": Decimal("0"),
                    "overhead_cost_cents": Decimal("0"),
                    "total_cost_cents": Decimal("7"),
                }
            ]
        }
    )
    service = ChargebackService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=None,
        workspaces_service=None,
    )
    report = await service.generate_report(
        requester=uuid4(),
        dimensions=["workspace", "agent"],
        group_by=["workspace", "agent"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 2, tzinfo=UTC),
    )

    csv_export = service.export_report(report, "csv", workspace_id=workspace_id)
    ndjson_export = service.export_report(report, "ndjson", workspace_id=workspace_id)

    assert "dimensions" in csv_export.content
    assert str(workspace_id) in csv_export.filename
    assert ndjson_export.content_type == "application/x-ndjson"
    assert report.totals["total_cost_cents"] == Decimal("7")


@pytest.mark.asyncio
async def test_chargeback_clickhouse_empty_visibility_and_audit_paths() -> None:
    workspace_id = uuid4()
    repo = FakeRepository({workspace_id: []})
    audit = AuditRecorder()
    service = ChargebackService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=ClickHouseRows(
            [
                {
                    "workspace_id": workspace_id,
                    "model_cost_cents": Decimal("1"),
                    "compute_cost_cents": Decimal("0"),
                    "storage_cost_cents": Decimal("0"),
                    "overhead_cost_cents": Decimal("0"),
                    "total_cost_cents": Decimal("1"),
                }
            ]
        ),  # type: ignore[arg-type]
        workspaces_service=object(),
        audit_chain_service=audit,
    )

    report = await service.generate_report(
        requester=uuid4(),
        dimensions=["workspace"],
        group_by=["workspace"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 2, tzinfo=UTC),
    )
    empty = await ChargebackService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=None,
        workspaces_service=VisibleWorkspaces([]),
    ).generate_report(
        requester=uuid4(),
        dimensions=["workspace"],
        group_by=["workspace"],
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 4, 2, tzinfo=UTC),
    )

    assert report.totals["total_cost_cents"] == Decimal("1")
    assert empty.rows == []
    assert len(audit.events) == 1
