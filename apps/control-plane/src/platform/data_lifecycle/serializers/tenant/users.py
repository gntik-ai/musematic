"""Serialize the tenant's user roster into the export.

Cross-context email exposure follows UPD-042 visibility settings; for
the MVP we redact emails uniformly to user-id form. Phase 9 polish
adds opt-in disclosure.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_tenant_users(
    *, session: AsyncSession, tenant_id: UUID
) -> AsyncIterator[tuple[str, bytes]]:
    has_users_table = await _table_exists(session, "users")
    if not has_users_table:
        yield "users/users.json", json.dumps(
            {"items": [], "note": "no users table"}, indent=2
        ).encode("utf-8")
        return

    has_tenant_id = await _column_exists(session, "users", "tenant_id")
    if not has_tenant_id:
        yield "users/users.json", json.dumps(
            {"items": [], "note": "users table has no tenant_id"}, indent=2
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT
                id::text AS user_id,
                status,
                created_at
            FROM users
            WHERE tenant_id = :tenant_id
            ORDER BY created_at ASC
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        items.append(
            {
                "user_id": row["user_id"],
                "status": row.get("status"),
                "created_at": _serializable(row["created_at"]),
            }
        )
    yield "users/users.json", json.dumps(
        {
            "count": len(items),
            "items": items,
            "privacy_note": (
                "User emails and display names are redacted by default. "
                "Opt-in disclosure is a Phase 9 enhancement."
            ),
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


async def _table_exists(session: AsyncSession, table: str) -> bool:
    r = await session.execute(
        text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = :t LIMIT 1
            """
        ),
        {"t": table},
    )
    return r.scalar_one_or_none() is not None


async def _column_exists(session: AsyncSession, table: str, column: str) -> bool:
    r = await session.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :t AND column_name = :c LIMIT 1
            """
        ),
        {"t": table, "c": column},
    )
    return r.scalar_one_or_none() is not None


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
