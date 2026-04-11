from __future__ import annotations

from platform.registry.models import LifecycleStatus
from platform.registry.state_machine import (
    EVENT_TRANSITIONS,
    VALID_REGISTRY_TRANSITIONS,
    get_valid_transitions,
    is_valid_transition,
)

import pytest


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LifecycleStatus.draft, LifecycleStatus.validated),
        (LifecycleStatus.validated, LifecycleStatus.published),
        (LifecycleStatus.published, LifecycleStatus.disabled),
        (LifecycleStatus.published, LifecycleStatus.deprecated),
        (LifecycleStatus.disabled, LifecycleStatus.published),
        (LifecycleStatus.deprecated, LifecycleStatus.archived),
    ],
)
def test_state_machine_accepts_valid_transitions(
    current: LifecycleStatus,
    target: LifecycleStatus,
) -> None:
    assert is_valid_transition(current, target) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LifecycleStatus.draft, LifecycleStatus.published),
        (LifecycleStatus.validated, LifecycleStatus.disabled),
        (LifecycleStatus.disabled, LifecycleStatus.archived),
        (LifecycleStatus.archived, LifecycleStatus.published),
    ],
)
def test_state_machine_rejects_invalid_transitions(
    current: LifecycleStatus,
    target: LifecycleStatus,
) -> None:
    assert is_valid_transition(current, target) is False


@pytest.mark.parametrize("status", list(LifecycleStatus))
def test_get_valid_transitions_matches_transition_map(status: LifecycleStatus) -> None:
    assert get_valid_transitions(status) == VALID_REGISTRY_TRANSITIONS[status]


def test_archived_has_no_valid_transitions_and_event_transitions_are_expected() -> None:
    assert get_valid_transitions(LifecycleStatus.archived) == set()
    assert EVENT_TRANSITIONS == {
        LifecycleStatus.published,
        LifecycleStatus.deprecated,
    }
