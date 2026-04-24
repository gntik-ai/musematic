from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


def _resolve_sunset(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        sunset = value
    else:
        sunset = datetime.fromisoformat(value)
    if sunset.tzinfo is None:
        return sunset.replace(tzinfo=UTC)
    return sunset.astimezone(UTC)


def _deprecation_note(sunset: datetime, successor: str | None) -> str:
    note = f".. deprecated:: Sunset on {sunset.date().isoformat()}."
    if successor:
        note = f"{note} Successor: {successor}"
    return note


def deprecated_route(
    *,
    sunset: str | datetime,
    successor: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    sunset_dt = _resolve_sunset(sunset)
    note = _deprecation_note(sunset_dt, successor)

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        cast(Any, fn).__deprecated_marker__ = sunset_dt, successor
        existing_doc = (fn.__doc__ or "").strip()
        fn.__doc__ = f"{note}\n\n{existing_doc}" if existing_doc else note
        return fn

    return decorator
