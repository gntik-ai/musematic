from __future__ import annotations

from platform.accounts.exceptions import InvalidTransitionError
from platform.accounts.models import UserStatus

VALID_TRANSITIONS: dict[UserStatus, set[UserStatus]] = {
    UserStatus.pending_verification: {
        UserStatus.pending_approval,
        UserStatus.active,
    },
    UserStatus.pending_approval: {
        UserStatus.active,
        UserStatus.archived,
    },
    UserStatus.active: {
        UserStatus.suspended,
        UserStatus.blocked,
        UserStatus.archived,
    },
    UserStatus.suspended: {
        UserStatus.active,
        UserStatus.blocked,
        UserStatus.archived,
    },
    UserStatus.blocked: {
        UserStatus.active,
        UserStatus.archived,
    },
    UserStatus.archived: set(),
}


def validate_transition(from_status: UserStatus, to_status: UserStatus) -> None:
    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(from_status.value, to_status.value)
