from __future__ import annotations

from platform.auth.events import PermissionDeniedPayload, publish_auth_event
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PolicyViolationError
from typing import Final
from uuid import UUID, uuid4

PURPOSE_ACTION_MAP: Final[dict[str, set[tuple[str, str]]]] = {
    "data-analysis": {
        ("analytics", "read"),
        ("execution", "read"),
        ("memory", "read"),
    },
    "orchestration": {
        ("execution", "read"),
        ("execution", "write"),
        ("workflow", "read"),
        ("workflow", "write"),
    },
    "retrieval": {
        ("memory", "read"),
        ("tool", "read"),
    },
}


async def check_purpose_bound(
    identity_type: str,
    agent_purpose: str | None,
    resource_type: str,
    action: str,
    producer: EventProducer | None,
    correlation_id: UUID,
    *,
    identity_id: UUID | None = None,
) -> None:
    if identity_type != "agent":
        return

    allowed_actions = PURPOSE_ACTION_MAP.get(agent_purpose or "", set())
    if (resource_type, action) in allowed_actions:
        return

    if identity_id is not None:
        await publish_auth_event(
            "auth.permission.denied",
            PermissionDeniedPayload(
                user_id=identity_id,
                resource_type=resource_type,
                action=action,
                reason="purpose_violation",
            ),
            correlation_id or uuid4(),
            producer,
        )
    raise PolicyViolationError(
        "PURPOSE_VIOLATION",
        "Requested action is outside the declared agent purpose",
    )
