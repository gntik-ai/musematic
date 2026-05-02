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


# ---------------------------------------------------------------------------
# UPD-049 — review_status state machine for the public-marketplace lifecycle.
# `review_status` lives on `registry_agent_profiles` alongside the existing
# `status` (LifecycleStatus). They are independent dimensions: a row's
# `status` is its lifecycle in the publishing tenant; `review_status` is
# the public-marketplace review state. Workspace/tenant-scope publish moves
# directly to `published`; public-scope publish moves through review.
# ---------------------------------------------------------------------------

# review_status values are plain strings (not an enum) — see registry/models.py
# where the column is `String(length=32)` with a CHECK constraint per
# migration 108. The state machine enumerates the legal transitions.

VALID_REVIEW_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review", "published"},
    "pending_review": {"approved", "rejected"},
    "approved": {"published"},  # auto-published on approve in the service flow
    "published": {"deprecated"},
    "deprecated": set(),  # terminal in this state machine
    "rejected": {"pending_review"},  # resubmit after addressing the reason
}


def is_valid_review_transition(current: str, target: str) -> bool:
    return target in VALID_REVIEW_TRANSITIONS.get(current, set())


def get_valid_review_transitions(current: str) -> set[str]:
    return set(VALID_REVIEW_TRANSITIONS.get(current, set()))
