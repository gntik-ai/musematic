from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.audit_hook import audit_chain_hook
from platform.common.events.envelope import CorrelationContext
from typing import Any
from uuid import UUID, uuid4


def correlation() -> CorrelationContext:
    return CorrelationContext(correlation_id=uuid4())


async def append_audit(
    audit_chain: AuditChainService | None,
    audit_event_id: UUID | None,
    source: str,
    row: dict[str, Any],
) -> None:
    if audit_chain is None:
        return
    await audit_chain_hook(audit_chain, audit_event_id, source, row)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def utcnow() -> datetime:
    return datetime.now(UTC)
