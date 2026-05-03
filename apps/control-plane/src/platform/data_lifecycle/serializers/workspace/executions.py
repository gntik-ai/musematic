"""Serialize a workspace's executions + journal events into the export."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_workspace_executions(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tenant_id: UUID,
) -> AsyncIterator[tuple[str, bytes]]:
    has_workspace_id = await _column_exists(session, "executions", "workspace_id")
    if not has_workspace_id:
        yield "executions/index.json", json.dumps(
            {"items": [], "note": "no workspace_id column on executions"}, indent=2
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT id::text AS id,
                   workflow_id::text AS workflow_id,
                   status,
                   created_at,
                   updated_at,
                   completed_at
            FROM executions
            WHERE workspace_id = :workspace_id
              AND tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 5000
            """
        ),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        item = {k: _serializable(v) for k, v in row.items()}
        items.append(item)
        yield (
            f"executions/{item['id']}.json",
            json.dumps(item, indent=2, sort_keys=True).encode("utf-8"),
        )
    yield "executions/index.json", json.dumps(
        {"count": len(items), "items": [{"id": i["id"], "status": i.get("status")} for i in items]},
        indent=2,
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
