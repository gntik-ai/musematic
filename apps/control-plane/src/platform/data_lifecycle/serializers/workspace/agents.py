"""Serialize a workspace's agents into the export ZIP.

Reads from ``registry_agent_profiles`` and ``registry_agent_revisions``
filtered by workspace_id. Writes one JSON file per agent under
``agents/`` plus a top-level ``agents/index.json`` listing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_workspace_agents(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tenant_id: UUID,
) -> AsyncIterator[tuple[str, bytes]]:
    """Yield (filepath, bytes) entries for the workspace's agents."""

    # Detect column existence to stay tolerant across schema migrations.
    has_workspace_id = await _column_exists(
        session, "registry_agent_profiles", "workspace_id"
    )
    if not has_workspace_id:
        # Older snapshots stored the workspace association elsewhere.
        # Emit only an index marker so the export remains well-formed.
        yield "agents/index.json", json.dumps(
            {"items": [], "note": "no workspace-scoped agents schema available"},
            indent=2,
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT id::text AS id,
                   fqn,
                   display_name,
                   status,
                   marketplace_scope,
                   created_at,
                   updated_at
            FROM registry_agent_profiles
            WHERE workspace_id = :workspace_id
              AND tenant_id = :tenant_id
            ORDER BY fqn ASC
            """
        ),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        item = {k: _serializable(v) for k, v in row.items()}
        items.append(item)
        yield (
            f"agents/{item['fqn'].replace('/', '__')}.json",
            json.dumps(item, indent=2, sort_keys=True).encode("utf-8"),
        )
    yield "agents/index.json", json.dumps(
        {"count": len(items), "items": [{"fqn": i["fqn"], "id": i["id"]} for i in items]},
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
    if isinstance(value, (UUID,)):
        return str(value)
    return value
