from __future__ import annotations

import json
from platform.admin.rbac import is_superadmin
from platform.audit.service import AuditChainService
from platform.auth.schemas import RoleType
from typing import Any
from uuid import UUID

ADMIN_AUDIT_SOURCE = "platform.admin"


def actor_user_id(actor: dict[str, Any]) -> UUID:
    return UUID(str(actor["sub"]))


def actor_role(actor: dict[str, Any]) -> str:
    return RoleType.SUPERADMIN.value if is_superadmin(actor) else RoleType.PLATFORM_ADMIN.value


async def append_admin_audit(
    audit_chain: AuditChainService,
    *,
    event_type: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
    severity: str = "info",
) -> None:
    canonical_payload = {
        "event_type": event_type,
        "actor_user_id": str(actor_user_id(actor)),
        **payload,
    }
    encoded = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    await audit_chain.append(
        None,
        ADMIN_AUDIT_SOURCE,
        encoded,
        event_type=event_type,
        actor_role=actor_role(actor),
        severity=severity,
        canonical_payload_json=canonical_payload,
    )
