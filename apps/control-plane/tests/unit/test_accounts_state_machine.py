from __future__ import annotations

from platform.accounts.exceptions import InvalidTransitionError
from platform.accounts.models import UserStatus
from platform.accounts.state_machine import VALID_TRANSITIONS, validate_transition

import pytest

VALID_CASES = [
    (from_status, to_status)
    for from_status, targets in VALID_TRANSITIONS.items()
    for to_status in sorted(targets, key=lambda item: item.value)
]
INVALID_CASES = [
    (from_status, to_status)
    for from_status in UserStatus
    for to_status in UserStatus
    if to_status not in VALID_TRANSITIONS[from_status]
]


@pytest.mark.parametrize(("from_status", "to_status"), VALID_CASES)
def test_valid_transitions_are_accepted(from_status: UserStatus, to_status: UserStatus) -> None:
    assert validate_transition(from_status, to_status) is None


@pytest.mark.parametrize(("from_status", "to_status"), INVALID_CASES)
def test_invalid_transitions_raise_error(from_status: UserStatus, to_status: UserStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition(from_status, to_status)

    assert exc_info.value.code == "INVALID_TRANSITION"
    assert exc_info.value.details == {
        "from_status": from_status.value,
        "to_status": to_status.value,
    }
