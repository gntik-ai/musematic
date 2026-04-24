from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class DeprecationMarker:
    sunset: datetime
    successor_path: str | None


_markers: dict[str, DeprecationMarker] = {}


def _normalize_sunset(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def clear_markers() -> None:
    _markers.clear()


def mark_deprecated(
    route_id: str,
    *,
    sunset: datetime,
    successor: str | None = None,
) -> None:
    _markers[route_id] = DeprecationMarker(
        sunset=_normalize_sunset(sunset),
        successor_path=successor,
    )


def get_marker(route_id: str | None) -> DeprecationMarker | None:
    if route_id is None:
        return None
    return _markers.get(route_id)
