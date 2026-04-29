from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from platform.admin.bootstrap import BOOTSTRAP_AUDIT_EVENT
from platform.audit.models import AuditChainEntry

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class InstallerState:
    bootstrapped_at: datetime | None
    method: str | None
    instance_name: str | None
    tenant_mode: str | None
    mfa_enrollment: str | None


async def get_installer_state(session: AsyncSession) -> InstallerState:
    result = await session.execute(
        select(AuditChainEntry)
        .where(AuditChainEntry.event_type == BOOTSTRAP_AUDIT_EVENT)
        .order_by(AuditChainEntry.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None or not isinstance(row.canonical_payload, dict):
        return InstallerState(None, None, None, None, None)
    payload = row.canonical_payload
    return InstallerState(
        bootstrapped_at=row.created_at,
        method=_string(payload.get("method")),
        instance_name=_string(payload.get("instance_name")),
        tenant_mode=_string(payload.get("tenant_mode")),
        mfa_enrollment=_string(payload.get("mfa_enrollment")),
    )


def _string(value: object) -> str | None:
    return None if value is None else str(value)
