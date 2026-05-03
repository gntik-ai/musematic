"""Serialize the tenant row + DPA history into the export."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_tenant_meta(
    *, session: AsyncSession, tenant_id: UUID
) -> AsyncIterator[tuple[str, bytes]]:
    rows = await session.execute(
        text(
            """
            SELECT
                id::text AS id,
                slug,
                kind,
                status,
                region,
                dpa_signed_at,
                dpa_version,
                dpa_artifact_sha256
            FROM tenants
            WHERE id = :tenant_id
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    row = rows.mappings().first()
    if row is None:
        yield "tenant/tenant.json", json.dumps(
            {"error": "tenant not found"}, indent=2
        ).encode("utf-8")
        return
    payload = {k: _serializable(v) for k, v in row.items()}
    yield "tenant/tenant.json", json.dumps(
        payload, indent=2, sort_keys=True
    ).encode("utf-8")
    # DPA history is reconstructed from audit chain entries elsewhere;
    # the tenant.json snapshot includes the active DPA hash so external
    # readers can verify the active version.


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
