"""Serialize the tenant's cost rollups by month into the export."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_tenant_costs(
    *, session: AsyncSession, tenant_id: UUID
) -> AsyncIterator[tuple[str, bytes]]:
    rows = await session.execute(
        text(
            """
            SELECT
                date_trunc('month', created_at) AS month,
                category,
                COUNT(*) AS event_count,
                COALESCE(SUM(amount_micro_usd), 0) AS amount_micro_usd
            FROM cost_attributions
            WHERE tenant_id = :tenant_id
            GROUP BY month, category
            ORDER BY month ASC, category ASC
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        items.append({k: _serializable(v) for k, v in row.items()})
    yield "costs/cost_history.json", json.dumps(
        {"items": items, "count": len(items), "currency_unit": "micro_usd"},
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
