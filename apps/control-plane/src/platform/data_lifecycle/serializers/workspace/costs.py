"""Serialize a workspace's cost attribution rollups into the export."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_workspace_costs(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tenant_id: UUID,
) -> AsyncIterator[tuple[str, bytes]]:
    has_workspace_id = await _column_exists(
        session, "cost_attributions", "workspace_id"
    )
    if not has_workspace_id:
        yield "costs/cost_summary.json", json.dumps(
            {"items": [], "note": "no workspace-scoped cost data"}, indent=2
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT
                date_trunc('day', created_at) AS day,
                category,
                COUNT(*) AS event_count,
                COALESCE(SUM(amount_micro_usd), 0) AS amount_micro_usd
            FROM cost_attributions
            WHERE workspace_id = :workspace_id
              AND tenant_id = :tenant_id
            GROUP BY day, category
            ORDER BY day ASC, category ASC
            """
        ),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        items.append({k: _serializable(v) for k, v in row.items()})
    yield "costs/cost_summary.json", json.dumps(
        {"items": items, "count": len(items), "currency_unit": "micro_usd"},
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


async def _column_exists(session: AsyncSession, table: str, column: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
              AND column_name = :column
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    )
    return result.scalar_one_or_none() is not None


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
