from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

Irreversibility = Literal["reversible", "partially_reversible", "irreversible"]


@dataclass(frozen=True)
class ChangePreview:
    affected_count: int
    irreversibility: Irreversibility
    estimated_duration: timedelta
    cascade_implications: list[str]


def compute_affected_count(operation: object, query: object) -> int:
    explicit = getattr(operation, "affected_count", None)
    if explicit is not None:
        return int(explicit)
    count = getattr(query, "count", None)
    if callable(count):
        return int(count())
    if isinstance(query, list | tuple | set | frozenset):
        return len(query)
    return 0


def classify_irreversibility(operation: object) -> Irreversibility:
    value = str(getattr(operation, "irreversibility", "")).lower()
    if value in {"reversible", "partially_reversible", "irreversible"}:
        return value  # type: ignore[return-value]
    if bool(getattr(operation, "deletes_data", False)):
        return "irreversible"
    if bool(getattr(operation, "external_side_effects", False)):
        return "partially_reversible"
    return "reversible"


def estimate_duration(operation: object) -> timedelta:
    seconds = getattr(operation, "estimated_seconds", None)
    if seconds is not None:
        return timedelta(seconds=int(seconds))
    affected_count = int(getattr(operation, "affected_count", 1) or 1)
    return timedelta(seconds=max(1, affected_count // 25))


def build_change_preview(operation: object, query: object) -> ChangePreview:
    affected_count = compute_affected_count(operation, query)
    return ChangePreview(
        affected_count=affected_count,
        irreversibility=classify_irreversibility(operation),
        estimated_duration=estimate_duration(operation),
        cascade_implications=list(getattr(operation, "cascade_implications", []) or []),
    )
