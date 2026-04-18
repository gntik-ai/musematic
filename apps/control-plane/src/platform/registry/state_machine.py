from __future__ import annotations

from platform.registry.models import LifecycleStatus

VALID_REGISTRY_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.draft: {LifecycleStatus.validated, LifecycleStatus.decommissioned},
    LifecycleStatus.validated: {LifecycleStatus.published, LifecycleStatus.decommissioned},
    LifecycleStatus.published: {
        LifecycleStatus.disabled,
        LifecycleStatus.deprecated,
        LifecycleStatus.decommissioned,
    },
    LifecycleStatus.disabled: {LifecycleStatus.published, LifecycleStatus.decommissioned},
    LifecycleStatus.deprecated: {LifecycleStatus.archived, LifecycleStatus.decommissioned},
    LifecycleStatus.archived: {LifecycleStatus.decommissioned},
    LifecycleStatus.decommissioned: set(),
}

EVENT_TRANSITIONS: set[LifecycleStatus] = {
    LifecycleStatus.published,
    LifecycleStatus.deprecated,
    LifecycleStatus.decommissioned,
}


def is_valid_transition(current: LifecycleStatus, target: LifecycleStatus) -> bool:
    return target in VALID_REGISTRY_TRANSITIONS.get(current, set())


def get_valid_transitions(current: LifecycleStatus) -> set[LifecycleStatus]:
    return set(VALID_REGISTRY_TRANSITIONS.get(current, set()))
