from __future__ import annotations

import json
from typing import Any
from uuid import UUID


async def audit_chain_hook(
    service: Any,
    audit_event_id: UUID | None,
    source: str,
    row_as_dict: dict[str, Any],
) -> Any:
    canonical_payload = json.dumps(
        row_as_dict,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return await service.append(audit_event_id, source, canonical_payload)
