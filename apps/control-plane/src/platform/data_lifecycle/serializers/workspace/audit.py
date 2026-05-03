"""Serialize the workspace-scoped audit chain entries into the export.

The output is a single JSONL file (one JSON object per line) so that
streaming readers can process arbitrarily large audit histories.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_workspace_audit(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tenant_id: UUID,
) -> AsyncIterator[tuple[str, bytes]]:
    has_workspace_id = await _column_exists(
        session, "audit_chain_entries", "workspace_id"
    )
    if not has_workspace_id:
        yield "audit/audit_chain.jsonl", b""
        yield "audit/index.json", json.dumps(
            {"count": 0, "note": "audit_chain_entries lacks workspace_id"},
            indent=2,
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT id::text AS id,
                   event_type,
                   actor_user_id::text AS actor_user_id,
                   chain_hash,
                   prior_hash,
                   created_at
            FROM audit_chain_entries
            WHERE workspace_id = :workspace_id
              AND tenant_id = :tenant_id
            ORDER BY created_at ASC
            LIMIT 100000
            """
        ),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    lines: list[bytes] = []
    count = 0
    for row in rows.mappings().all():
        entry = {k: _serializable(v) for k, v in row.items()}
        lines.append(json.dumps(entry, sort_keys=True).encode("utf-8") + b"\n")
        count += 1
    yield "audit/audit_chain.jsonl", b"".join(lines)
    yield "audit/index.json", json.dumps(
        {"count": count, "format": "jsonl"}, indent=2
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
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value
