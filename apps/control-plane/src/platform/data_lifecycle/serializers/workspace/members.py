"""Serialize the workspace member roster into the export.

Privacy guard (FR-751.4): cross-workspace email addresses MUST NOT
appear unless the member has opted in via UPD-042 visibility settings.
For the MVP we conservatively redact ALL email addresses to opaque
user-id form; the opt-in lookup is a Phase 9 polish task.

This is the rule-46/47 boundary: a workspace owner sees only their
workspace's roster; cross-workspace email exposure is forbidden.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_workspace_members(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tenant_id: UUID,
) -> AsyncIterator[tuple[str, bytes]]:
    has_table = await _table_exists(session, "workspaces_memberships")
    if not has_table:
        yield "members/members.json", json.dumps(
            {"items": [], "note": "no workspaces_memberships table"}, indent=2
        ).encode("utf-8")
        return

    rows = await session.execute(
        text(
            """
            SELECT
                user_id::text AS user_id,
                role,
                created_at
            FROM workspaces_memberships
            WHERE workspace_id = :workspace_id
              AND tenant_id = :tenant_id
            ORDER BY role ASC, user_id ASC
            """
        ),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    items: list[dict[str, Any]] = []
    for row in rows.mappings().all():
        # MVP redaction: do NOT include emails or display names. Future
        # work: read each user's UPD-042 visibility opt-in and surface
        # email iff allowed.
        items.append(
            {
                "user_id": row["user_id"],
                "role": row["role"],
                "joined_at": _serializable(row["created_at"]),
            }
        )
    yield "members/members.json", json.dumps(
        {
            "count": len(items),
            "items": items,
            "privacy_note": (
                "Member emails are redacted by default per FR-751.4. "
                "Opt-in disclosure is a Phase 9 enhancement."
            ),
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


async def _table_exists(session: AsyncSession, table: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table
            LIMIT 1
            """
        ),
        {"table": table},
    )
    return result.scalar_one_or_none() is not None


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
