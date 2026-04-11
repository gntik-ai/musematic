from __future__ import annotations

from platform.interactions.exceptions import InvalidStateTransitionError
from platform.interactions.models import InteractionState

INTERACTION_TRANSITIONS: dict[tuple[InteractionState, str], InteractionState] = {
    (InteractionState.initializing, "ready"): InteractionState.ready,
    (InteractionState.ready, "start"): InteractionState.running,
    (InteractionState.ready, "cancel"): InteractionState.canceled,
    (InteractionState.running, "wait"): InteractionState.waiting,
    (InteractionState.running, "pause"): InteractionState.paused,
    (InteractionState.running, "complete"): InteractionState.completed,
    (InteractionState.running, "fail"): InteractionState.failed,
    (InteractionState.running, "cancel"): InteractionState.canceled,
    (InteractionState.waiting, "resume"): InteractionState.running,
    (InteractionState.waiting, "pause"): InteractionState.paused,
    (InteractionState.waiting, "cancel"): InteractionState.canceled,
    (InteractionState.paused, "resume"): InteractionState.running,
    (InteractionState.paused, "cancel"): InteractionState.canceled,
}


def validate_transition(current: InteractionState, trigger: str) -> InteractionState:
    next_state = INTERACTION_TRANSITIONS.get((current, trigger))
    if next_state is None:
        raise InvalidStateTransitionError(current.value, trigger)
    return next_state
