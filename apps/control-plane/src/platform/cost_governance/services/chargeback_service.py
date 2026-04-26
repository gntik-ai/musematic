from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from platform.common.audit_hook import audit_chain_hook
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.repository import CostGovernanceRepository
from platform.cost_governance.schemas import (
    ChargebackExportResponse,
    ChargebackReportResponse,
    ChargebackReportRow,
)
from typing import Any
from uuid import UUID, uuid4


class ChargebackService:
    def __init__(
        self,
        *,
        repository: CostGovernanceRepository,
        clickhouse_repository: ClickHouseCostRepository | None,
        workspaces_service: Any | None,
        audit_chain_service: Any | None = None,
        default_currency: str = "USD",
    ) -> None:
        self.repository = repository
        self.clickhouse_repository = clickhouse_repository
        self.workspaces_service = workspaces_service
        self.audit_chain_service = audit_chain_service
        self.default_currency = default_currency

    async def generate_report(
        self,
        *,
        requester: UUID,
        dimensions: list[str],
        group_by: list[str],
        since: datetime,
        until: datetime,
        workspace_filter: list[UUID] | None = None,
    ) -> ChargebackReportResponse:
        visible_workspace_ids = await self._visible_workspace_ids(requester)
        if workspace_filter is not None:
            visible_workspace_ids = [
                workspace_id
                for workspace_id in workspace_filter
                if workspace_id in set(visible_workspace_ids)
            ]
        rows = await self._query_rows(visible_workspace_ids, group_by, since, until)
        report_rows = [
            ChargebackReportRow(
                dimensions=_dimension_payload(row),
                model_cost_cents=Decimal(str(row.get("model_cost_cents") or 0)),
                compute_cost_cents=Decimal(str(row.get("compute_cost_cents") or 0)),
                storage_cost_cents=Decimal(str(row.get("storage_cost_cents") or 0)),
                overhead_cost_cents=Decimal(str(row.get("overhead_cost_cents") or 0)),
                total_cost_cents=Decimal(str(row.get("total_cost_cents") or 0)),
                currency=self.default_currency,
            )
            for row in rows
        ]
        totals = {
            "model_cost_cents": sum(
                (row.model_cost_cents for row in report_rows),
                Decimal("0"),
            ),
            "compute_cost_cents": sum(
                (row.compute_cost_cents for row in report_rows),
                Decimal("0"),
            ),
            "storage_cost_cents": sum(
                (row.storage_cost_cents for row in report_rows),
                Decimal("0"),
            ),
            "overhead_cost_cents": sum(
                (row.overhead_cost_cents for row in report_rows),
                Decimal("0"),
            ),
            "total_cost_cents": sum(
                (row.total_cost_cents for row in report_rows),
                Decimal("0"),
            ),
        }
        response = ChargebackReportResponse(
            dimensions=dimensions,
            time_range={"since": since, "until": until},
            group_by=group_by,
            rows=report_rows,
            totals=totals,
            currency=self.default_currency,
            generated_at=datetime.now(UTC),
        )
        await self._audit(
            "cost.chargeback.report.generated",
            requester,
            {"requester": requester, "workspace_count": len(visible_workspace_ids)},
        )
        return response

    def export_report(
        self,
        report: ChargebackReportResponse,
        report_format: str = "csv",
        *,
        workspace_id: UUID | None = None,
    ) -> ChargebackExportResponse:
        stem = workspace_id or "all"
        since = report.time_range["since"].date().isoformat()
        until = report.time_range["until"].date().isoformat()
        if report_format == "ndjson":
            content = "\n".join(row.model_dump_json() for row in report.rows)
            return ChargebackExportResponse(
                filename=f"chargeback-{stem}-{since}-{until}.ndjson",
                content_type="application/x-ndjson",
                content=content,
            )
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "dimensions",
                "model_cost_cents",
                "compute_cost_cents",
                "storage_cost_cents",
                "overhead_cost_cents",
                "total_cost_cents",
                "currency",
            ],
        )
        writer.writeheader()
        for row in report.rows:
            writer.writerow(
                {
                    "dimensions": json.dumps(row.dimensions, sort_keys=True, default=str),
                    "model_cost_cents": row.model_cost_cents,
                    "compute_cost_cents": row.compute_cost_cents,
                    "storage_cost_cents": row.storage_cost_cents,
                    "overhead_cost_cents": row.overhead_cost_cents,
                    "total_cost_cents": row.total_cost_cents,
                    "currency": row.currency,
                }
            )
        return ChargebackExportResponse(
            filename=f"chargeback-{stem}-{since}-{until}.csv",
            content_type="text/csv",
            content=buffer.getvalue(),
        )

    async def _query_rows(
        self,
        visible_workspace_ids: list[UUID],
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        if not visible_workspace_ids:
            return []
        if self.clickhouse_repository is not None:
            return await self.clickhouse_repository.query_cost_rollups(
                visible_workspace_ids,
                group_by,
                since,
                until,
            )
        rows: list[dict[str, Any]] = []
        for workspace_id in visible_workspace_ids:
            rows.extend(
                await self.repository.aggregate_attributions(workspace_id, group_by, since, until)
            )
        return rows

    async def _visible_workspace_ids(self, requester: UUID) -> list[UUID]:
        if self.workspaces_service is None:
            return await self.repository.list_workspace_ids_with_costs()
        getter = getattr(self.workspaces_service, "get_user_workspace_ids", None)
        if callable(getter):
            return list(await getter(requester))
        return await self.repository.list_workspace_ids_with_costs()

    async def _audit(self, event: str, event_id: UUID, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        await audit_chain_hook(
            self.audit_chain_service,
            uuid4(),
            "cost_governance",
            {"event": event, "event_id": str(event_id), **payload},
        )


def _dimension_payload(row: dict[str, Any]) -> dict[str, Any]:
    cost_keys = {
        "model_cost_cents",
        "compute_cost_cents",
        "storage_cost_cents",
        "overhead_cost_cents",
        "total_cost_cents",
    }
    return {key: value for key, value in row.items() if key not in cost_keys}
