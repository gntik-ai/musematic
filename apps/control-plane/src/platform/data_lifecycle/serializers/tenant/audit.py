"""Serialize the tenant-scoped audit chain into the export.

Output is JSONL (one JSON object per line). Limited to the most-recent
12 months per FR-758.1 (Article 28 evidence package); the deletion
cold-storage tombstone retains the full history per FR-754.6.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_tenant_audit(
    *, session: AsyncSession, tenant_id: UUID
) -> AsyncIterator[tuple[str, bytes]]:
    cutoff = datetime.now(UTC) - timedelta(days=365)
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
            WHERE tenant_id = :tenant_id
              AND created_at >= :cutoff
            ORDER BY created_at ASC
            LIMIT 100000
            """
        ),
        {"tenant_id": str(tenant_id), "cutoff": cutoff.isoformat()},
    )
    lines: list[bytes] = []
    count = 0
    for row in rows.mappings().all():
        entry = {k: _serializable(v) for k, v in row.items()}
        lines.append(json.dumps(entry, sort_keys=True).encode("utf-8") + b"\n")
        count += 1
    yield "audit/audit_chain.jsonl", b"".join(lines)
    yield "audit/index.json", json.dumps(
        {"count": count, "format": "jsonl", "window_days": 365}, indent=2
    ).encode("utf-8")


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value
