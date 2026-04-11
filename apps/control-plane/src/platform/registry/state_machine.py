from __future__ import annotations

from platform.registry.models import LifecycleStatus

VALID_REGISTRY_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.draft: {LifecycleStatus.validated},
    LifecycleStatus.validated: {LifecycleStatus.published},
    LifecycleStatus.published: {LifecycleStatus.disabled, LifecycleStatus.deprecated},
    LifecycleStatus.disabled: {LifecycleStatus.published},
    LifecycleStatus.deprecated: {LifecycleStatus.archived},
    LifecycleStatus.archived: set(),
}

EVENT_TRANSITIONS: set[LifecycleStatus] = {
    LifecycleStatus.published,
    LifecycleStatus.deprecated,
}


def is_valid_transition(current: LifecycleStatus, target: LifecycleStatus) -> bool:
    return target in VALID_REGISTRY_TRANSITIONS.get(current, set())


def get_valid_transitions(current: LifecycleStatus) -> set[LifecycleStatus]:
    return set(VALID_REGISTRY_TRANSITIONS.get(current, set()))
